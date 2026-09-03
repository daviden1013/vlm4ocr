"""
Pluggable PDF rendering backends.

vlm4ocr depends on no PDF library. Users who process PDFs pick a backend and install it
themselves, so users who never touch PDFs carry no PDF dependency and no third-party
license obligation. There is no automatic selection and no fallback: the backend is named
explicitly, and if it fails, the error is reported rather than silently retried elsewhere.
Deciding what to do about a document that will not load is the caller's business logic.

Three backends are supported, which is the whole field: these are the only three PDF
rasterizers available to Python. Everything else (pypdf, pdfplumber, pdfminer, pikepdf)
parses or manipulates PDFs but cannot render a page to an image.

    backend       library      renderer   license
    ----------------------------------------------------------------------
    pypdfium2     pypdfium2    PDFium     Apache-2.0 / BSD-3 (permissive)
    pdf2image     pdf2image    poppler    MIT wrapper, GPL poppler binary
    pymupdf       pymupdf      MuPDF      AGPL-3.0

Thread safety: PDFium and MuPDF are not thread-safe, and neither pypdfium2 nor PyMuPDF
serializes access for you. Every backend therefore holds a per-document lock around
rendering. The lock is per document, not global, so rendering many documents at once still
runs in parallel; only two pages of the SAME document are serialized. Since the VLM call
dominates OCR latency, that costs nothing in practice.
"""
import abc
import os
import threading
from typing import List, Optional

from PIL import Image

from vlm4ocr.exceptions import DocumentLoadError, PDFBackendNotAvailableError

# Rendering resolution used when the caller does not specify one. 200 dpi is what
# pdf2image produced by default in earlier versions of vlm4ocr, so results are unchanged
# for existing pdf2image users. pypdfium2 and PyMuPDF both default to 72 dpi natively, so
# this value is applied explicitly to every backend to keep page images comparable.
DEFAULT_PDF_DPI = 200

# pip target -> what to install for each backend
_INSTALL_HINTS = {
    "pypdfium2": "pip install vlm4ocr[pypdfium2]   (or: pip install pypdfium2)",
    "pdf2image": "pip install vlm4ocr[pdf2image]   (or: pip install pdf2image, plus the poppler binary)",
    "pymupdf": "pip install vlm4ocr[pymupdf]     (or: pip install pymupdf)",
}


class PDFBackend(abc.ABC):
    """
    Base class for PDF rendering backends.

    A backend opens one document, reports its page count, and renders pages to PIL images
    at a requested dpi. Opening happens eagerly in __init__ so that a document which cannot
    be read fails immediately, before any page work or VLM call is attempted.
    """
    name: str = "unknown"

    def __init__(self, file_path: str, dpi: int = DEFAULT_PDF_DPI):
        self.file_path = file_path
        self.dpi = dpi
        # PDFium and MuPDF are not thread-safe; see the module docstring.
        self._lock = threading.Lock()
        self._open()

    @abc.abstractmethod
    def _open(self) -> None:
        """ Opens the document and validates it. Must raise DocumentLoadError on failure. """

    @abc.abstractmethod
    def get_page_count(self) -> int:
        """ Returns the number of pages. """

    @abc.abstractmethod
    def _render(self, page_index: int) -> Image.Image:
        """ Renders one page at self.dpi. Called with the document lock held. """

    def render_page(self, page_index: int) -> Image.Image:
        """
        Renders a single page, serialized per document.

        Raises:
        -------
        DocumentLoadError
            If the page cannot be rendered.
        """
        try:
            with self._lock:
                return self._render(page_index)
        except DocumentLoadError:
            raise
        except Exception as e:
            raise DocumentLoadError(
                f"Failed to render page {page_index} of PDF file '{os.path.basename(self.file_path)}'.",
                file_path=self.file_path, backend=self.name, page_index=page_index, cause=e) from e

    def render_all_pages(self) -> List[Image.Image]:
        """
        Renders every page. Backends that can render a whole document in one operation
        override this; the default renders page by page.
        """
        return [self.render_page(i) for i in range(self.get_page_count())]

    def close(self) -> None:
        """ Releases the underlying document handle. Safe to call more than once. """

    def _load_error(self, message: str, cause: Optional[BaseException] = None) -> DocumentLoadError:
        """ Builds a document-level DocumentLoadError tagged with this backend. """
        return DocumentLoadError(message, file_path=self.file_path, backend=self.name, cause=cause)


