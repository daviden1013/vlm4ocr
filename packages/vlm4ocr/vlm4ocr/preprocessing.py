import re
import asyncio
import importlib.util
import importlib.resources
import warnings
from typing import Tuple, Literal, Optional, TYPE_CHECKING
from PIL import Image

if TYPE_CHECKING:
    from vlm4ocr.vlm_engines import VLMEngine


RotateCorrectionMethod = Literal["tesseract", "vlm"]


def _normalize_mode(image: Image.Image, for_resample: bool = False) -> Image.Image:
    """
    Convert an image to a mode that can be resampled with a filter and encoded as PNG.

    Pillow silently falls back to nearest-neighbor when resizing "1" and "P" images,
    filters palette indices (not colors) for "PA", and cannot save several modes
    (CMYK, YCbCr, LAB, HSV, RGBX, F, I;16B, ...) as PNG.

    Parameters:
    ----------
    image : Image.Image
        The image to normalize.
    for_resample : bool, Optional
        If True, also convert "1" and "P" (which PNG stores natively but Pillow cannot
        resample with a filter). If False, those modes are kept to keep the payload small.

    Returns:
    -------
    Image.Image
        The image in "L", "LA", "RGB" or "RGBA" mode (or unchanged "1"/"P" when
        for_resample is False). The input image is returned as-is if no conversion is needed.
    """
    mode = image.mode
    if mode in ("L", "LA", "RGB", "RGBA"):
        return image
    if mode in ("1", "P") and not for_resample:
        return image
    if mode == "1":
        return image.convert("L")
    if mode in ("P", "PA"):
        has_alpha = mode == "PA" or "transparency" in image.info
        return image.convert("RGBA" if has_alpha else "RGB")
    if mode.startswith("I") or mode == "F":
        # High bit depth grayscale. convert("L") clips instead of scaling, so stretch the
        # actual value range to 0-255 (also handles 12-bit data stored in 16 bits).
        image = image.convert("F")
        low, high = image.getextrema()
        if high > low:
            image = image.point(lambda v: (v - low) * (255.0 / (high - low)))
        return image.convert("L")
    if mode == "La":
        return image.convert("LA")
    if mode == "RGBa":
        return image.convert("RGBA")
    return image.convert("RGB")


