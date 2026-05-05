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


_OCR_PAGE_KEYS = ("text", "image_processing_status", "bboxes", "image_width", "image_height")


@dataclass
class OCRPage:
    """
    Holds all data for a single OCR-processed page.

    Attributes are the canonical access pattern. Dict-style access
    (page["text"], page.get("bboxes")) is supported for backward compatibility.
    """
    text: str
    image_processing_status: dict
    bboxes: Optional[List["BBoxItem"]] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    # Internal fields set by OCRResult.add_page — not part of public API
    _source_path: str = field(default="", repr=False)
    _page_idx: int = field(default=0, repr=False)

    def __repr__(self):
        return f"OCRPage(page_idx={self._page_idx}, text_length={len(self.text)})"

    # --- dict-style compat ---

    def __getitem__(self, key: str):
        if key not in _OCR_PAGE_KEYS:
            raise KeyError(key)
        return getattr(self, key)

    def get(self, key: str, default=None):
        if key not in _OCR_PAGE_KEYS:
            return default
        return getattr(self, key)

    def __contains__(self, key: str):
        return key in _OCR_PAGE_KEYS

    def keys(self):
        return _OCR_PAGE_KEYS

    # --- bbox methods ---

    def get_bboxes(self) -> Optional[List["BBoxItem"]]:
        """Returns the parsed bbox records for this page, or None."""
        return self.bboxes

    def plot_bboxes(
        self,
        show_label: bool = True,
        show_text: bool = False,
        color: str = "label",
        box_width: int = 3,
        font_path: Optional[str] = None,
        font_size: int = 20,
    ) -> Image.Image:
        """
        Render this page's source image with bboxes drawn on top.

        Reloads the source file, re-applies the rotation used during OCR (if any),
        and resizes to the dimensions sent to the VLM. When the source image is
        downscaled, `box_width` and `font_size` are scaled by the same factor so
        the outlines and labels stay visually proportional to the page content.

        Parameters
        ----------
        show_label : bool, default True
            Draw each box's label as a tag above the box.
        show_text : bool, default False
            Draw each box's OCR text (italic) in the tag above the box. When
            both show_label and show_text are True the tag reads "label; text"
            with the label in bold and the text in italic.
        color : "label" | "random" | str, default "label"
            Box color strategy. "label" assigns a deterministic color per label.
            "random" picks a random color per box. Any other string is treated as
            a PIL color (name or hex, e.g. "red", "#E63946") for all boxes.
        box_width : int, default 3
            Outline thickness in pixels, specified at original image scale. Scaled
            down automatically if the image was resized for OCR.
        font_path : str | None, Optional
            Path to a TTF font for label text. Falls back to a common system font,
            then to PIL's default bitmap font.
        font_size : int, default 20
            Label font size in pixels, specified at original image scale. Scaled
            down automatically if the image was resized for OCR.

        Returns
        -------
        PIL.Image.Image
            A copy of the source page with bboxes drawn on it.
        """
        if self.bboxes is None:
            raise ValueError(
                f"Page {self._page_idx} has no bboxes. plot_bboxes is only available for "
                "OCRResult produced with output_mode='bbox'."
            )

        from vlm4ocr.utils import PDFDataLoader, TIFFDataLoader, ImageDataLoader
        from vlm4ocr.bbox import plot_bbox as _plot_bbox

        file_ext = os.path.splitext(self._source_path)[1].lower()
        if file_ext == ".pdf":
            loader = PDFDataLoader(self._source_path)
        elif file_ext in (".tif", ".tiff"):
            loader = TIFFDataLoader(self._source_path)
        else:
            loader = ImageDataLoader(self._source_path)
        image = loader.get_page(self._page_idx)

        rot_status = self.image_processing_status.get("rotate_correction")
        if rot_status and rot_status.get("status") == "success":
            angle = rot_status.get("rotation_angle") or 0
            if angle:
                image = image.rotate(angle, expand=True)

        resize_status = self.image_processing_status.get("resize")
        if (resize_status and resize_status.get("status") == "success"
                and resize_status.get("resized") and self.image_width and self.image_height):
            image_processor = ImageProcessor()
            original_w = image.size[0]
            image, _ = image_processor.resize(
                image, max_dimension_pixels=max(self.image_width, self.image_height)
            )
            scale = image.size[0] / original_w
            box_width = max(1, int(round(box_width * scale)))
            font_size = max(6, int(round(font_size * scale)))

        return _plot_bbox(
            self.bboxes,
            image,
            show_label=show_label,
            show_text=show_text,
            color=color,
            box_width=box_width,
            font_path=font_path,
            font_size=font_size,
        )


@dataclass
class OCRResult:
    """
    This class represents the result of an OCR process.

    Parameters:
    ----------
    input_dir : str
        The directory where the input files (e.g., image, PDF, tiff) are located.
    output_mode : str
        The output format. Must be 'markdown', 'HTML', 'text', 'JSON', or 'bbox'.
    """
    input_dir: str
    output_mode: OutputMode
    pages: List[OCRPage] = field(default_factory=list)
    filename: str = field(init=False)
    status: str = field(init=False, default="processing")
    messages_log: List[List[Dict[str,str]]] = field(default_factory=list)

    def __post_init__(self):
        self.filename = os.path.basename(self.input_dir)

        if self.output_mode not in ["markdown", "HTML", "text", "JSON", "bbox"]:
            raise ValueError("output_mode must be 'markdown', 'HTML', 'text', 'JSON', or 'bbox'")

    def add_page(self, text: str, image_processing_status: dict,
                 bboxes: Optional[List["BBoxItem"]] = None,
                 image_width: Optional[int] = None,
                 image_height: Optional[int] = None):
        """
        Adds a new page to the OCRResult. Internal method called by OCR engines.

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

        page = OCRPage(
            text=text,
            image_processing_status=image_processing_status,
            bboxes=bboxes,
            image_width=image_width,
            image_height=image_height,
            _source_path=self.input_dir,
            _page_idx=len(self.pages),
        )
        self.pages.append(page)

    def get_page(self, idx: int) -> OCRPage:
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

    def to_string(self, page_delimiter: str = "auto") -> str:
        """
        Convert the OCRResult object to a string representation.

        Parameters:
        ----------
        page_delimiter : str, Optional
            The delimiter to use between pages. If 'auto', defaults by output mode:
            'markdown' / 'text' -> '\\n\\n---\\n\\n', 'HTML' -> '<br><br>'
        """
        if not isinstance(page_delimiter, str):
            raise ValueError("page_delimiter must be a string")

        if page_delimiter == "auto":
            self.page_delimiter = get_default_page_delimiter(self.output_mode)
        else:
            self.page_delimiter = page_delimiter

        return self.page_delimiter.join([page.text for page in self.pages])

    
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
