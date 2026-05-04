import os
from typing import List, Dict, Literal, Optional, Union, TYPE_CHECKING
from PIL import Image
from dataclasses import dataclass, field
from vlm4ocr.utils import get_default_page_delimiter
from vlm4ocr.preprocessing import ImageProcessor, RotateCorrectionMethod

if TYPE_CHECKING:
    from vlm4ocr.vlm_engines import VLMEngine

OutputMode = Literal["markdown", "HTML", "text", "JSON", "bbox"]


@dataclass
class BBoxItem:
    """A single detected region with its bounding box, label, and text."""
    bbox: List[int]   # [x1, y1, x2, y2] absolute pixels
    label: str
    text: str


@dataclass
class BBoxFormat:
    """Describes how a specific VLM family encodes bbox output."""
    coord_scale: Literal["normalized_1000", "auto"] = "auto"
    axis_order: Literal["x0y0x1y1", "y0x0y1x1"] = "x0y0x1y1"
    bbox_key: str = "bbox"
    label_key: str = "label"
    text_key: str = "text"
    system_prompt_file: str = "ocr_bbox_system_prompt_default.txt"


@dataclass
class OCRResult:
    """
    This class represents the result of an OCR process.

    Parameters:
    ----------
    input_dir : str
        The directory where the input files (e.g., image, PDF, tiff) are located.
    output_mode : str
        The output format. Must be 'markdown', 'HTML', or 'text'.
    pages : List[str]
        A list of strings, each representing a page of the OCR result.
    """
    input_dir: str
    output_mode: OutputMode
    pages: List[dict] = field(default_factory=list)
    filename: str = field(init=False)
    status: str = field(init=False, default="processing")
    messages_log: List[List[Dict[str,str]]] = field(default_factory=list)

    def __post_init__(self):
        """
        Called after the dataclass-generated __init__ method.
        Used for validation and initializing derived fields.
        """
        self.filename = os.path.basename(self.input_dir)

        # output_mode validation
        if self.output_mode not in ["markdown", "HTML", "text", "JSON", "bbox"]:
            raise ValueError("output_mode must be 'markdown', 'HTML', 'text', 'JSON', or 'bbox'")

        # pages validation 
        if not isinstance(self.pages, list):
            raise ValueError("pages must be a list of dict")
        for i, page_content in enumerate(self.pages):
            if not isinstance(page_content, dict):
                raise ValueError(f"Each page must be a dict. Page at index {i} is not a dict.")


    def add_page(self, text: str, image_processing_status: dict,
                 bboxes: Optional[List["BBoxItem"]] = None,
                 image_width: Optional[int] = None,
                 image_height: Optional[int] = None):
        """
        This method adds a new page to the OCRResult object.

        Parameters:
        ----------
        text : str
            The OCR result text of the page.
        image_processing_status : dict
            A dictionary containing the image processing status for the page.
        bboxes : List[BBoxItem] | None, Optional
            Parsed bounding-box records (populated in bbox output mode).
        image_width : int | None, Optional
            Width of the post-resize image (pixels), populated in bbox mode.
        image_height : int | None, Optional
            Height of the post-resize image (pixels), populated in bbox mode.
        """
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        if not isinstance(image_processing_status, dict):
            raise ValueError("image_processing_status must be a dict")

        page = {
            "text": text,
            "image_processing_status": image_processing_status,
            "bboxes": bboxes,
            "image_width": image_width,
            "image_height": image_height,
        }
        self.pages.append(page)

    def get_page(self, idx):
        if not isinstance(idx, int):
            raise ValueError("Index must be an integer")
        if idx < 0 or idx >= len(self.pages):
            raise IndexError(f"Index out of range. The OCRResult has {len(self.pages)} pages, but index {idx} was requested.")
        
        return self.pages[idx]

    def clear_messages_log(self):
        self.messages_log = []

    def add_messages_to_log(self, messages: List[Dict[str,str]]):
        if not isinstance(messages, list):
            raise ValueError("messages must be a list of dict")
        
        self.messages_log.extend(messages)

    def get_messages_log(self) -> List[List[Dict[str,str]]]:
        return self.messages_log.copy()

    def __len__(self):
        return len(self.pages)
    
    def __iter__(self):
        return iter(self.pages)
    
    def __repr__(self):
        return f"OCRResult(filename={self.filename}, output_mode={self.output_mode}, pages_count={len(self.pages)}, status={self.status})"
    
    def to_string(self, page_delimiter:str="auto") -> str:
        """
        Convert the OCRResult object to a string representation.

        Parameters:
        ----------
        page_delimiter : str, Optional
            Only applies if separate_pages = True. The delimiter to use between PDF pages. 
            if 'auto', it will be set to the default page delimiter for the output mode: 
            'markdown' -> '\n\n---\n\n'
            'HTML' -> '<br><br>'
            'text' -> '\n\n---\n\n'
        """
        if not isinstance(page_delimiter, str):
            raise ValueError("page_delimiter must be a string")
        
        if page_delimiter == "auto":
            self.page_delimiter = get_default_page_delimiter(self.output_mode)
        else:
            self.page_delimiter = page_delimiter

        return self.page_delimiter.join([page.get("text", "") for page in self.pages])

    def get_bboxes(self, page_idx: int) -> Optional[List["BBoxItem"]]:
        """Returns the parsed bbox records for a given page, or None."""
        return self.get_page(page_idx).get("bboxes")

    def plot_bboxes(self, page_idx: int, **kwargs) -> Image.Image:
        """
        Render the source page image with this page's bboxes drawn on top.

        Reloads the source file, re-applies the rotation used during OCR (if any),
        and resizes to the dimensions sent to the VLM. Then calls the standalone
        `vlm4ocr.plot_bbox` to draw the boxes.

        Parameters
        ----------
        page_idx : int
            Page index in this result.
        **kwargs
            Forwarded to `vlm4ocr.plot_bbox` (e.g. show_label, color_by_label,
            box_width, font_path, font_size).

        Returns
        -------
        PIL.Image.Image
            A copy of the source page with bboxes drawn on it.
        """
        page = self.get_page(page_idx)
        bboxes = page.get("bboxes")
        if bboxes is None:
            raise ValueError(
                f"Page {page_idx} has no bboxes. plot_bbox is only available for "
                "OCRResult produced with output_mode='bbox'."
            )

        # Lazy imports to avoid circular dependency
        from vlm4ocr.utils import PDFDataLoader, TIFFDataLoader, ImageDataLoader
        from vlm4ocr.bbox import plot_bbox as _plot_bbox

        file_ext = os.path.splitext(self.input_dir)[1].lower()
        if file_ext == ".pdf":
            loader = PDFDataLoader(self.input_dir)
        elif file_ext in (".tif", ".tiff"):
            loader = TIFFDataLoader(self.input_dir)
        else:
            loader = ImageDataLoader(self.input_dir)
        image = loader.get_page(page_idx)

        # Re-apply rotation that was used during OCR (same convention as ImageProcessor)
        rot_status = page.get("image_processing_status", {}).get("rotate_correction")
        if rot_status and rot_status.get("status") == "success":
            angle = rot_status.get("rotation_angle") or 0
            if angle:
                image = image.rotate(angle, expand=True)

        # Resize to match the post-resize image the VLM saw
        target_w = page.get("image_width")
        target_h = page.get("image_height")
        if target_w and target_h and image.size != (target_w, target_h):
            image = image.resize((target_w, target_h), Image.LANCZOS)

        return _plot_bbox(bboxes, image, **kwargs)
    
