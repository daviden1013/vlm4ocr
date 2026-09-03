![Python Version](https://img.shields.io/pypi/pyversions/vlm4ocr)
![PyPI](https://img.shields.io/pypi/v/vlm4ocr)
[![Website](https://img.shields.io/badge/website-GitHub.io-purple)](https://daviden1013.github.io/vlm4ocr/)

Vision Language Models (VLMs) for Optical Character Recognition (OCR).

| Feature                 | Support                                                                 |
| :---------------------- | :---------------------------------------------------------------------- |
| **File Types** | :white_check_mark: PDF, TIFF, PNG, JPG/JPEG, BMP, GIF, WEBP         |
| **VLM Engines** | :white_check_mark: Ollama, OpenAI Compatible (vLLM, SGLang, OpenRouter), OpenAI, Azure OpenAI |
| **Output Modes** | :white_check_mark: Markdown, HTML, plain text, JSON, BBox |
| **Batch OCR** | :white_check_mark: Processes many files concurrently with Python, CLI, and web app |
| **Pipelines** | :white_check_mark: Per-page routing for heterogeneous documents (`IndependentPagePipeline`) |

## 🆕Recent Updates
- [v0.2.0](https://github.com/daviden1013/vlm4ocr/releases/tag/v0.2.0) (Jun 1, 2025): 
  - 📐**User Guide** is now available at [Documentation Page](https://daviden1013.github.io/vlm4ocr/)
  - **Image processing features**: added `rotate_correction` and `max_dimension_pixels` to handle misaligned scan and large images. 
  - **Optimized file staging**: added `max_file_load` parameter to `concurrent_ocr` method. 
- [v0.3.0](https://github.com/daviden1013/vlm4ocr/releases/tag/v0.3.0) (Jul 5, 2025): 
  - **Key information extraction with JSON**: instead of OCR the entire document, extract only the key information and output as JSON.
  - **Batch processing to web app**: The web app now supports concurrent batch processing of multiple images using `OCREngine.concurrent_ocr` method as backend. 
- [v0.3.1](https://github.com/daviden1013/vlm4ocr/releases/tag/v0.3.1) (Oct 11, 2025):
  - **Added reasoning VLM supports**: Added new configs to support reasoning VLMs (e.g., Qwen-VL-30B-A3B-Thinking, o4-mini). 
  - **Added OpenAICompatible VLM engines**: Separated the OpenAI compatible VLM engines into a parent class `OpenAICompatibleVLMEngine`.
- [v0.4.0](https://github.com/daviden1013/vlm4ocr/releases/tag/v0.4.0) (Dec 15, 2025):
  - **Few-shot examples**: Added support for few-shot examples to improve OCR accuracy.
- [v0.4.3](https://github.com/daviden1013/vlm4ocr/releases/tag/v0.4.3):
  - **SGLang support**: Added `SGLangVLMEngine` for serving VLMs with SGLang.
- [v0.4.4](https://github.com/daviden1013/vlm4ocr/releases/tag/v0.4.4):
  - **VLM-based rotation correction**: `rotate_correction` now accepts `"tesseract"`, `"vlm"`, or `False`. Use `"vlm"` when Tesseract isn't installed or struggles with noisy scans.
- [v0.5.0](https://github.com/daviden1013/vlm4ocr/releases/tag/v0.5.0) (May 4, 2026):
  - **BBox output mode**: New `output_mode="bbox"` returns OCR text with bounding-box coordinates and labels per region. Leave `user_prompt` empty for full-text bbox OCR or set it to a free-text instruction (e.g., `"patient name and DOB"`) for targeted extraction. Built-in format registry covers Qwen3-VL, Gemma 3/4, and GPT-4.1.
- [v0.6.0](https://github.com/daviden1013/vlm4ocr/releases/tag/v0.6.0) (Jul 10, 2026):
  - **OCR pipelines**: New `IndependentPagePipeline` + `OCREngine.ocr_image_async` let you process each page differently — classify and route the pages of a **heterogeneous document** (e.g., mixed form types in one PDF) to different prompts/schemas, while the pipeline handles loading, concurrency, and assembly. See the [OCR Pipelines guide](https://daviden1013.github.io/vlm4ocr/ocr_pipelines/).

## Table of Contents
- [Overview](#overview)
- [Supported Models](#supported-models)
- [Prerequisites](#prerequisites)
- [Web Application](#web-application)
- [Python package](#python-package)
- [CLI](#cli)

## ✨Overview
`vlm4ocr` provides a simple way to perform OCR using the power of modern Vision Language Models (VLMs). A drag-and-drop **web application** is included for easy access. The **Python package** supports concurrent batch processing for large amount of documents. **CLI** provides lightweight access to most OCR features without the burden of coding. 
Below are screenshots from our [Web Application](#web-application). Note that all contents shown in this README are synthesized. **There is no real personal information**.

#### Stream OCR resuts in real-time
A scanned lab report with tables and highlights are converted into markdown text by our OCR engine.
<div align="center"><img src=docs/readme_img/web_app/table_markdown_demo.PNG width=1000 ></div>

#### Batch processing many files
Many scanned documents are batch processed and converted into markdown text by our OCR engine. 
<div align="center"><img src=docs/readme_img/web_app/batch_processing.PNG width=1000 ></div>

## ⭐Supported Models 
### Open-weights (ALL Supported!!)
**All open-weights VLMs are supported** via our [Ollama](/packages/vlm4ocr/vlm4ocr/vlm_engines.py) and [OpenAI compatible engines](/packages/vlm4ocr/vlm4ocr/vlm_engines.py), including:
- [Qwen3-VL](https://huggingface.co/collections/Qwen/qwen3-vl-68d2a7c1b8a8afce4ebd2dbe)
- [Qwen2.5-VL](https://huggingface.co/collections/Qwen/qwen25-vl-6795ffac22b334a837c0f9a5)
- [Llama-3.2](https://huggingface.co/collections/meta-llama/llama-32-66f448ffc8c32f949b04c8cf)
- [LLaVa-1.5](https://huggingface.co/collections/llava-hf/llava-15-65f762d5b6941db5c2ba07e0)

### Proprietary 
Proprietary models such as gpt-4o are supported via our [OpenAI](/packages/vlm4ocr/vlm4ocr/vlm_engines.py) and [Azure](/packages/vlm4ocr/vlm4ocr/vlm_engines.py) engines.


## 🚦Prerequisites
- Python 3.x
- At least one VLM inference engine setup (Ollama, OpenAI/Azure API keys, or an OpenAI-compatible API endpoint).

```bash
pip install ollama # For Ollama
pip install openai # For OpenAI (compatible) and Azure OpenAI
```

### PDF support
vlm4ocr does not install a PDF library. If you process PDFs, pick a rendering backend,
install it, and name it with `pdf_backend` (`--pdf_backend` on the CLI). If you only
process images and TIFFs, install nothing extra. There is no default and no automatic
fallback: the backend you name is the backend that is used.

| Backend | Renderer | License | Notes |
| --- | --- | --- | --- |
| `pypdfium2` | PDFium | Apache-2.0 / BSD-3 | Recommended. Permissive, wheel-only, no system binary. |
| `pdf2image` | poppler | MIT wrapper, **GPL** poppler binary | Requires installing `poppler-utils` separately. |
| `pymupdf` | MuPDF | **AGPL-3.0** | Most tolerant of damaged PDFs. Review the license before commercial use. |

```bash
pip install vlm4ocr[pypdfium2]   # recommended
pip install vlm4ocr[pdf2image]   # also needs the poppler system package
pip install vlm4ocr[pymupdf]     # AGPL-3.0
```

```python
ocr_engine = OCREngine(vlm_engine=vlm_engine, pdf_backend="pypdfium2")
```

If a PDF is passed without a backend, vlm4ocr raises `PDFBackendNotAvailableError` naming
the options rather than guessing.

## 🌎Web Application
A ready-to-use Flask web application is included. We support input preview, real-time streaming, and output export. 

https://github.com/user-attachments/assets/b196453c-fd2c-491a-ba1e-0a77cf7f5941

### Installation
#### :whale:Running with Docker
The easiest way to run VLM4OCR web application is through [Docker](https://docs.docker.com/get-started/get-docker/). The image is available on Docker Hub.
```sh
docker pull daviden1013/vlm4ocr-app:latest
docker run -p 5000:5000 daviden1013/vlm4ocr-app:latest
```
Open your web browser and navigate to:
http://localhost:5000

If port 5000 is already in use on your machine, you can map it to a different local port. For example, to map it to local port 8080:
```sh
docker run -p 8080:5000 daviden1013/vlm4ocr-app:latest
```
Then visit http://localhost:8080

##### Using Ollama with the Dockerized App
If you are running Ollama on your host machine (outside the Docker container) and want to connect to it from the VLM4OCR web app running inside Docker:

**Docker Desktop (Windows/Mac):** In the VLM4OCR web UI, set the Ollama Host to http://host.docker.internal:11434.
**Linux:** Run the Docker container with host networking:
```sh
docker run --network="host" daviden1013/vlm4ocr-app:latest
```
With `--network="host"`, you don't need the `-p` flag for port mapping (the container will use the host's network directly, so the app will be available at http://localhost:5000). Then, in the VLM4OCR web app, you can use the default http://localhost:11434 for the Ollama Host.

#### Install from source
Alternatively, you can clone this repo and run VLM4OCR web application from source:
```bash
# Install python package
pip install vlm4ocr 

# Clone source code
git clone https://github.com/daviden1013/vlm4ocr.git

# Run Web App
cd vlm4ocr/services/web_app
python run.py
```


## 🐍Python package
### Installation

Python package is available on PyPi
```bash
pip install vlm4ocr
```

### Quick start
In this demo, we use a locally deployed [vLLM OpenAI compatible server](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) to run [Qwen3-VL-30B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-30B-A3B-Instruct) model. 

```python
from vlm4ocr import VLLMVLMEngine

vlm_engine = VLLMVLMEngine(model="Qwen/Qwen3-VL-30B-A3B-Instruct")
```

To use other VLM inference engines:
<details>
<summary> OpenAI Compatible</summary>

```python
from vlm4ocr import OpenAICompatibleVLMEngine

vlm_engine = OpenAICompatibleVLMEngine(model="<mode_name>", base_url="<base_url>", api_key="<api_key>")
```
</details>

<details>
<summary> <img src="docs/readme_img/ollama_icon.png" alt="Icon" width="22"/> Ollama</summary>

```python
from vlm4ocr import OllamaVLMEngine

vlm_engine = OllamaVLMEngine(model_name="llama3.2-vision:11b-instruct-fp16")
```
</details>


<details>
<summary><img src=docs/readme_img/openai-logomark_white.png width=16 /> OpenAI API</summary>

Follow the [Best Practices for API Key Safety](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety) to set up API key.

```bash
export OPENAI_API_KEY=<your_API_key>
```

```python
from vlm4ocr import OpenAIVLMEngine

vlm_engine = OpenAIVLMEngine(model="gpt-4o-mini")
```
</details>

<details>
<summary><img src=docs/readme_img/Azure_icon.png width=32 /> Azure OpenAI API</summary>

Follow the [Azure AI Services Quickstart](https://learn.microsoft.com/en-us/azure/ai-services/openai/quickstart?tabs=command-line%2Ckeyless%2Ctypescript-keyless%2Cpython-new&pivots=programming-language-python) to set up Endpoint and API key.

```bash
export AZURE_OPENAI_API_KEY="<your_API_key>"
export AZURE_OPENAI_ENDPOINT="<your_endpoint>"
```

```python
from llm_ie.engines import AzureOpenAIVLMEngine

vlm_engine = AzureOpenAIVLMEngine(model="gpt-4o-mini", 
                                  api_version="<your api version>")
```
</details>

We define OCR engine and specify output formats.

```python
from vlm4ocr import OCREngine

# Image/PDF paths
image_path = "/examples/synthesized_data/GPT-4o_synthesized_note_1_page_1.jpg"
pdf_path = "/examples/synthesized_data/GPT-4o_synthesized_note_1.pdf"

# Define OCR engine
ocr = OCREngine(vlm_engine, output_mode="markdown")
```

Run OCR sequentially (process one image at a time) for single or multiple files:
```python
# OCR for a single image
ocr_results = ocr.sequential_ocr(image_path, verbose=True)

# OCR for a single pdf (multiple pages)
ocr_results = ocr.sequential_ocr(pdf_path, verbose=True)

# OCR for multiple image and pdf files
ocr_results = ocr.sequential_ocr([pdf_path, image_path], verbose=True)

# Auto-correct page rotation before OCR — "tesseract" uses Tesseract OSD, "vlm" reuses the OCR engine's VLM
ocr_results = ocr.sequential_ocr(image_path, rotate_correction="vlm", verbose=True)

# Inspect OCR results
len(ocr_results) # 2 files
ocr_results[0].input_dir
ocr_results[0].filename
len(ocr_results[0]) # PDF file number of pages
ocr_text = ocr_results[0].to_string() # OCR text (all pages concatenated)
```

Run OCR concurrently and write to file:
```python
import asyncio

async def run_ocr():
    response = ocr.concurrent_ocr([image_path_1, image_path_2], concurrent_batch_size=4)
    async for result in response:
        if result.status == "success":
            filename = result.filename
            ocr_text = result.to_string()
            with open(f"{filename}.md", "w", encoding="utf-8") as f:
                f.write(ocr_text)

asyncio.run(run_ocr())
```

Run OCR with bounding boxes (`output_mode="bbox"`). Leave `user_prompt` empty for full-text bbox OCR, or set it to a free-text instruction for targeted extraction:

```python
from vlm4ocr import VLLMVLMEngine, OCREngine

vlm_engine = VLLMVLMEngine(model="Qwen/Qwen3.5-35B-A3B")

# Full-text OCR with bounding boxes
ocr = OCREngine(vlm_engine=vlm_engine, output_mode="bbox")
ocr_results = ocr.sequential_ocr(image_path)

# Targeted extraction with bounding boxes
ocr = OCREngine(
    vlm_engine=vlm_engine,
    output_mode="bbox",
    user_prompt="Extract patient name, date of birth, Platelets, CMP glucose, BUN, and RBCs values.",
)
ocr_results = ocr.sequential_ocr(image_path)

# Inspect bbox results
for page_num, page in enumerate(ocr_results[0].pages):
    for item in page.bboxes:
        print(item.label, item.bbox, item.text)

    # Visualize on the source page (targeted extraction: color by label, show both)
    annotated = page.plot_bboxes(show_label=True, show_text=True, color="label")
    annotated.save(f"annotated_page{page_num}.png")
```

Note that this is a **synthesized data with NO real PHI!!**
```json
[
	{"bbox_2d": [508, 143, 620, 158], "label": "patient name", "text": "Mary Johnson"},
	{"bbox_2d": [508, 160, 610, 176], "label": "date of birth", "text": "Jan 29, 1990"},
	{"bbox_2d": [484, 405, 569, 421], "label": "Platelets", "text": "280 x10⁹/L"},
	{"bbox_2d": [484, 455, 560, 470], "label": "CMP glucose", "text": "90 mg/dL"},
	{"bbox_2d": [484, 540, 562, 555], "label": "BUN", "text": "12 mg/dL"},
	{"bbox_2d": [484, 778, 690, 794], "label": "RBCs", "text": "0 - 1 per high power field"}
]
```

<div align="left"><img src=docs/readme_img/bbox.png width=500 ></div>

Supply few-shot examples to improve OCR accuracy:
```python
from PIL import Image
import asyncio
from vlm4ocr import FewShotExample, VLLMVLMEngine, OCREngine

# Load few-shot examples
# Note that the example text should be the expected OCR output for the example image. Do not include any extra instructions.
example_1_image = Image.open("example_1.JPG")
with open("example_1.txt", "r") as f:
    example_1_text = f.read()

example_2_image = Image.open("example_2.JPG")
with open("example_2.txt", "r") as f:
    example_2_text = f.read()

few_shot_examples = [
    FewShotExample(image=example_1_image, text=example_1_text, max_dimension_pixels=512),
    FewShotExample(image=example_2_image, text=example_2_text, max_dimension_pixels=512)
]

async def run_ocr():
    response = ocr.concurrent_ocr([image_path_1, image_path_2], concurrent_batch_size=4, few_shot_examples=few_shot_examples)
    async for result in response:
        if result.status == "success":
            filename = result.filename
            ocr_text = result.to_string()
            with open(f"{filename}.md", "w", encoding="utf-8") as f:
                f.write(ocr_text)

asyncio.run(run_ocr())
```

## 💻CLI
Command line interface (CLI) provides an easy way to batch process many images, PDFs, and TIFFs in a directory. 
### Installation

Install the Python package on PyPi and CLI tool will be automatically installed.
```bash
pip install vlm4ocr
```

### Usage
Run OCR for all supported file types in the `/examples/synthesized_data/` folder with a locally deployed [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) and generate results as markdown. OCR results and a log file (enabled by `--log`) will be written to the `output_path`. `--concurrent_batch_size` deternmines the number of images/pages can be processed at a time. This is good for managing resources. 
```sh
# OpenAI compatible API
vlm4ocr --input_path /examples/synthesized_data/ \
        --output_path /examples/ocr_output/ \
        --output_mode markdown \
        --log \
        --vlm_engine openai_compatible \
        --model Qwen/Qwen2.5-VL-7B-Instruct \
        --api_key EMPTY \
        --base_url http://localhost:8000/v1 \
        --concurrent_batch_size 4
```

Use *gpt-4.1-mini* to process a PDF with many pages. Since `--output_path` is not specified, outputs and logs will be written to the current work directory. 
```sh
# OpenAI API
export OPENAI_API_KEY=<api key>
vlm4ocr --input_path /examples/synthesized_data/GPT-4o_synthesized_note_1.pdf \
        --output_mode HTML \
        --log \
        --vlm_engine openai \
        --model gpt-4.1-mini \
        --concurrent_batch_size 4
```