## Installation

Python package is available on PyPi.
```bash
pip install vlm4ocr
```

## Quick start
In this demo, we use a locally deployed [vLLM OpenAI compatible server](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) to run [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct). For more inference APIs and VLMs, please see [VLMEngine](./vlm_engines.md). 

```python
from vlm4ocr import OpenAIVLMEngine

vlm_engine = OpenAIVLMEngine(model="Qwen/Qwen2.5-VL-7B-Instruct", 
                             base_url="http://localhost:8000/v1", 
                             api_key="EMPTY")
```

We define OCR engine and specify output formats.

```python
from vlm4ocr import OCREngine

# Image/PDF paths
image_path = "/examples/synthesized_data/GPT-4o_synthesized_note_1_page_1.jpg"
pdf_path = "/examples/synthesized_data/GPT-4o_synthesized_note_1.pdf"

# Define OCR engine
ocr = OCREngine(vlm_engine, output_mode="markdown")
```

#### Run OCR sequentially 
We run OCR sequentially (process one image at a time) for single or multiple files. This approach is suitable for testing or processing small-scaled requests.

```python
# OCR for a single image
ocr_results = ocr.sequential_ocr(image_path, verbose=True)

# OCR for a single pdf (multiple pages)
ocr_results = ocr.sequential_ocr(pdf_path, verbose=True)

# OCR for multiple image and pdf files
ocr_results = ocr.sequential_ocr([pdf_path, image_path], verbose=True)

# Inspect OCR results
len(ocr_results) # 2 files
ocr_results[0].input_dir # input dir
ocr_results[0].filename # input filename
ocr_results[0].status # OCR result status: 'success'
len(ocr_results[0]) # PDF file number of pages
ocr_text = ocr_results[0].to_string() # OCR text (all pages concatenated)
```

#### Run OCR concurrently 
For high-volume OCR tasks, it is more efficient to run OCR concurrently. The example below concurrently processes 4 images/pages at a time and write outputs to file whenever a file has finished. 

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