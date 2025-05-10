![Python Version](https://img.shields.io/pypi/pyversions/vlm4ocr)
![PyPI](https://img.shields.io/pypi/v/vlm4ocr)

Vision Language Models (VLMs) for Optical Character Recognition (OCR).

| Feature                 | Support                                                                 |
| :---------------------- | :---------------------------------------------------------------------- |
| **File Types** | :white_check_mark: PDF, TIFF, PNG, JPG/JPEG, BMP, GIF, WEBP         |
| **VLM Engines** | :white_check_mark: Ollama, OpenAI Compatible, OpenAI, Azure OpenAI |
| **Output Modes** | :white_check_mark: Markdown, HTML, plain text |
| **Batch OCR** | :white_check_mark: Processes many pages concurrently by setting `concurrent_batch_size` |


## Table of Contents
- [Overview](#overview)
- [Supported Models](#supported-models)
- [Example Notebooks](#example-notebooks)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Web Application](#web-application)
- [Python package](#python-package)

## :sparkles:Overview
`vlm4ocr` provides a simple way to perform OCR using the power of modern Vision Language Models (VLMs). A drag-and-drop **web application** is included for easy access. The **Python package** supports concurrent batch processing for large amount of documents.

#### Markdown output mode
<div align="center"><img src=doc_asset/readme_img/table_markdown_demo.PNG width=1000 ></div>

#### HTML output mode
<div align="center"><img src=doc_asset/readme_img/report_HTML_demo.PNG width=1000 ></div>

## :star:Supported Models 
### Open-weights (ALL Supported!!)
**All open-weights VLMs are supported** via our [Ollama](/packages/vlm4ocr/vlm4ocr/vlm_engines.py) and [OpenAI compatible engines](/packages/vlm4ocr/vlm4ocr/vlm_engines.py), including:
- [Qwen2.5-VL](https://huggingface.co/collections/Qwen/qwen25-vl-6795ffac22b334a837c0f9a5)
- [Llama-3.2](https://huggingface.co/collections/meta-llama/llama-32-66f448ffc8c32f949b04c8cf)
- [LLaVa-1.5](https://huggingface.co/collections/llava-hf/llava-15-65f762d5b6941db5c2ba07e0)

### Proprietary 
Proprietary models such as gpt-4o are supported via our [OpenAI](/packages/vlm4ocr/vlm4ocr/vlm_engines.py) and [Azure](/packages/vlm4ocr/vlm4ocr/vlm_engines.py) engines.

## :books:Example Notebooks



## :vertical_traffic_light:Prerequisites
- Python 3.x
- For PDF processing: [poppler](https://pypi.org/project/pdf2image/) library.
- At least one VLM inference engine setup (Ollama, OpenAI/Azure API keys, or an OpenAI-compatible API endpoint).

```bash
pip install ollama # For Ollama
pip install openai # For OpenAI (compatible) and Azure OpenAI
```

## :earth_americas:Web Application
A ready-to-use Flask web application is included.

https://github.com/user-attachments/assets/b196453c-fd2c-491a-ba1e-0a77cf7f5941

### Installation
#### Install from source
```bash
# Install python package
pip install vlm4ocr 

# Clone source code
git clone https://github.com/daviden1013/vlm4ocr.git

# Run Web App
cd vlm4ocr/services/web_app
python run.py
```

## :computer:CLI
Command line interface (CLI) provides an easy way to batch process many images, PDFs, and TIFFs in a directory. 
### Installation

Install the Python package on PyPi and CLI tool will be automatically installed.
```bash
pip install vlm4ocr
```

### Usage
Run OCR for all supported file types in the `/examples/synthesized_data/` folder with a locally deployed [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct).
```sh
# OpenAI compatible API (batch processing)
vlm4ocr --input_path /examples/synthesized_data/ \
        --output_mode markdown \
        --vlm_engine openai_compatible \
        --model Qwen/Qwen2.5-VL-7B-Instruct \
        --api_key EMPTY \
        --base_url http://localhost:8000/v1 \
        --concurrent \
        --concurrent_batch_size 4 \
```

Alternatively, use *gpt-4o-mini* to process a PDF with many pages by batch.
```sh
# OpenAI API
export OPENAI_API_KEY=<api key>
vlm4ocr --input_path /examples/synthesized_data/GPT-4o_synthesized_note_1.pdf \
        --output_mode HTML \
        --vlm_engine openai \
        --model gpt-4o-mini \
        --concurrent \
        --concurrent_batch_size 4 \
```

## :snake:Python package
### Installation

Python package is available on PyPi
```bash
pip install vlm4ocr
```

### Quick start
In this demo, we use a locally deployed [vLLM OpenAI compatible server](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) to run [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct).

```python
from vlm4ocr import OpenAIVLMEngine

vlm_engine = OpenAIVLMEngine(model="Qwen/Qwen2.5-VL-7B-Instruct", 
                             base_url="http://localhost:8000/v1", 
                             api_key="EMPTY")
```

To use other VLM inference engines:
<details>
<summary> OpenAI Compatible</summary>

```python
from vlm4ocr import OpenAIVLMEngine

vlm_engine = OpenAIVLMEngine(model="<mode_name>", base_url="<base_url>", api_key="<api_key>")
```
</details>

<details>
<summary> <img src="doc_asset/readme_img/ollama_icon.png" alt="Icon" width="22"/> Ollama</summary>

```python
from vlm4ocr import OllamaVLMEngine

vlm_engine = OllamaVLMEngine(model_name="llama3.2-vision:11b-instruct-fp16")
```
</details>


<details>
<summary><img src=doc_asset/readme_img/openai-logomark_white.png width=16 /> OpenAI API</summary>

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
<summary><img src=doc_asset/readme_img/Azure_icon.png width=32 /> Azure OpenAI API</summary>

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

Run OCR for single or multiple files:
```python
# OCR for a single image
ocr_results = ocr.run_ocr(image_path, verbose=True)

# OCR for a single pdf (multiple pages)
ocr_results = ocr.run_ocr(pdf_path, verbose=True)

# OCR for multiple image/pdf files
ocr_results = ocr.run_ocr([image_path, pdf_path], verbose=True)

# Batch OCR for multiple image/pdf files
ocr_results = ocr.run_ocr([image_path, pdf_path], concurrent=True, concurrent_batch_size=32)
