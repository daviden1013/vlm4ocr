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

""" run OCR """
ocr = OCREngine(vlm_engine=vlm, output_mode="markdown")
ocr_results = ocr.sequential_ocr([image_path_1, image_path_2], max_dimension_pixels=512, verbose=True)
