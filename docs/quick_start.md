## Installation

Python package is available on PyPi.
```bash
pip install vlm4ocr
```

## Quick start
In this demo, we use a locally deployed [vLLM OpenAI compatible server](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) to run [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct). For more inference APIs and VLMs, please see [VLMEngine](./vlm_engines.md). 

```python
from vlm4ocr import VLLMVLMEngine

vlm_engine = VLLMVLMEngine(model="Qwen/Qwen2.5-VL-7B-Instruct")
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
### Full text OCR
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

# Per-page access — pages are OCRPage dataclasses
page = ocr_results[0].get_page(0)
page.text                         # OCR text for this page
page.image_processing_status      # rotation/resize status dict
# Dict-style access is preserved for backward compatibility:
page["text"]
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

### Key information extraction with JSON
In some use cases, we are only interested in a specific set of key information from the OCR results. Processing the entire OCR text is inefficient. We can directly extract the key information using the `output_mode="JSON"`. To use the JSON extraction feature, a custom user prompt that defines the JSON structure is required. The example below demonstrates how to extract key information from images and PDFs. 

#### Run OCR sequentially 

```python
import json

user_prompt = """
Your output should include keys: "Patient", "MRN". 
For example:
{
    "Patient": "John Doe",
    "MRN": "12345"
}
"""

ocr = OCREngine(vlm_engine=vlm, output_mode="JSON", user_prompt=user_prompt)
ocr_results = ocr.sequential_ocr([image_path_1, image_path_2], verbose=True)

for result in ocr_results:
    for page_num, page in enumerate(result.pages):
        print(json.loads(page['text']))
        with open(f"{result.filename}_page_{page_num}.json", "w", encoding="utf-8") as f:
            json.dump(json.loads(page['text']), f, indent=4)
```

#### Run OCR concurrently 

```python
import asyncio
import json

user_prompt = """
Your output should include keys: "Patient", "MRN". 
For example:
{
    "Patient": "John Doe",
    "MRN": "12345"
}
"""
ocr = OCREngine(vlm_engine=vlm, output_mode="JSON", user_prompt=user_prompt)

async def run_ocr():
    response = ocr.concurrent_ocr([image_path_1, image_path_2], concurrent_batch_size=4)
    async for result in response:
        if result.status == "success":
            filename = result.filename
            for page_num, page in enumerate(result.pages):
                with open(f"{filename}_page_{page_num}.json", "w", encoding="utf-8") as f:
                    json.dump(json.loads(page['text']), f, indent=4)
                print(f"Saved {filename}_page_{page_num}.json")
        else:
            print(f"Error processing {result.filename}: {result.error}")

asyncio.run(run_ocr())
```

### OCR with bounding boxes
For workflows that need region-level positioning — for example, downstream layout analysis, redaction, or visual QA — use `output_mode="bbox"`. The OCR engine returns the same per-page text plus a `bboxes` list of `BBoxItem` records (`bbox=[x1, y1, x2, y2]`, `label`, `text`).

Two complementary modes are supported:

- **Full-text bbox OCR** — leave `user_prompt` empty (or pass `None`). The model transcribes the entire page and returns one box per region.
- **Targeted extraction** — pass a free-text instruction such as `"Extract patient name and date of birth"`. Only regions matching the instruction are returned.

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
    user_prompt="Extract patient name and date of birth",
)
ocr_results = ocr.sequential_ocr(image_path)
```

Inspect and visualize results:

```python
# Inspect bbox results
for page_num, page in enumerate(ocr_results[0].pages):
    for item in page.bboxes:
        print(item.label, item.bbox, item.text)

    # Visualize on the source page (full-text mode: random colors, text only)
    annotated = page.plot_bboxes(show_label=False, show_text=True, color="random")
    annotated.save(f"annotated_page{page_num}.png")
```

#### Per-VLM bbox formats
Different VLM families emit boxes with different conventions (key names, axis order, coordinate scale). `vlm4ocr` resolves the right format automatically from the model name. **Qwen3-VL**, **Gemma 3/4**, and **GPT-4.1** are registered out of the box. To override the auto-resolved format, pass a custom `BBoxFormat`:

```python
from vlm4ocr import OCREngine, BBoxFormat

ocr = OCREngine(
    vlm_engine=vlm_engine,
    output_mode="bbox",
    bbox_format=BBoxFormat(
        coord_scale="normalized_1000",
        axis_order="x0y0x1y1",
        bbox_key="bbox_2d",
        label_key="label",
        text_key="text",
    ),
)
```

If the model name matches no registered pattern, a default `BBoxFormat()` is used and a warning is logged.