class PyPdfium2Backend(PDFBackend):
    """PDFium via pypdfium2. Permissively licensed and needs no system binary."""
    name = "pypdfium2"

    def _open(self) -> None:
        try:
            import pypdfium2
        except ImportError as e:
            raise PDFBackendNotAvailableError(
                f"PDF backend 'pypdfium2' is not installed. {_INSTALL_HINTS['pypdfium2']}",
                backend="pypdfium2", file_path=self.file_path, cause=e) from e
        self._pypdfium2 = pypdfium2
        try:
            self._doc = pypdfium2.PdfDocument(self.file_path)
            self._page_count = len(self._doc)
        except Exception as e:
            # PDFium reports a damaged file and a file that is not a PDF with the same
            # message, so no finer distinction is available here. The verbatim text is
            # preserved on the exception for callers that need to match on it.
            raise self._load_error(
                f"Failed to open PDF file '{os.path.basename(self.file_path)}'.", cause=e) from e

    def get_page_count(self) -> int:
        return self._page_count

    def _render(self, page_index: int) -> Image.Image:
        page = self._doc[page_index]
        try:
            # scale is relative to PDF user space, which is 72 dpi.
            return page.render(scale=self.dpi / 72).to_pil()
        finally:
            # pypdfium2 asserts that children are closed before their parent document, and
            # its finalizers run at GC time, so pages are released explicitly here.
            page.close()

    def close(self) -> None:
        doc = getattr(self, "_doc", None)
        if doc is not None:
            doc.close()
            self._doc = None


class Pdf2ImageBackend(PDFBackend):
    """
    poppler via pdf2image. Note that poppler itself is GPL-licensed and must be installed
    as a system binary. Each render spawns a poppler subprocess, so this backend is process
    isolated but re-parses the document on every page.
    """
    name = "pdf2image"

    def _open(self) -> None:
        try:
            from pdf2image import convert_from_path, pdfinfo_from_path
        except ImportError as e:
            raise PDFBackendNotAvailableError(
                f"PDF backend 'pdf2image' is not installed. {_INSTALL_HINTS['pdf2image']}",
                backend="pdf2image", file_path=self.file_path, cause=e) from e
        self._convert_from_path = convert_from_path
        try:
            info = pdfinfo_from_path(self.file_path, userpw=None, poppler_path=None)
        except Exception as e:
            # pdf2image funnels a missing poppler binary, a damaged file, and a wrong
            # password all through PDFPageCountError, so they cannot be told apart by type.
            raise self._load_error(
                f"Failed to open PDF file '{os.path.basename(self.file_path)}'.", cause=e) from e
        self._page_count = info.get("Pages", 0)

    def get_page_count(self) -> int:
        return self._page_count

    def _render(self, page_index: int) -> Image.Image:
        pages = self._convert_from_path(self.file_path, dpi=self.dpi,
                                        first_page=page_index + 1, last_page=page_index + 1)
        if not pages:
            raise self._load_error(
                f"poppler returned no image for page {page_index} of "
                f"'{os.path.basename(self.file_path)}'.")
        return pages[0]

    def render_all_pages(self) -> List[Image.Image]:
        # One poppler call for the whole document. Rendering page by page would re-parse
        # the PDF once per page, which is quadratic in page count.
        try:
            with self._lock:
                return self._convert_from_path(self.file_path, dpi=self.dpi)
        except Exception as e:
            raise self._load_error(
                f"Failed to render PDF file '{os.path.basename(self.file_path)}'.", cause=e) from e


