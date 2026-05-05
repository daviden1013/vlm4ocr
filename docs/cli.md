Command line interface (CLI) provides an easy way to batch process many images, PDFs, and TIFFs in a directory.

## Installation

Install the Python package on PyPi and the CLI tool will be automatically installed.
```bash
pip install vlm4ocr
```

## Quick Start

Run OCR for all supported file types in the `/examples/synthesized_data/` folder with a locally deployed [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) and generate results as markdown. OCR results and a log file (enabled by `--log`) will be written to the `output_path`. `--concurrent_batch_size` determines the number of images/pages that can be processed at a time.
```sh
# OpenAI compatible API
vlm4ocr --input_path /examples/synthesized_data/ \
        --output_path /examples/ocr_output/ \
        --skip_existing \
        --output_mode markdown \
        --log \
        --max_dimension_pixels 4000 \
        --vlm_engine openai_compatible \
        --model Qwen/Qwen2.5-VL-7B-Instruct \
        --api_key EMPTY \
        --base_url http://localhost:8000/v1 \
        --concurrent_batch_size 4
```

Use *gpt-4o-mini* to process a PDF. Since `--output_path` is not specified, outputs and logs will be written to the current working directory.
```sh
# OpenAI API
export OPENAI_API_KEY=<api key>
vlm4ocr --input_path /examples/synthesized_data/GPT-4o_synthesized_note_1.pdf \
        --output_mode HTML \
        --log \
        --vlm_engine openai \
        --model gpt-4o-mini \
        --concurrent_batch_size 4
```

Use a locally deployed *Qwen3.5-35B-A3B* via vLLM. Pass `extra_body` to disable the model's thinking mode:
```sh
vlm4ocr --input_path /examples/synthesized_data/ \
        --output_path /examples/ocr_output/ \
        --skip_existing \
        --output_mode markdown \
        --log \
        --vlm_engine vllm \
        --model Qwen/Qwen3.5-35B-A3B \
        --base_url http://localhost:8000/v1 \
        --max_new_tokens 16384 \
        --temperature 0.7 \
        --top_p 0.8 \
        --presence_penalty 1.5 \
        --extra_body '{"top_k": 20, "min_p": 0.0, "chat_template_kwargs": {"enable_thinking": false}}' \
        --concurrent_batch_size 4
```

Extract structured JSON from a document by describing the fields in a prompt file:
```sh
vlm4ocr --input_path /examples/invoice.pdf \
        --output_mode JSON \
        --user_prompt_file /examples/prompts/invoice_schema.txt \
        --output_path /examples/ocr_output/ \
        --vlm_engine openai \
        --model gpt-4o \
        --concurrent_batch_size 4
```

Detect and localize all text regions (full-text bbox OCR) across a directory of images:
```sh
vlm4ocr --input_path /examples/images/ \
        --output_mode bbox \
        --output_path /examples/bbox_output/ \
        --vlm_engine openai \
        --model gpt-4o \
        --concurrent_batch_size 4
```

Target a specific field (targeted bbox extraction) with a user prompt:
```sh
vlm4ocr --input_path /examples/images/ \
        --output_mode bbox \
        --user_prompt "Extract all price and total amount fields." \
        --output_path /examples/bbox_output/ \
        --vlm_engine openai \
        --model gpt-4o \
        --concurrent_batch_size 4
```

## Usage
The CLI parameters are grouped into categories to manage the OCR process.

#### Input/Output Options
- `--input_path` Specify a single input file or a directory with multiple files for OCR.
- `--output_mode` Output format. One of `text`, `markdown`, `HTML`, `JSON`, or `bbox`. (default: `markdown`)
  - `JSON` — extracts structured data; requires `--user_prompt` or `--user_prompt_file` to define the JSON structure.
  - `bbox` — detects and localizes text regions. Writes one `.json` file per document (bounding box coordinates and text) and one annotated `.png` per page. Without a user prompt, performs full-text OCR over the whole page; with a user prompt, targets the described fields.
- `--output_path` If `input_path` is a directory of multiple files, this should be an output directory. If input is a single file, this can be a full file path or a directory. If not provided, results are saved to the current working directory.
- `--skip_existing` Skip processing files that already have OCR results in the output directory.

