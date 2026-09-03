from vlm4ocr import BasicVLMConfig, OpenAIReasoningVLMConfig, OCREngine, OpenAIVLMEngine, AzureOpenAIVLMEngine, OllamaVLMEngine

image_path_1 = "/home/daviden1013/David_projects/vlm4ocr/examples/synthesized_data/GPT-4o_synthesized_note_1_page_1.jpg"
image_path_2 = "/home/daviden1013/David_projects/vlm4ocr/examples/synthesized_data/GPT-4o_synthesized_note_1.pdf"

""" OpenAI compatible """
vlm = OpenAIVLMEngine(model="Qwen/Qwen2.5-VL-7B-Instruct", base_url="http://localhost:8000/v1", api_key="EMPTY", config=BasicVLMConfig(
    max_tokens=2048,
    temperature=0.0
))

""" Ollama """
vlm = OllamaVLMEngine(model_name="llama3.2-vision:11b-instruct-fp16")

""" OpenAI """
vlm = OpenAIVLMEngine(model="gpt-4-turbo")
vlm = OpenAIVLMEngine(model="o3-mini", config=OpenAIReasoningVLMConfig(reasoning_effort="low"))

""" Azure OpenAI """
vlm = AzureOpenAIVLMEngine(model="gpt-4-turbo", api_version="<api_version>")

""" Full text OCR """
# pdf_backend is required for PDF input (image_path_2 below is a PDF). vlm4ocr installs no
# PDF library: pick one and install it, e.g. pip install vlm4ocr[pypdfium2].
ocr = OCREngine(vlm_engine=vlm, output_mode="markdown", pdf_backend="pypdfium2")
ocr_results = ocr.sequential_ocr([image_path_1, image_path_2], max_dimension_pixels=512, verbose=True)

""" JSON output """

user_prompt = """
Your output should include keys: "Patient", "MRN". 
For example:
{
    "Patient": "John Doe",
    "MRN": "12345"
}
"""

ocr = OCREngine(vlm_engine=vlm, output_mode="JSON", user_prompt=user_prompt, pdf_backend="pypdfium2")
ocr_results = ocr.sequential_ocr([image_path_1, image_path_2], max_dimension_pixels=512, verbose=True)

import json
for result in ocr_results:
    for page in result.pages:
        print(json.loads(page['text']))

import os
import asyncio
async def run_ocr():
    response = ocr.concurrent_ocr([image_path_1, image_path_2], concurrent_batch_size=4)
    async for result in response:
        if result.status == "success":
            filename = result.filename
            for page_num, page in enumerate(result.pages):
                with open(os.path.join("/home/daviden1013/David_projects/vlm4ocr", f"{filename}_page_{page_num}.json"), "w", encoding="utf-8") as f:
                    json.dump(json.loads(page['text']), f, indent=4)
                print(f"Saved {filename}_page_{page_num}.json")
        else:
            print(f"Error processing {result.filename}: {result.error}")

asyncio.run(run_ocr())