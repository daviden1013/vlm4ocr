import abc
import os
import io
import base64
from concurrent.futures import Executor
from typing import Dict, List, Optional
import json
import json_repair
from PIL import Image
import asyncio
import warnings
from vlm4ocr.exceptions import DocumentLoadError
from vlm4ocr.pdf_backends import DEFAULT_PDF_DPI, get_pdf_backend


class DataLoader(abc.ABC):
    def __init__(self, file_path: str, executor: Optional[Executor] = None):
        """
        Parameters:
        ----------
        file_path : str
            Path to the file to load.
        executor : concurrent.futures.Executor, Optional
            Thread pool used by get_page_async to run the blocking page load. If None,
            asyncio's default executor is used. Callers processing many files at once
            should pass a dedicated executor so page loading cannot starve other
            run_in_executor work (e.g. resize, tesseract OSD) in the shared default pool.
        """
        self.file_path = file_path
        self.executor = executor
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

    @abc.abstractmethod
    def get_all_pages(self) -> List[Image.Image]:
        """ 
        Abstract method to get all pages from the file. 
        """
        pass

    @abc.abstractmethod
    def get_page(self, page_index:int) -> Image.Image:
        """ 
        Abstract method to get pages from the file. 
        
        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve. 
        """
        pass

    async def get_page_async(self, page_index:int) -> Image.Image:
        """ 
        Asynchronously retrieves a page by running get_page in this loader's executor.
        
        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.get_page, page_index)

    @abc.abstractmethod
    def get_page_count(self) -> int:
        """ Returns the number of pages in the PDF file. """
        pass

    def get_load_info(self) -> dict:
        """
        Describes how this loader produces page images, e.g. {"backend": "pypdfium2",
        "dpi": 200}. Recorded per page in OCRPage.image_processing_status["page_load"] so a
        result can be audited, and so plot_bboxes can reload the source page at exactly the
        resolution the bboxes were computed against.
        """
        return {"backend": "unknown"}

    def close(self) -> None:
        """ Releases any underlying file handle. Safe to call more than once. """


class PDFDataLoader(DataLoader):
    """
    Loads pages from a PDF using an explicitly named rendering backend.

    vlm4ocr has no PDF dependency of its own, so `backend` is required: see
    vlm4ocr.pdf_backends for the three supported options and their licenses.
    """
    def __init__(self, file_path: str, executor: Optional[Executor] = None,
                 backend: Optional[str] = None, dpi: int = DEFAULT_PDF_DPI):
        """
        Parameters:
        ----------
        file_path : str
            Path to the PDF.
        executor : concurrent.futures.Executor, Optional
            Thread pool used by get_page_async. See DataLoader.
        backend : str, Optional
            'pypdfium2', 'pdf2image', or 'pymupdf'. Required; there is no default.
        dpi : int, Optional
            Rendering resolution, applied identically across backends. Defaults to 200.
        """
        super().__init__(file_path, executor=executor)
        # Opening happens here, so a document that cannot be read fails before any page
        # work or VLM call is attempted.
        self.backend = get_pdf_backend(self.file_path, backend, dpi=dpi)
        self.dpi = dpi

    def get_all_pages(self) -> List[Image.Image]:
        """ Renders every page of the PDF. """
        return self.backend.render_all_pages()

    def get_page(self, page_index:int) -> Image.Image:
        """
        Renders a single page of the PDF.

        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve.
        """
        return self.backend.render_page(page_index)

    def get_page_count(self) -> int:
        """ Returns the number of pages in the PDF file. """
        return self.backend.get_page_count()

    def get_load_info(self) -> dict:
        return {"backend": self.backend.name, "dpi": self.dpi}

    def close(self) -> None:
        self.backend.close()


class TIFFDataLoader(DataLoader):
    def __init__(self, file_path: str, executor: Optional[Executor] = None):
        super().__init__(file_path, executor=executor)

    def get_all_pages(self) -> List[Image.Image]:
        """ 
        Extracts images from a TIFF file. 
        """
        try:
            img = Image.open(self.file_path)
            images = []
            for i in range(img.n_frames):
                img.seek(i)
                images.append(img.copy())
            return images
        except Exception as e:
            raise DocumentLoadError(
                f"Failed to read TIFF file '{os.path.basename(self.file_path)}'.",
                file_path=self.file_path, backend="pillow", cause=e) from e
        

    def get_page(self, page_index:int) -> Image.Image:
        """
        Extracts a page from a TIFF file.

        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve. 
        """
        try:
            img = Image.open(self.file_path)
            img.seek(page_index)
            return img.copy()
        except (IndexError, EOFError) as e:
            raise DocumentLoadError(
                f"Page index {page_index} out of range for TIFF file '{os.path.basename(self.file_path)}'.",
                file_path=self.file_path, backend="pillow", page_index=page_index, cause=e) from e
        except Exception as e:
            raise DocumentLoadError(
                f"Failed to read page {page_index} of TIFF file '{os.path.basename(self.file_path)}'.",
                file_path=self.file_path, backend="pillow", page_index=page_index, cause=e) from e

    def get_load_info(self) -> dict:
        return {"backend": "pillow"}

    def get_page_count(self) -> int:
        """ Returns the number of images (pages) in the TIFF file. """
        try:
            img = Image.open(self.file_path)
            return img.n_frames 
        except Exception as e:
            raise DocumentLoadError(
                f"Failed to read page count of TIFF file '{os.path.basename(self.file_path)}'.",
                file_path=self.file_path, backend="pillow", cause=e) from e


class ImageDataLoader(DataLoader):
    def get_all_pages(self) -> List[Image.Image]:
        """ 
        Loads a single image file. 
        """
        try:
            image = Image.open(self.file_path)
            image.load()
            return [image]
        except FileNotFoundError:
            raise
        except Exception as e:
            raise DocumentLoadError(
                f"Failed to load image file '{os.path.basename(self.file_path)}'.",
                file_path=self.file_path, backend="pillow", cause=e) from e
        
    def get_page(self, page_index:int) -> Image.Image:
        """ 
        Loads a single image file. 
        
        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve. Not applicable for single image files.
        """
        try:
            image = Image.open(self.file_path)
            image.load()
            return image
        except FileNotFoundError:
            raise
        except Exception as e:
            raise DocumentLoadError(
                f"Failed to load image file '{os.path.basename(self.file_path)}'.",
                file_path=self.file_path, backend="pillow", cause=e) from e
        
    def get_load_info(self) -> dict:
        return {"backend": "pillow"}

    def get_page_count(self) -> int:
        """ Returns 1 as there is only one image in a single image file. """
        return 1


SUPPORTED_IMAGE_EXTS = ['.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']


def default_page_load_workers() -> int:
    """
    Default size of the page-loading thread pool: one worker per CPU, capped at 32.

    Page loading is CPU-bound work that releases the GIL (PDF rasterization, JPEG/TIFF
    decoding), so it scales with threads up to the core count. Beyond that, extra threads
    only add contention.
    """
    return min(32, os.cpu_count() or 1)


def get_data_loader(file_path: str, executor: Optional[Executor] = None,
                    pdf_backend: Optional[str] = None,
                    pdf_dpi: int = DEFAULT_PDF_DPI) -> DataLoader:
    """
    Returns the appropriate DataLoader for a file based on its extension. Extension
    matching is case-insensitive. Shared by OCREngine and the pipelines.

    Parameters:
    -----------
    file_path : str
        Path to the file to load.
    executor : concurrent.futures.Executor, Optional
        Thread pool the loader uses for async page loads. See DataLoader.
    pdf_backend : str, Optional
        PDF rendering backend: 'pypdfium2', 'pdf2image', or 'pymupdf'. Required for PDF
        input; ignored for images and TIFFs.
    pdf_dpi : int, Optional
        PDF rendering resolution. Defaults to 200.

    Raises:
    -------
    DocumentLoadError
        If the file extension is not in SUPPORTED_IMAGE_EXTS.
    PDFBackendNotAvailableError
        If the file is a PDF and no usable pdf_backend was given.
    """
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext not in SUPPORTED_IMAGE_EXTS:
        raise DocumentLoadError(f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}",
                                file_path=file_path)
    if file_ext == '.pdf':
        return PDFDataLoader(file_path, executor=executor, backend=pdf_backend, dpi=pdf_dpi)
    if file_ext in ('.tif', '.tiff'):
        return TIFFDataLoader(file_path, executor=executor)
    return ImageDataLoader(file_path, executor=executor)


def image_to_base64(image:Image.Image, format:str="png") -> str:
    """ Converts an image to a base64 string. """
    try:
        buffered = io.BytesIO()
        image.save(buffered, format=format)
        img_bytes = buffered.getvalue()
        encoded_bytes = base64.b64encode(img_bytes)
        base64_encoded_string = encoded_bytes.decode('utf-8')
        return base64_encoded_string
    except Exception as e:
        print(f"Error converting image to base64: {e}")
        raise ValueError(f"Failed to convert image to base64: {e}") from e
    
def clean_markdown(text:str) -> str:
    cleaned_text = text.replace("```markdown", "").replace("```", "")
    return cleaned_text

def _find_dict_strings( text: str) -> List[str]:
    """
    Extracts balanced JSON-like dictionaries from a string, even if nested.

    Parameters:
    -----------
    text : str
        the input text containing JSON-like structures.

    Returns : List[str]
        A list of valid JSON-like strings representing dictionaries.
    """
    open_brace = 0
    start = -1
    json_objects = []

    for i, char in enumerate(text):
        if char == '{':
            if open_brace == 0:
                # start of a new JSON object
                start = i 
            open_brace += 1
        elif char == '}':
            open_brace -= 1
            if open_brace == 0 and start != -1:
                json_objects.append(text[start:i + 1])
                start = -1

    return json_objects

def extract_json(gen_text:str) -> List[Dict[str, str]]:
    """ 
    This method inputs a generated text and output a JSON of information tuples
    """
    out = []
    dict_str_list = _find_dict_strings(gen_text)
    for dict_str in dict_str_list:
        try:
            dict_obj = json.loads(dict_str)
            out.append(dict_obj)
        except json.JSONDecodeError:
            dict_obj = json_repair.repair_json(dict_str, skip_json_loads=True, return_objects=True)
            if dict_obj:
                warnings.warn(f'JSONDecodeError detected, fixed with repair_json:\n{dict_str}', RuntimeWarning)
                out.append(dict_obj)
            else:
                warnings.warn(f'JSONDecodeError could not be fixed:\n{dict_str}', RuntimeWarning)
    return out

def get_default_page_delimiter(output_mode:str) -> str:
    """ 
    Returns the default page delimiter based on the environment variable.

    Parameters:
    ----------
    output_mode : str
        The output mode, which can be "markdown", "HTML", or "text".
    
    Returns:
    -------
    str
        The default page delimiter.
    """
    if output_mode not in ["markdown", "HTML", "text", "JSON", "bbox"]:
        raise ValueError("output_mode must be 'markdown', 'HTML', 'text', 'JSON', or 'bbox'")

    if output_mode == "markdown":
        return "\n\n---\n\n"
    elif output_mode == "HTML":
        return "<br><br>"
    elif output_mode == "text":
        return "\n\n---\n\n"
    elif output_mode == "JSON":
        return "\n\n---\n\n"
    elif output_mode == "bbox":
        return "\n\n---\n\n"