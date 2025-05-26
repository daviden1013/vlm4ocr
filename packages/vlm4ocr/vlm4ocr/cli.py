import argparse
import os
import sys
import logging
import asyncio
import time

# Attempt to import from the local package structure
try:
    from .ocr_engines import OCREngine
    from .vlm_engines import OpenAIVLMEngine, AzureOpenAIVLMEngine, OllamaVLMEngine
    from .data_types import OCRResult
except ImportError:
    # Fallback for when the package is installed
    from vlm4ocr.ocr_engines import OCREngine
    from vlm4ocr.vlm_engines import OpenAIVLMEngine, AzureOpenAIVLMEngine, OllamaVLMEngine
    from vlm4ocr.data_types import OCRResult

import tqdm.asyncio

# --- Global logger setup (console) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("vlm4ocr_cli")

SUPPORTED_IMAGE_EXTS_CLI = ['.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']
OUTPUT_EXTENSIONS = {'markdown': '.md', 'HTML':'.html', 'text':'.txt'}

def get_output_path(input_file_path, args_output_file, output_mode, num_total_inputs, base_output_dir_for_multiple_no_output_file_arg):
    """
    Determines the full output path for a given input file.
    Output filename format: <original_basename>_ocr.<new_extension>
    Example: input "abc.pdf", output_mode "markdown" -> "abc.pdf_ocr.md"
    """
    original_basename = os.path.basename(input_file_path) 
    output_filename_core = f"{original_basename}_ocr"
    
    output_filename_ext = OUTPUT_EXTENSIONS.get(output_mode, '.txt')
    final_output_filename = f"{output_filename_core}{output_filename_ext}" # "abc.pdf_ocr.md"

    if args_output_file:
        if num_total_inputs > 1 and os.path.isdir(args_output_file):
            return os.path.join(args_output_file, final_output_filename)
        elif num_total_inputs == 1 or not os.path.isdir(args_output_file): # Single input or output_file is a specific file path
            # If output_file is a dir for a single input, save inside it with the generated name
            if os.path.isdir(args_output_file) and num_total_inputs == 1:
                 return os.path.join(args_output_file, final_output_filename)
            return args_output_file # Assumed to be the exact full output file path desired by user
        else: # Fallback (should not be commonly reached if primary logic is sound)
             return os.path.join(base_output_dir_for_multiple_no_output_file_arg, final_output_filename)
    else: # No args_output_file, save to the determined base output directory
        return os.path.join(base_output_dir_for_multiple_no_output_file_arg, final_output_filename)

def setup_file_logger(log_dir, timestamp_str, debug_mode):
    """Sets up a file handler for logging."""
    log_file_name = f"{timestamp_str}.log"
    log_file_path = os.path.join(log_dir, log_file_name)

    file_handler = logging.FileHandler(log_file_path, mode='a') # Append mode
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    
    log_level = logging.DEBUG if debug_mode else logging.INFO
    file_handler.setLevel(log_level)
    
    # Add handler to our specific logger instance
    logger.addHandler(file_handler)
    logger.info(f"Logging to file: {log_file_path}")