## Few-shot examples
Few-shot examples can be provided to improve the accuracy. Below are examples of how to include few-shot examples in the OCR engine.

### Few-shot examples for full-text OCR
First, we prepare a list of few-shot examples. Each example is an object of `FewShotExample` that contains an input image (`PIL.Image.Image`) and the corresponding expected output text. Note that the output text should be the exact text you expect the VLM to generate for the given input image. **Do not include any additional explanations or variations**. Few-shot examples can also include a `max_dimension_pixels` parameter to resize the image while maintaining the aspect ratio. This is useful when the original image size exceeds the VLM's maximum input size. Few-shot examples can also include a `rotate_correction` parameter to automatically correct the image orientation before feeding it to the VLM.
The few-shot example images and text are available in the `examples/synthesized_data/few_shot_examples/` folder in this repository.
```python
import os
from PIL import Image
from vlm4ocr import FewShotExample

# Load few-shot examples
example_1_image = Image.open(os.path.join("examples", "synthesized_data", "few_shot_examples", "images", "template_1_sample_4_poor.JPG"))
with open(os.path.join("examples", "synthesized_data", "few_shot_examples", "ground_truth", "template_1_sample_4_poor.txt"), "r") as f:
    example_1_text = f.read()

example_2_image = Image.open(os.path.join("examples", "synthesized_data", "few_shot_examples", "images", "template_3_sample_4_poor.JPG"))
with open(os.path.join("examples", "synthesized_data", "few_shot_examples", "ground_truth", "template_3_sample_4_poor.txt"), "r") as f:
    example_2_text = f.read()

few_shot_examples = [
    FewShotExample(image=example_1_image, text=example_1_text, max_dimension_pixels=512),
    FewShotExample(image=example_2_image, text=example_2_text, max_dimension_pixels=512)
]
```

We load the target image for OCR.
```python
image_path = os.path.join("examples", "synthesized_data", "few_shot_examples", "images", "template_6_sample_4_poor.JPG")
```

As before, we define the VLM engine and OCR engine.

```python
from vlm4ocr import VLLMVLMEngine, OCREngine

# Define VLM engine
vlm_engine = VLLMVLMEngine(model="Qwen/Qwen2.5-VL-7B-Instruct")

# Define OCR engine
ocr = OCREngine(vlm_engine, output_mode="text")      
```

But this time, we pass the few-shot examples to the OCR methods.

```python
# OCR for a single image
ocr_results = ocr.sequential_ocr(image_path, max_dimension_pixels=512, verbose=True, few_shot_examples=few_shot_examples)
```


### Few-shot examples for key information extraction with JSON
```python
import os
from PIL import Image
from vlm4ocr import FewShotExample

# Load few-shot examples
example_1_image = Image.open(os.path.join("examples", "synthesized_data", "few_shot_examples", "images", "template_1_sample_4_poor.JPG"))
with open(os.path.join("examples", "synthesized_data", "few_shot_examples", "ground_truth", "template_1_sample_4_poor.json"), "r") as f:
    example_1_text = f.read()

example_2_image = Image.open(os.path.join("examples", "synthesized_data", "few_shot_examples", "images", "template_3_sample_4_poor.JPG"))
with open(os.path.join("examples", "synthesized_data", "few_shot_examples", "ground_truth", "template_3_sample_4_poor.json"), "r") as f:
    example_2_text = f.read()

few_shot_examples = [
    FewShotExample(image=example_1_image, text=example_1_text, max_dimension_pixels=512),
    FewShotExample(image=example_2_image, text=example_2_text, max_dimension_pixels=512)
]
```


We load the target image for OCR.
```python
image_path = os.path.join("examples", "synthesized_data", "few_shot_examples", "images", "template_6_sample_4_poor.JPG")
```

We define the VLM engine, JSON extraction schema, and OCR engine.

```python
from vlm4ocr import VLLMVLMEngine, OCREngine

# Define VLM engine
vlm_engine = VLLMVLMEngine(model="Qwen/Qwen2.5-VL-7B-Instruct")

# Define JSON extraction schema
user_prompt = """
Your output should include keys: "Patient", "MRN". 
For example:
{
    "Patient": "John Doe",
    "MRN": "12345"
}
"""

# Define OCR engine
ocr = OCREngine(vlm_engine, output_mode="JSON", user_prompt=user_prompt)      
```

But this time, we pass the few-shot examples to the OCR methods.

```python
# OCR for a single image
ocr_results = ocr.sequential_ocr(image_path, max_dimension_pixels=512, verbose=True, few_shot_examples=few_shot_examples)
```