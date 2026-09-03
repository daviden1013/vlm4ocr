"""
Exception taxonomy for vlm4ocr.

The design goal is to report WHERE a failure happened and WHAT the underlying library
said, and nothing more. vlm4ocr deliberately does not classify errors as retryable,
transient, or fixable-by-X: how to react to a corrupted PDF, a rate-limited endpoint, or
an unparseable response is business logic that belongs to the calling pipeline.

- WHERE is the exception class. Each class corresponds to one step of the OCR flow:
  loading the document, calling the VLM, parsing the response.
- WHAT is `original_error` / `original_error_type`, copied verbatim from the underlying
  library, plus the chained `__cause__`.

The verbatim copy matters. PDF backends do not agree on how much they tell you, and none
of them distinguish every failure mode: pypdfium2 returns a byte-identical message for a
truncated PDF and for a file that is not a PDF at all, while pdf2image funnels everything
through PDFPageCountError. vlm4ocr therefore does not invent finer-grained subclasses than
the backends can actually support. Callers who need a sharper distinction (for example
telling "encrypted" apart from "damaged") can match on `original_error` themselves.
"""
from typing import Any, Dict, Optional


class VLM4OCRError(Exception):
    """
    Base class for all vlm4ocr errors.

    Attributes:
    ----------
    file_path : str | None
        The input file being processed when the error occurred.
    original_error : str | None
        str() of the underlying library's exception, verbatim and unmodified.
    original_error_type : str | None
        Class name of the underlying exception, e.g. "PdfiumError", "FileDataError".
    """
    def __init__(self, message: str, *, file_path: Optional[str] = None,
                 cause: Optional[BaseException] = None):
        super().__init__(message)
        self.message = message
        self.file_path = file_path
        self.original_error = str(cause) if cause is not None else None
        self.original_error_type = type(cause).__name__ if cause is not None else None

    def to_dict(self) -> Dict[str, Any]:
        """
        A JSON-serializable view of the error, for logging or persisting alongside results.
        Subclasses add their own fields.
        """
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "file_path": self.file_path,
            "original_error": self.original_error,
            "original_error_type": self.original_error_type,
        }

    def __str__(self) -> str:
        if self.original_error:
            return f"{self.message} ({self.original_error_type}: {self.original_error})"
        return self.message


class PDFBackendNotAvailableError(VLM4OCRError):
    """
    Raised when a PDF must be loaded but no usable PDF backend is available: either none
    was specified, or the specified one is not installed.

    vlm4ocr does not depend on any PDF rendering library. Users who process PDFs choose a
    backend and install it themselves, so that users who never touch PDFs carry no PDF
    dependency and no third-party license obligations.

    Attributes:
    ----------
    backend : str | None
        The backend that was requested, or None if none was specified.
    """
    def __init__(self, message: str, *, backend: Optional[str] = None,
                 file_path: Optional[str] = None, cause: Optional[BaseException] = None):
        super().__init__(message, file_path=file_path, cause=cause)
        self.backend = backend

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["backend"] = self.backend
        return d


class DocumentLoadError(VLM4OCRError):
    """
    Raised when a document could not be opened, its page count could not be determined, or
    a page could not be decoded or rasterized. This is the document-loading step; no VLM
    call has been made.

    Attributes:
    ----------
    backend : str | None
        Which loader produced the error, e.g. "pdf2image", "pypdfium2", "pymupdf", "pillow".
    page_index : int | None
        The page being loaded, or None when the failure is document-level (open, page count).
        A None page_index means no page of this document is usable.
    """
    def __init__(self, message: str, *, file_path: Optional[str] = None,
                 backend: Optional[str] = None, page_index: Optional[int] = None,
                 cause: Optional[BaseException] = None):
        super().__init__(message, file_path=file_path, cause=cause)
        self.backend = backend
        self.page_index = page_index

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["backend"] = self.backend
        d["page_index"] = self.page_index
        return d


class VLMError(VLM4OCRError):
    """
    Raised when the VLM call itself fails: connection, timeout, rate limit, authentication,
    or any other provider-side error. The provider's exception is preserved verbatim in
    `original_error`, since only the caller knows which of those warrant a retry.

    Attributes:
    ----------
    page_index : int | None
        The page whose VLM call failed.
    """
    def __init__(self, message: str, *, file_path: Optional[str] = None,
                 page_index: Optional[int] = None, cause: Optional[BaseException] = None):
        super().__init__(message, file_path=file_path, cause=cause)
        self.page_index = page_index

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["page_index"] = self.page_index
        return d


class OutputParseError(VLM4OCRError):
    """
    Raised when the VLM responded but its output could not be parsed into the requested
    output_mode, e.g. unparseable bounding boxes in 'bbox' mode. The VLM call succeeded and
    was paid for; the raw response is kept in `raw_response` so it is not lost.

    Attributes:
    ----------
    page_index : int | None
        The page whose response could not be parsed.
    raw_response : str | None
        The model's unparsed output.
    """
    def __init__(self, message: str, *, file_path: Optional[str] = None,
                 page_index: Optional[int] = None, raw_response: Optional[str] = None,
                 cause: Optional[BaseException] = None):
        super().__init__(message, file_path=file_path, cause=cause)
        self.page_index = page_index
        self.raw_response = raw_response

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["page_index"] = self.page_index
        d["raw_response"] = self.raw_response
        return d