def main():
    parser = argparse.ArgumentParser(
        description="VLM4OCR: Perform OCR on images, PDFs, or TIFF files using Vision Language Models. Processing is concurrent by default.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    io_group = parser.add_argument_group("Input/Output Options")
    io_group.add_argument("--input_path", required=True, help="Path to input file or directory.")
    io_group.add_argument("--output_mode", choices=["markdown", "HTML", "text"], default="markdown", help="Output format.")
    io_group.add_argument("--output_file", help="Optional: Path to save output. If input_path is a directory, this should be an output directory. If not provided, results saved to current working directory.")

    vlm_engine_group = parser.add_argument_group("VLM Engine Selection")
    vlm_engine_group.add_argument("--vlm_engine", choices=["openai", "azure_openai", "ollama", "openai_compatible"], required=True, help="VLM engine.")
    vlm_engine_group.add_argument("--model", required=True, help="Model identifier for the VLM engine.")

    openai_group = parser.add_argument_group("OpenAI & OpenAI-Compatible Options")
    openai_group.add_argument("--api_key", default=os.environ.get("OPENAI_API_KEY"), help="API key.")
    openai_group.add_argument("--base_url", help="Base URL for OpenAI-compatible services.")

    azure_group = parser.add_argument_group("Azure OpenAI Options")
    azure_group.add_argument("--azure_api_key", default=os.environ.get("AZURE_OPENAI_API_KEY"), help="Azure API key.")
    azure_group.add_argument("--azure_endpoint", default=os.environ.get("AZURE_OPENAI_ENDPOINT"), help="Azure endpoint URL.")
    azure_group.add_argument("--azure_api_version", default=os.environ.get("AZURE_OPENAI_API_VERSION"), help="Azure API version.")

    ollama_group = parser.add_argument_group("Ollama Options")
    ollama_group.add_argument("--ollama_host", default="http://localhost:11434", help="Ollama host URL.")
    ollama_group.add_argument("--ollama_num_ctx", type=int, default=4096, help="Context length for Ollama.")
    ollama_group.add_argument("--ollama_keep_alive", type=int, default=300, help="Ollama keep_alive seconds.")

    ocr_params_group = parser.add_argument_group("OCR Engine Parameters")
    ocr_params_group.add_argument("--user_prompt", help="Custom user prompt.")
    ocr_params_group.add_argument("--max_new_tokens", type=int, default=4096, help="Max new tokens for VLM.")
    ocr_params_group.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")

    processing_group = parser.add_argument_group("Processing Options")
    processing_group.add_argument(
        "--concurrent_batch_size",
        type=int,
        default=4,
        help="Number of images/pages to process concurrently. Set to 1 for sequential processing of VLM calls."
    )
    processing_group.add_argument("--debug", action="store_true", help="Enable debug level logging for console and file.")

    args = parser.parse_args()
    
    # --- Timestamp for logging and potentially output folders ---
    current_timestamp_str = time.strftime("%Y%m%d_%H%M%S")

    # --- Configure Logger Level based on args ---
    # Console logger level is set by basicConfig initially, then adjusted
    # The file logger level will be set in setup_file_logger
    if args.debug:
        logger.setLevel(logging.DEBUG) # Our specific logger
        logging.getLogger().setLevel(logging.DEBUG) # Root logger for other libs if needed
        logger.debug("Debug mode enabled for console.")
    else: # Default console level if not debug
        logger.setLevel(logging.INFO) # Or keep logging.INFO as per basicConfig
        logging.getLogger().setLevel(logging.WARNING)

    if args.concurrent_batch_size < 1:
        parser.error("--concurrent_batch_size must be 1 or greater.")

    # --- Determine Base Output Directory (for log file and default outputs) ---
    determined_output_dir = os.getcwd() # Default
    is_processing_multiple_files = False # Will be set after checking input_path

    if os.path.isdir(args.input_path):
        # Temporarily scan to check if multiple files will be processed for directory logic
        temp_files_list = [f for f in os.listdir(args.input_path) if os.path.isfile(os.path.join(args.input_path, f)) and os.path.splitext(f)[1].lower() in SUPPORTED_IMAGE_EXTS_CLI]
        if len(temp_files_list) > 1:
            is_processing_multiple_files = True
    elif os.path.isfile(args.input_path):
        is_processing_multiple_files = False # Single file

    if args.output_file:
        if is_processing_multiple_files: # Input is a dir with multiple files, output_file should be a dir
            if os.path.exists(args.output_file) and not os.path.isdir(args.output_file):
                logger.critical(f"Output path '{args.output_file}' exists and is not a directory, but multiple files are being processed. Please specify a valid directory for --output_file or omit it to use the current directory.")
                sys.exit(1)
            determined_output_dir = args.output_file
        else: # Single input file, output_file is a specific file path
            determined_output_dir = os.path.dirname(args.output_file)
            if not determined_output_dir: # If output_file is just a filename
                determined_output_dir = os.getcwd()
    
    if not os.path.exists(determined_output_dir):
        logger.info(f"Creating output directory for logs/results: {determined_output_dir}")
        os.makedirs(determined_output_dir, exist_ok=True)

    # --- Setup File Logger ---
    # Must be done after determined_output_dir is finalized.
    setup_file_logger(determined_output_dir, current_timestamp_str, args.debug)

    logger.debug(f"Parsed arguments: {args}") # Log after file logger is set up

    # --- Initialize VLM Engine ---
    vlm_engine_instance = None
    try:
        logger.info(f"Initializing VLM engine: {args.vlm_engine} with model: {args.model}")
        if args.vlm_engine == "openai":
            if not args.api_key: parser.error("--api_key (or OPENAI_API_KEY) is required for OpenAI.")
            vlm_engine_instance = OpenAIVLMEngine(model=args.model, api_key=args.api_key)
        elif args.vlm_engine == "openai_compatible":
            if not args.base_url: parser.error("--base_url is required for openai_compatible.")
            vlm_engine_instance = OpenAIVLMEngine(model=args.model, api_key=args.api_key, base_url=args.base_url)
        elif args.vlm_engine == "azure_openai":
            if not args.azure_api_key: parser.error("--azure_api_key (or AZURE_OPENAI_API_KEY) is required.")
            if not args.azure_endpoint: parser.error("--azure_endpoint (or AZURE_OPENAI_ENDPOINT) is required.")
            if not args.azure_api_version: parser.error("--azure_api_version (or AZURE_OPENAI_API_VERSION) is required.")
            vlm_engine_instance = AzureOpenAIVLMEngine(model=args.model, api_key=args.azure_api_key, azure_endpoint=args.azure_endpoint, api_version=args.azure_api_version)
        elif args.vlm_engine == "ollama":
            vlm_engine_instance = OllamaVLMEngine(model_name=args.model, host=args.ollama_host, num_ctx=args.ollama_num_ctx, keep_alive=args.ollama_keep_alive)
        logger.info("VLM engine initialized successfully.")
    except ImportError as e:
        logger.error(f"Failed to import library for {args.vlm_engine}: {e}. Install dependencies.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error initializing VLM engine '{args.vlm_engine}': {e}")
        if args.debug: logger.exception("Traceback:")
        sys.exit(1)

    # --- Initialize OCR Engine ---
    try:
        logger.info(f"Initializing OCR engine with output mode: {args.output_mode}")
        ocr_engine_instance = OCREngine(vlm_engine=vlm_engine_instance, output_mode=args.output_mode, user_prompt=args.user_prompt)
        logger.info("OCR engine initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing OCR engine: {e}")
        if args.debug: logger.exception("Traceback:")
        sys.exit(1)

    # --- Prepare input file paths (actual list) ---
    input_files_to_process = []
    if os.path.isdir(args.input_path):
        logger.info(f"Input is directory: {args.input_path}. Scanning for files...")
        for item in os.listdir(args.input_path):
            item_path = os.path.join(args.input_path, item)
            if os.path.isfile(item_path) and os.path.splitext(item)[1].lower() in SUPPORTED_IMAGE_EXTS_CLI:
                input_files_to_process.append(item_path)
        if not input_files_to_process:
            logger.error(f"No supported files found in directory: {args.input_path}")
            sys.exit(1)
        logger.info(f"Found {len(input_files_to_process)} files to process.")
    elif os.path.isfile(args.input_path):
        if os.path.splitext(args.input_path)[1].lower() not in SUPPORTED_IMAGE_EXTS_CLI:
            logger.error(f"Input file '{args.input_path}' is not supported. Supported: {SUPPORTED_IMAGE_EXTS_CLI}")
            sys.exit(1)
        input_files_to_process = [args.input_path]
        logger.info(f"Processing single input file: {args.input_path}")
    else:
        logger.error(f"Input path not valid: {args.input_path}")
        sys.exit(1)
    
    # --- Run OCR ---
    try:
        logger.info(f"Processing with concurrent_batch_size: {args.concurrent_batch_size}.")

        async def process_and_write_concurrently():
            ocr_task_generator = ocr_engine_instance.concurrent_ocr(
                file_paths=input_files_to_process,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                concurrent_batch_size=args.concurrent_batch_size
            )
            
            # Progress bar shown only if multiple files are being processed OR single file (tqdm handles total=1 well)
            show_progress_bar = (len(input_files_to_process) > 0)

            iterator_wrapper = tqdm.asyncio.tqdm(
                ocr_task_generator, 
                total=len(input_files_to_process), 
                desc="Processing files", 
                unit="file",
                disable=not show_progress_bar 
            )
            
            async for result_object in iterator_wrapper:
                if not isinstance(result_object, OCRResult):
                    logger.warning(f"Received unexpected data type: {type(result_object)}")
                    continue

                input_file_path_from_result = result_object.input_dir
                current_output_file_path = get_output_path(
                    input_file_path_from_result, args.output_file, args.output_mode,
                    len(input_files_to_process), determined_output_dir # Pass the correctly determined base output dir
                )
                
                if result_object.status == "error":
                    error_message = result_object.pages[0] if result_object.pages else 'Unknown error during OCR'
                    logger.error(f"OCR failed for {result_object.filename}: {error_message}")
                    # Error is already logged to console and file by logger.error
                else:
                    try:
                        content_to_write = result_object.to_string()
                        with open(current_output_file_path, "w", encoding="utf-8") as f:
                            f.write(content_to_write)
                        # Log successful save, but not if tqdm is active and providing feedback
                        if not show_progress_bar:
                           logger.info(f"OCR result for '{input_file_path_from_result}' saved to: {current_output_file_path}")
                    except Exception as e:
                        logger.error(f"Error writing output for '{input_file_path_from_result}' to '{current_output_file_path}': {e}")
            
            if hasattr(iterator_wrapper, 'close') and isinstance(iterator_wrapper, tqdm.asyncio.tqdm):
                # This ensures the pbar finishes cleanly if the loop exits early or there are few items
                if iterator_wrapper.n < iterator_wrapper.total:
                    iterator_wrapper.n = iterator_wrapper.total # Force to 100%
                    iterator_wrapper.refresh()
                iterator_wrapper.close()


        try:
            asyncio.run(process_and_write_concurrently())
        except RuntimeError as e:
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                logger.warning("asyncio.run() error. Attempting to use existing loop.")
                loop = asyncio.get_event_loop_policy().get_event_loop()
                if loop.is_running():
                     logger.critical("Cannot execute in current asyncio context. If in Jupyter, try 'import nest_asyncio; nest_asyncio.apply()'.")
                     sys.exit(1)
                else:
                    loop.run_until_complete(process_and_write_concurrently())
            else: raise e
            
        logger.info("All processing finished.")

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        if args.debug: logger.exception("Traceback:")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Input/Value Error: {e}")
        if args.debug: logger.exception("Traceback:")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during main processing: {e}")
        if args.debug: logger.exception("Traceback:")
        sys.exit(1)

if __name__ == "__main__":
    main()