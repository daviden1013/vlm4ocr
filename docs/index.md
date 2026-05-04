# VLM4OCR

*vlm4ocr* is a toolkit for Optical character recognition (OCR) with Vision language models (VLMs). In includes three components:

- [Web Application](./web_application.md) for drag-and-drop access
- [CLI](./cli.md) for command line access
- [Python package](./quick_start.md) for Python access

## What's new in v0.5.0

- **BBox output mode** — `OCREngine(output_mode="bbox", ...)` returns text with bounding-box coordinates and labels. Leave `user_prompt` empty for full-text bbox OCR or set it to a free-text instruction (e.g., `"patient name and DOB"`) for targeted extraction. Built-in format registry covers Qwen3-VL, Gemma 3/4, and GPT-4.1. See [Quick Start](./quick_start.md#ocr-with-bounding-boxes).
- **Web app — BBox tab** — visualize bounding boxes directly in the browser with an *Image | Raw response* toggle. Batch mode emits annotated PNGs and a consolidated JSON per file.
- **`OCRPage` dataclass** — `OCRResult.pages` entries are now `OCRPage` dataclasses with `.text`, `.bboxes`, `.image_width`, `.image_height`, and a `.plot_bboxes()` helper. Dict-style access still works.