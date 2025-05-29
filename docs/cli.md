Command line interface (CLI) provides an easy way to batch process many images, PDFs, and TIFFs in a directory. 

## Installation

Install the Python package on PyPi and the CLI tool will be automatically installed.
```bash
pip install vlm4ocr
```

## Quick Start
Run OCR for all supported file types in the `/examples/synthesized_data/` folder with a locally deployed [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) and generate results as markdown. OCR results and a log file (enabled by `--log`) will be written to the `output_path`. `--concurrent_batch_size` deternmines the number of images/pages can be processed at a time. This is good for managing resources. 
```sh
# OpenAI compatible API
vlm4ocr --input_path /examples/synthesized_data/ \
        --output_path /examples/ocr_output/ \
        --skip_existing \
        --output_mode markdown \
        --log \
        --vlm_engine openai_compatible \
        --model Qwen/Qwen2.5-VL-7B-Instruct \
        --api_key EMPTY \
        --base_url http://localhost:8000/v1 \
        --concurrent_batch_size 4
```

Use *gpt-4o-mini* to process a PDF with many pages. Since `--output_path` is not specified, outputs and logs will be written to the current work directory. 
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

## Usage
The CLI parameters are grouped into categories to manage the OCR process.

#### Input/Output Options
- `--input_path` Specify a single input file or a directory with multiple files for OCR.
- `--output_mode` Should be one of `text`, `markdown`, or `HTML`.
- `--output_path` If input_path is a directory of multiple files, this should be an output directory. If input is a single file, this can be a full file path or a directory. If not provided, results are saved to the current working directory. 
- `--skip_existing` Skip processing files that already have OCR results in the output directory. If False, all input files will be processed and potentially overwrite existing outputs.

#### VLM Engine Selection
- `--vlm_engine` Should be one of `openai`, `azure_openai`, `ollama`, or `openai_compatible`.
- `--model` VLM model name.

##### OpenAI & OpenAI-Compatible Options
- `--api_key` API key. Can be set though environmental variable.
- `--base_url` Base URL.

##### Azure OpenAI Options
- `--azure_api_key` Azure API key. Can be set though environmental variable. 
- `--azure_endpoint` Azure endpoint. Can be set though environmental variable. 
- `--azure_api_version` Azure API version. 

##### Ollama Options
- `--ollama_host` Ollama host:port (default: http://localhost:11434).
- `--ollama_num_ctx` Ollama context length (default: 4096).
- `--ollama_keep_alive` Ollama keep_alive seconds. (default: 300)

#### OCR Engine Parameters
- `--user_prompt` Specify custom user prompt.
- `--max_new_tokens` Set maximum output tokens (default: 4096).
- `--temperature` Set temperature (default: 0.0).

#### Processing Options
- `--concurrent_batch_size` Number of images/pages to process concurrently. Set to 1 for sequential processing of VLM calls. (default: 4)
- `max_file_load` Number of input files to pre-load. Set to -1 for automatic config: 2 * concurrent_batch_size. 
- `--log` Enable writing logs to a timestamped file in the output directory. (default: False)
- `--debug` Enable debug level logging for console (and file if --log is active). (default: False)