#### Image Processing Parameters
- `--rotate_correction` Apply automatic rotation correction. Choices: `tesseract` (requires Tesseract OCR), `vlm` (prompts the configured VLM). Omit to disable. (default: disabled)
- `--max_dimension_pixels` Maximum dimension (width or height) in pixels for input images. Images larger than this will be resized while maintaining aspect ratio. (default: 4000)

#### VLM Engine Selection
- `--vlm_engine` VLM backend. One of `openai`, `azure_openai`, `ollama`, `openai_compatible`, `vllm`, `sglang`, or `openrouter`.
- `--model` VLM model name.
- `--max_new_tokens` Maximum output tokens. (default: 4096)
- `--temperature` Sampling temperature. (default: model default)
- `--top_p` Sampling top-p. (default: model default)
- `--presence_penalty` Presence penalty. (default: model default)
- `--extra_body` Additional request body fields as a JSON string. Useful for engine-specific parameters such as `top_k`, `min_p`, or `chat_template_kwargs` (e.g. to disable thinking mode on Qwen3 models).

##### OpenAI & OpenAI-Compatible Options (`openai`, `openai_compatible`, `vllm`, `sglang`, `openrouter`)
- `--api_key` API key. Can also be set via `OPENAI_API_KEY` (OpenAI) or `OPENROUTER_API_KEY` (openrouter) environment variable. Optional for `vllm` and `sglang` (local servers typically don't require one).
- `--base_url` Base URL for the API. Required for `openai_compatible`. Defaults: `vllm` → `http://localhost:8000/v1`, `sglang` → `http://localhost:30000/v1`, `openrouter` → `https://openrouter.ai/api/v1`.

##### Azure OpenAI Options
- `--azure_api_key` Azure API key. Can also be set via `AZURE_OPENAI_API_KEY`.
- `--azure_endpoint` Azure endpoint URL. Can also be set via `AZURE_OPENAI_ENDPOINT`.
- `--azure_api_version` Azure API version. Can also be set via `AZURE_OPENAI_API_VERSION`.

##### Ollama Options
- `--ollama_host` Ollama host URL. (default: `http://localhost:11434`)
- `--ollama_num_ctx` Context length. (default: 4096)
- `--ollama_keep_alive` Keep-alive seconds. (default: 300)

#### OCR Engine Parameters
- `--user_prompt` Custom user prompt as an inline string. For multi-line prompts prefer `--user_prompt_file`. If both are provided, `--user_prompt` takes precedence with a warning.
- `--user_prompt_file` Path to a text file containing the user prompt. Useful for long prompts or JSON schema definitions.
- `--system_prompt` Custom system prompt as an inline string. Overrides the built-in default for the selected output mode. If both `--system_prompt` and `--system_prompt_file` are provided, `--system_prompt` takes precedence with a warning.
- `--system_prompt_file` Path to a text file containing the system prompt.

#### Processing Options
- `--concurrent_batch_size` Number of images/pages to process concurrently. Set to 1 for sequential processing. (default: 4)
- `--max_file_load` Number of input files to pre-load. Set to -1 for automatic: 2 × `concurrent_batch_size`. (default: -1)
- `--log` Write logs to a timestamped file in the output directory.
- `--debug` Enable debug-level logging on the console (and in the log file if `--log` is active).

## Output Files

| `--output_mode` | Output per document |
|---|---|
| `markdown` | `<filename>_ocr.md` |
| `HTML` | `<filename>_ocr.html` |
| `text` | `<filename>_ocr.txt` |
| `JSON` | `<filename>_ocr.json` |
| `bbox` | `<filename>_ocr.json` + `<filename>_ocr_page1.png`, `_page2.png`, … |

The bbox JSON structure is:
```json
{
  "filename": "document.pdf",
  "pages": [
    {
      "page_idx": 0,
      "image_width": 1024,
      "image_height": 768,
      "bboxes": [
        { "bbox": [x1, y1, x2, y2], "label": "...", "text": "..." }
      ]
    }
  ]
}
```