class PyMuPDFBackend(PDFBackend):
    """
    MuPDF via PyMuPDF. The most damage-tolerant of the three, but AGPL-3.0 licensed, so
    installing it is a deliberate choice with license consequences for the installer.
    """
    name = "pymupdf"

    def _open(self) -> None:
        try:
            import pymupdf
        except ImportError as e:
            raise PDFBackendNotAvailableError(
                f"PDF backend 'pymupdf' is not installed. {_INSTALL_HINTS['pymupdf']}",
                backend="pymupdf", file_path=self.file_path, cause=e) from e
        self._pymupdf = pymupdf
        try:
            self._doc = pymupdf.open(self.file_path)
        except Exception as e:
            raise self._load_error(
                f"Failed to open PDF file '{os.path.basename(self.file_path)}'.", cause=e) from e

        # MuPDF recovers from damage rather than refusing to open, so two failure modes
        # arrive as a successfully opened document instead of an exception and have to be
        # checked explicitly. Without these checks a password-protected or unsalvageable
        # file would silently produce a blank or empty OCR result.
        if self._doc.needs_pass:
            self._doc.close()
            self._doc = None
            raise self._load_error(
                f"PDF file '{os.path.basename(self.file_path)}' is password protected.")
        if self._doc.page_count == 0:
            repaired = getattr(self._doc, "is_repaired", False)
            self._doc.close()
            self._doc = None
            raise self._load_error(
                f"PDF file '{os.path.basename(self.file_path)}' contains no readable pages"
                + (" (MuPDF attempted to repair it)." if repaired else "."))
        self._page_count = self._doc.page_count

    def get_page_count(self) -> int:
        return self._page_count

    def _render(self, page_index: int) -> Image.Image:
        import io
        pixmap = self._doc[page_index].get_pixmap(dpi=self.dpi)
        return Image.open(io.BytesIO(pixmap.tobytes("png")))

    def close(self) -> None:
        doc = getattr(self, "_doc", None)
        if doc is not None:
            doc.close()
            self._doc = None


PDF_BACKENDS = {
    "pypdfium2": PyPdfium2Backend,
    "pdf2image": Pdf2ImageBackend,
    "pymupdf": PyMuPDFBackend,
}

SUPPORTED_PDF_BACKENDS = tuple(PDF_BACKENDS)


def get_pdf_backend(file_path: str, backend: Optional[str],
                    dpi: int = DEFAULT_PDF_DPI) -> PDFBackend:
    """
    Builds the named PDF backend for a file.

    Parameters:
    -----------
    file_path : str
        Path to the PDF.
    backend : str | None
        One of 'pypdfium2', 'pdf2image', 'pymupdf'. Required: there is no default backend,
        because vlm4ocr does not depend on any PDF library and will not guess which one a
        deployment is meant to use.
    dpi : int, Optional
        Rendering resolution. Defaults to 200.

    Raises:
    -------
    PDFBackendNotAvailableError
        If no backend was named, or the named backend is not installed.
    ValueError
        If the named backend is not a recognised name.
    DocumentLoadError
        If the document could not be opened.
    """
    if backend is None:
        raise PDFBackendNotAvailableError(
            "Loading a PDF requires a PDF backend, and none was specified. Pass "
            "pdf_backend='pypdfium2' (or 'pdf2image' / 'pymupdf') and install it:\n  "
            + "\n  ".join(_INSTALL_HINTS[b] for b in SUPPORTED_PDF_BACKENDS),
            file_path=file_path)
    if backend not in PDF_BACKENDS:
        raise ValueError(f"Unknown PDF backend: {backend!r}. "
                         f"Supported backends are: {list(SUPPORTED_PDF_BACKENDS)}")
    if not isinstance(dpi, int) or dpi <= 0:
        raise ValueError("pdf_dpi must be a positive integer")
    return PDF_BACKENDS[backend](file_path, dpi=dpi)
