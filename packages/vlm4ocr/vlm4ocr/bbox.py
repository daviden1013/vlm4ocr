import hashlib
import logging
from typing import List, Optional, Tuple

import json_repair
from PIL import Image, ImageDraw, ImageFont

from vlm4ocr.data_types import BBoxItem, BBoxFormat

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Format registry: per-VLM-family bbox conventions
# ---------------------------------------------------------------------------

# (substring_pattern, BBoxFormat) — longest match wins when the model name contains the pattern.
BBOX_FORMAT_REGISTRY: List[Tuple[str, BBoxFormat]] = [
    ("qwen3", BBoxFormat(
        coord_scale="normalized_1000",
        axis_order="x0y0x1y1",
        bbox_key="bbox_2d",
        label_key="label",
        text_key="text",
        system_prompt_file="ocr_bbox_system_prompt_qwen.txt",
    )),
    ("gemma-4", BBoxFormat(
        coord_scale="normalized_1000",
        axis_order="y0x0y1x1",
        bbox_key="box_2d",
        label_key="label",
        text_key="text",
        system_prompt_file="ocr_bbox_system_prompt_gemma.txt",
    )),
    ("gemma-3", BBoxFormat(
        coord_scale="normalized_1000",
        axis_order="y0x0y1x1",
        bbox_key="box_2d",
        label_key="label",
        text_key="text",
        system_prompt_file="ocr_bbox_system_prompt_gemma.txt",
    )),
    ("gpt-4.1", BBoxFormat(
        coord_scale="normalized_1000",
        axis_order="x0y0x1y1",
        bbox_key="bbox",
        label_key="label",
        text_key="text",
        system_prompt_file="ocr_bbox_system_prompt_default.txt",
    )),
]


def resolve_bbox_format(model_name: str) -> BBoxFormat:
    """
    Return the BBoxFormat for `model_name` by substring matching against the registry.
    Longest matching pattern wins. Falls back to default BBoxFormat() and logs a warning.
    """
    model_lower = model_name.lower()
    best_fmt: Optional[BBoxFormat] = None
    best_len = -1

    for pattern, fmt in BBOX_FORMAT_REGISTRY:
        if pattern.lower() in model_lower and len(pattern) > best_len:
            best_fmt = fmt
            best_len = len(pattern)

    if best_fmt is None:
        logger.warning(
            f"No bbox format registered for model '{model_name}'. "
            "Using default BBoxFormat (xyxy, auto scale)."
        )
        return BBoxFormat()

    logger.info(f"Resolved bbox format for '{model_name}': {best_fmt}")
    return best_fmt


def register_bbox_format(pattern: str, fmt: BBoxFormat) -> None:
    """Register a custom BBoxFormat at runtime without forking the package."""
    BBOX_FORMAT_REGISTRY.append((pattern, fmt))


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _detect_scale(coords: List[float]) -> str:
    """Heuristic: infer coordinate scale from the max value seen."""
    if not coords:
        return "normalized_1000"
    max_val = max(abs(c) for c in coords)
    if max_val <= 1.5:
        return "normalized_1"
    elif max_val <= 1024:
        return "normalized_1000"
    else:
        return "pixel"


