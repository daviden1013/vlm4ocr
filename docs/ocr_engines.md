OCR engine handles the OCR process. It supports [concurrent processing](#concurrent-ocr) which is ideal for large amount of input files; [sequential processing](#sequential-ocr) which is good for lightweight tasks or testing; [streaming](#stream-ocr) that streams OCR results which is designed for frontend integration.

OCR engine requires an [VLM engine](./vlm_engines.md) instance and an `output_mode` as one of *markdown*, *HTML*, *text*, *JSON*, or *bbox*. The optional `user_prompt` can be used to provide additional information about the input files. For example, *The input is a scanned MRI report*. Note that for `output_mode="JSON"`, the `user_prompt` is required to define the structure of the JSON output. For `output_mode="bbox"`, the `user_prompt` is optional — leave it empty for full-text bbox OCR, or set it to a free-text instruction for targeted extraction.

```python
from vlm4ocr import OCREngine

ocr = OCREngine(vlm_engine=vlm_engine, 
                output_mode="markdown", 
                user_prompt="<additional information about the input files>")
```

`system_prompt` can be customized. But we recommend using the default (`system_prompt=None` or omit) since it controls the output mode and post-processing. Below is the system prompt for markdown output mode:

```text
You are a helpful assistant that can convert scanned documents \
into markdown text. Your output is accurate and well-formatted, \
starting with ```markdown and ending with ```. You will only \
output the markdown text without any additional explanations or comments. \
The markdown should include all text, tables, and lists with appropriate \
headers (e.g., "##"). You will ignore images, icons, or anything that can \
not be converted into text.
```

## Concurrent OCR
`concurrent_ocr` is the recommended method to process large amount of files. The method returns an async generator of `OCRResult` instance (`AsyncGenerator[OCRResult, None]`). OCR results are generated whenever is ready (first-done-first-out). **There is no guarantee the input order and output order will match. Use the `OCRResult.filename` as identifier**. The `file_paths` is a single file (image, PDF, TIFF) or a list of file directories. `rotate_correction` use [Tesseract](https://pypi.org/project/pytesseract/) to correct for rotation. **Please install Tesseract to use this feature**. `max_dimension_pixels` resize images to ensure the largest dimension (width or length) are less than the maximum allowed pixels. Few-shot examples can be provided via `few_shot_examples` parameter to improve OCR accuracy. `concurrent_batch_size` is the number of images/pages that VLM processes at a time. This is used to manage inferencing resource (usually GPU). The `max_file_load` is the number of input files to be pre-loaded for staging. This manages the I/O and memory (dRAM) resources. By default, `max_file_load` is twice of `concurrent_batch_size`. 

The code below runs OCR in batches of 4 images/pages, while having 8 files pre-loaded to ensure efficiency. 
```python
response = ocr.concurrent_ocr(file_paths=<a list of files>, 
                              rotate_correction=True,
                              max_dimension_pixels=4000,
                              few_shot_examples=<optional, a list of few-shot examples>,
                              concurrent_batch_size=4,
                              max_file_load=8)
```

#### Example: dynamic output-writing
The example below use `concurrent_ocr` to perform OCR and write available results to file.

```python
import asyncio

async def run_ocr():
    response = ocr.concurrent_ocr(<list of files>, concurrent_batch_size=4)
    async for result in response:
        if result.status == "success":
            filename = result.filename
            ocr_text = result.to_string()
            with open(f"{filename}.md", "w", encoding="utf-8") as f:
                f.write(ocr_text)

asyncio.run(run_ocr())
```

## Sequential OCR
`sequential_ocr` is a lightweight method to perform OCR. Input files are processed page by page, file by file sequentially. This is suitable for small-scaled tasks or testing. The `verbose=True` streams the OCR results in console. 

```python
# OCR for a single image
ocr_results = ocr.sequential_ocr(image_path, verbose=True)

# OCR for a single pdf (multiple pages)
ocr_results = ocr.sequential_ocr(pdf_path, verbose=True)

# OCR for multiple image and pdf files
ocr_results = ocr.sequential_ocr([pdf_path, image_path], verbose=True)

# Inspect OCR results
len(ocr_results) # 2 files
ocr_results[0].input_dir
ocr_results[0].filename
len(ocr_results[0]) # PDF file number of pages
ocr_text = ocr_results[0].to_string() # OCR text (all pages concatenated)
```

## Stream OCR
`stream_ocr` method is designed for frontend integration. It outputs a generator of chunk dictionary (`Generator[Dict[str, str], None, None]`). For OCR output tokens, it yields: {"type": "ocr_chunk", "data": chunk}. For page delimitors, it yields: {"type": "page_delimiter", "data": page_delimiter}. 

```python
response = ocr.stream_ocr(image_path)

for chunk in response:
    if chunk["type"] == "ocr_chunk":
        print(chunk["data"], end="", flush=True)
    elif chunk["type"] == "page_delimiter":
        print(chunk["data"])
```

## Few-shot Examples
Few-shot examples can be provided to improve OCR accuracy. Each example is an object of `FewShotExample` class that contains `image` and `text` attributes. Note that the output text should be the exact text you expect the VLM to generate for the given input image. **Do not include any additional explanations or variations**. Few-shot examples can also include a `max_dimension_pixels` parameter to resize the image while maintaining the aspect ratio. This is useful when the original image size exceeds the VLM's maximum input size. Few-shot examples can also include a `rotate_correction` parameter to automatically correct the image orientation before feeding it to the VLM.

```python
import os
from PIL import Image
from vlm4ocr import FewShotExample

# Load few-shot examples
example_1_image = Image.open("<path_to_example_1_image>")
example_1_text = """<expected output text for example 1>"""

example_2_image = Image.open("<path_to_example_2_image>")
example_2_text = """<expected output text for example 2>"""

few_shot_examples = [
    FewShotExample(image=example_1_image, text=example_1_text, rotate_correction=True, max_dimension_pixels=512),
    FewShotExample(image=example_2_image, text=example_2_text, rotate_correction=True, max_dimension_pixels=512)
]

# Use few-shot examples in OCR
ocr_results = ocr.sequential_ocr([image_path_1, image_path_2], 
                                 few_shot_examples=few_shot_examples,
                                 verbose=True)
```