class ImageProcessor:
    def __init__(self, vlm_engine: Optional["VLMEngine"] = None,
                 resample: Image.Resampling = Image.Resampling.LANCZOS,
                 reducing_gap: Optional[float] = 3.0,
                 orientation_max_dimension_pixels: Optional[int] = 1024):
        """
        Image preprocessing utilities for OCR: rotation correction and resizing.

        Parameters:
        ----------
        vlm_engine : VLMEngine, Optional
            Required only when rotation correction is performed via method="vlm".
        resample : Image.Resampling, Optional
            Resampling filter used by resize. Defaults to LANCZOS.
        reducing_gap : float, Optional
            Passed to Pillow's Image.resize. Speeds up large downscales by first reducing the
            image by an integer factor; values >= 3.0 are visually indistinguishable from
            plain resampling. None disables it.
        orientation_max_dimension_pixels : int, Optional
            For rotation correction with method="vlm", the image sent to the VLM is first
            downscaled to fit within this dimension. The detected rotation is applied to the
            full-size image. None sends the full-size image.
        """
        self.has_tesseract = importlib.util.find_spec("pytesseract") is not None
        self.vlm_engine = vlm_engine
        self.resample = resample
        self.reducing_gap = reducing_gap
        self.orientation_max_dimension_pixels = orientation_max_dimension_pixels
        self._orientation_system_prompt: Optional[str] = None

    def _load_orientation_prompt(self) -> str:
        if self._orientation_system_prompt is None:
            prompt_path = importlib.resources.files('vlm4ocr.assets.default_prompt_templates').joinpath('orientation_system_prompt.txt')
            with prompt_path.open('r', encoding='utf-8') as f:
                self._orientation_system_prompt = f.read()
        return self._orientation_system_prompt

    @staticmethod
    def _parse_angle(response_text: str) -> Optional[int]:
        """
        Extract the first integer found in the VLM response and normalize to [0, 360).
        Returns None if no integer is present.
        """
        match = re.search(r"\d+", response_text)
        if match is None:
            return None
        angle = int(match.group(0)) % 360
        return angle

    def rotate_correction(self, image: Image.Image, method: RotateCorrectionMethod = "tesseract") -> Tuple[Image.Image, int]:
        """
        Correct the rotation of an image.

        Parameters:
        ----------
        image : Image.Image
            The image to be corrected.
        method : {"tesseract", "vlm"}
            "tesseract" uses pytesseract OSD. "vlm" prompts the configured VLM engine.

        Returns:
        -------
        Tuple[Image.Image, int]
            The corrected image and the rotation angle applied (degrees).
        """
        if method == "tesseract":
            return self._rotate_correction_tesseract_osd(image)
        if method == "vlm":
            return self._rotate_correction_vlm(image)
        raise ValueError(f"Unknown rotate_correction method: {method!r}. Must be 'tesseract' or 'vlm'.")

    async def rotate_correction_async(self, image: Image.Image, method: RotateCorrectionMethod = "tesseract") -> Tuple[Image.Image, int]:
        """
        Asynchronous version of rotate_correction.
        """
        if method == "tesseract":
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._rotate_correction_tesseract_osd, image)
        if method == "vlm":
            return await self._rotate_correction_vlm_async(image)
        raise ValueError(f"Unknown rotate_correction method: {method!r}. Must be 'tesseract' or 'vlm'.")

    def _rotate_correction_tesseract_osd(self, image: Image.Image) -> Tuple[Image.Image, int]:
        """
        Use Tesseract OSD to detect and correct the rotation.
        """
        if importlib.util.find_spec("pytesseract") is None:
            raise ImportError("pytesseract is not installed. Please install it to use this feature.")

        import pytesseract

        try:
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
            rotation_angle = osd['rotate']
            if rotation_angle != 0:
                return image.rotate(rotation_angle, expand=True), rotation_angle
            return image, 0
        except Exception as e:
            print(f"Error correcting image rotation: {e}")
            raise ValueError(f"Failed to correct image rotation: {e}") from e

    def _rotate_correction_vlm(self, image: Image.Image) -> Tuple[Image.Image, int]:
        """
        Prompt the configured VLM engine to detect orientation and rotate accordingly.
        """
        if self.vlm_engine is None:
            raise ValueError("vlm_engine is required for rotate_correction method='vlm'.")

        probe = image
        if self.orientation_max_dimension_pixels is not None:
            probe, _ = self.resize(image, max_dimension_pixels=self.orientation_max_dimension_pixels)

        system_prompt = self._load_orientation_prompt()
        messages = self.vlm_engine.get_ocr_messages(
            system_prompt=system_prompt,
            user_prompt=None,
            image=probe,
        )
        response = self.vlm_engine.chat(messages)
        return self._apply_vlm_response(image, response.get("response", ""))

    async def _rotate_correction_vlm_async(self, image: Image.Image) -> Tuple[Image.Image, int]:
        if self.vlm_engine is None:
            raise ValueError("vlm_engine is required for rotate_correction method='vlm'.")

        probe = image
        if self.orientation_max_dimension_pixels is not None:
            probe, _ = await self.resize_async(image, max_dimension_pixels=self.orientation_max_dimension_pixels)

        system_prompt = self._load_orientation_prompt()
        messages = self.vlm_engine.get_ocr_messages(
            system_prompt=system_prompt,
            user_prompt=None,
            image=probe,
        )
        response = await self.vlm_engine.chat_async(messages)
        return self._apply_vlm_response(image, response.get("response", ""))

    def _apply_vlm_response(self, image: Image.Image, response_text: str) -> Tuple[Image.Image, int]:
        angle = self._parse_angle(response_text)
        if angle is None:
            warnings.warn(
                f"VLM orientation response contained no integer angle; skipping rotation. Response: {response_text!r}"
            )
            return image, 0
        if angle == 0:
            return image, 0
        return image.rotate(angle, expand=True), angle

    def resize(self, image: Image.Image, max_dimension_pixels: int = 4000) -> Tuple[Image.Image, bool]:
        """
        Resize the image to fit within the specified maximum dimension while maintaining aspect ratio.
        Images are only shrunk, never enlarged. Modes that Pillow cannot resample with a filter
        ("1", "P", ...) are converted first (see _normalize_mode).
        """
        width, height = image.size
        if width > max_dimension_pixels or height > max_dimension_pixels:
            if width > height:
                new_width = max_dimension_pixels
                new_height = max(1, round((max_dimension_pixels / width) * height))
            else:
                new_height = max_dimension_pixels
                new_width = max(1, round((max_dimension_pixels / height) * width))
            image = _normalize_mode(image, for_resample=True)
            return image.resize((new_width, new_height), resample=self.resample, reducing_gap=self.reducing_gap), True

        return image, False

    async def resize_async(self, image: Image.Image, max_dimension_pixels: int = 4000) -> Tuple[Image.Image, bool]:
        """
        Asynchronous version of resize.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.resize, image, max_dimension_pixels)