@dataclass
class FewShotExample:
    """
    This class represents a few-shot example for OCR tasks.

    Parameters:
    ----------
    image : PIL.Image.Image
        The image associated with the example.
    text : str
        The expected OCR result text for the image.
    rotate_correction : {"tesseract", "vlm", False}, Optional
        Rotation correction method applied at construction time. "tesseract" uses pytesseract OSD;
        "vlm" prompts the provided vlm_engine. False disables correction.
    vlm_engine : VLMEngine, Optional
        Required when rotate_correction="vlm".
    max_dimension_pixels : int, Optional
        The maximum dimension of the image in pixels. Original dimensions will be resized to fit in. If None, no resizing is applied.
    """
    image: Image.Image
    text: str
    rotate_correction: Union[RotateCorrectionMethod, Literal[False]] = False
    vlm_engine: Optional["VLMEngine"] = None
    max_dimension_pixels: int = None
    def __post_init__(self):
        if not isinstance(self.image, Image.Image):
            raise ValueError("image must be a PIL.Image.Image object")
        if not isinstance(self.text, str):
            raise ValueError("text must be a string")

        if self.rotate_correction == "vlm" and self.vlm_engine is None:
            raise ValueError("vlm_engine is required when rotate_correction='vlm'.")

        if self.rotate_correction or self.max_dimension_pixels is not None:
            self.image_processor = ImageProcessor(vlm_engine=self.vlm_engine)

        # Rotate correction if specified
        if self.rotate_correction:
            self.image, _ = self.image_processor.rotate_correction(self.image, method=self.rotate_correction)

        # Resize image if max_dimension_pixels is specified
        if self.max_dimension_pixels is not None:
            self.image, _ = self.image_processor.resize(image=self.image, max_dimension_pixels=self.max_dimension_pixels)