def parse_bbox_response(
    raw_response: str,
    bbox_format: BBoxFormat,
    image_width: int,
    image_height: int,
) -> List[BBoxItem]:
    """
    Parse a raw VLM bbox response string into a canonical list of BBoxItem.

    Uses json_repair for tolerance. Applies axis swap, scale conversion, and
    clipping per the supplied BBoxFormat. Malformed items are dropped (not raised).
    """
    try:
        parsed = json_repair.loads(raw_response)
    except Exception:
        logger.warning("bbox post-processing: failed to parse response as JSON, returning []")
        return []

    if not isinstance(parsed, list):
        if isinstance(parsed, dict):
            parsed = [parsed]
        else:
            logger.warning("bbox post-processing: top-level JSON is not a list, returning []")
            return []

    if bbox_format.coord_scale == "auto":
        all_coords: List[float] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            raw_bbox = item.get(bbox_format.bbox_key)
            if isinstance(raw_bbox, list) and len(raw_bbox) >= 4:
                try:
                    all_coords.extend(float(c) for c in raw_bbox[:4])
                except (TypeError, ValueError):
                    pass
        scale = _detect_scale(all_coords)
    else:
        scale = bbox_format.coord_scale

    items: List[BBoxItem] = []
    dropped = 0

    for item in parsed:
        if not isinstance(item, dict):
            dropped += 1
            continue

        raw_bbox = item.get(bbox_format.bbox_key)
        text = item.get(bbox_format.text_key)
        label = item.get(bbox_format.label_key) or "word"

        if text is None:
            dropped += 1
            continue

        if not isinstance(raw_bbox, list) or len(raw_bbox) < 4:
            dropped += 1
            continue

        try:
            coords = [float(c) for c in raw_bbox[:4]]
        except (TypeError, ValueError):
            dropped += 1
            continue

        if bbox_format.axis_order == "y0x0y1x1":
            coords = [coords[1], coords[0], coords[3], coords[2]]

        if scale == "normalized_1000":
            coords[0] = coords[0] * image_width / 1000
            coords[1] = coords[1] * image_height / 1000
            coords[2] = coords[2] * image_width / 1000
            coords[3] = coords[3] * image_height / 1000
        elif scale == "normalized_1":
            coords[0] = coords[0] * image_width
            coords[1] = coords[1] * image_height
            coords[2] = coords[2] * image_width
            coords[3] = coords[3] * image_height

        x1 = max(0, min(int(coords[0]), image_width))
        y1 = max(0, min(int(coords[1]), image_height))
        x2 = max(0, min(int(coords[2]), image_width))
        y2 = max(0, min(int(coords[3]), image_height))

        items.append(BBoxItem(bbox=[x1, y1, x2, y2], label=str(label), text=str(text)))

    if dropped:
        logger.warning(f"bbox post-processing: dropped {dropped} malformed item(s)")

    return items


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def _color_for_label(label: str) -> Tuple[int, int, int]:
    """Deterministic RGB color from a label string (so repeated runs match)."""
    h = hashlib.md5(label.encode("utf-8")).digest()
    return (h[0] % 200, h[1] % 200, h[2] % 200)


def _load_font(font_path: Optional[str], font_size: int) -> ImageFont.ImageFont:
    if font_path:
        try:
            return ImageFont.truetype(font_path, size=font_size)
        except OSError:
            pass
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size=font_size)
        except OSError:
            continue
    return ImageFont.load_default()


def plot_bbox(
    bboxes: List[BBoxItem],
    image: Image.Image,
    show_label: bool = True,
    color_by_label: bool = True,
    box_width: int = 3,
    font_path: Optional[str] = None,
    font_size: int = 20,
) -> Image.Image:
    """
    Draw bounding boxes from a list of BBoxItem onto an image.

    `bboxes` must be in absolute pixel coordinates matching `image`'s dimensions
    (i.e. the post-resize image used during OCR — see `OCRResult.pages[i]['image_width']`
    and `image_height`).

    Parameters
    ----------
    bboxes : List[BBoxItem]
        Bounding box records as produced by OCREngine in bbox output mode.
    image : PIL.Image.Image
        The image to draw on. The original is not modified; a copy is returned.
    show_label : bool, default True
        Draw each box's label as a tag above the box.
    color_by_label : bool, default True
        Color each box deterministically by its label so distinct categories are
        visually separable. If False, all boxes are red.
    box_width : int, default 3
        Outline thickness in pixels.
    font_path : str | None
        Path to a TTF font for label text. Falls back to a common system font,
        then to PIL's default bitmap font.
    font_size : int, default 20

    Returns
    -------
    PIL.Image.Image
        A copy of `image` with the boxes (and optional labels) drawn on it.
    """
    out = image.copy()
    draw = ImageDraw.Draw(out)
    font = _load_font(font_path, font_size) if show_label else None

    for item in bboxes:
        try:
            x1, y1, x2, y2 = item.bbox
            label = item.label or ""
        except (TypeError, ValueError, AttributeError):
            continue

        color = _color_for_label(label) if color_by_label else "red"
        draw.rectangle([x1, y1, x2, y2], outline=color, width=box_width)

        if show_label and label:
            tb = draw.textbbox((x1, y1), label, font=font)
            text_w = tb[2] - tb[0]
            text_h = tb[3] - tb[1]
            label_y0 = max(y1 - text_h - 4, 0)
            draw.rectangle([x1, label_y0, x1 + text_w + 4, y1], fill=color)
            draw.text((x1 + 2, label_y0), label, fill="white", font=font)

    return out
