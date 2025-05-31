import argparse
import os
import sys
import logging
import asyncio
import time

# Attempt to import from the local package structure
try:
    from .ocr_engines import OCREngine
    from .vlm_engines import OpenAIVLMEngine, AzureOpenAIVLMEngine, OllamaVLMEngine, BasicVLMConfig
    from .data_types import OCRResult
except ImportError:
    # Fallback for when the package is installed
    from vlm4ocr.ocr_engines import OCREngine
    from vlm4ocr.vlm_engines import OpenAIVLMEngine, AzureOpenAIVLMEngine, OllamaVLMEngine, BasicVLMConfig
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

def get_output_path_for_ocr_result(input_file_path, specified_output_path_arg, output_mode, num_total_inputs, base_output_dir_if_no_specific_path):
    """
    Determines the full output path for a given OCR result file.
    Output filename format: <original_basename>_ocr.<new_extension>
    Example: input "abc.pdf", output_mode "markdown" -> "abc.pdf_ocr.md"
    """
    original_basename = os.path.basename(input_file_path) 
    output_filename_core = f"{original_basename}_ocr"
    
    output_filename_ext = OUTPUT_EXTENSIONS.get(output_mode, '.txt')
    final_output_filename = f"{output_filename_core}{output_filename_ext}"

    if specified_output_path_arg: # If --output_path is used
        # Scenario 1: Multiple input files, --output_path is expected to be a directory.
        if num_total_inputs > 1 and os.path.isdir(specified_output_path_arg):
            return os.path.join(specified_output_path_arg, final_output_filename)
        # Scenario 2: Single input file.
        # --output_path could be a full file path OR a directory.
        elif num_total_inputs == 1:
            if os.path.isdir(specified_output_path_arg): # If --output_path is a directory for the single file
                return os.path.join(specified_output_path_arg, final_output_filename)
            else: # If --output_path is a specific file name for the single file
                return specified_output_path_arg 
        # Scenario 3: Multiple input files, but --output_path is NOT a directory (error, handled before this fn)
        # or other edge cases, fall back to base_output_dir_if_no_specific_path
        else: 
             return os.path.join(base_output_dir_if_no_specific_path, final_output_filename)
    else: # No --output_path, save to the determined base output directory
        return os.path.join(base_output_dir_if_no_specific_path, final_output_filename)

def setup_file_logger(log_dir, timestamp_str, debug_mode):
    """Sets up a file handler for logging."""
    log_file_name = f"vlm4ocr_{timestamp_str}.log"
    log_file_path = os.path.join(log_dir, log_file_name)

    file_handler = logging.FileHandler(log_file_path, mode='a')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    
    log_level = logging.DEBUG if debug_mode else logging.INFO
    file_handler.setLevel(log_level)
    
    logger.addHandler(file_handler)
    logger.info(f"Logging to file: {log_file_path}")


def main():
    parser = argparse.ArgumentParser(
        description="VLM4OCR: Perform OCR on images, PDFs, or TIFF files using Vision Language Models. Processing is concurrent by default.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    io_group = parser.add_argument_group("Input/Output Options")
    io_group.add_argument("--input_path", required=True, help="Path to a single input file or a directory of files.")
    io_group.add_argument("--output_mode", choices=["markdown", "HTML", "text"], default="markdown", help="Output format.")
    io_group.add_argument("--output_path", help="Optional: Path to save OCR results. If input_path is a directory of multiple files, this should be an output directory. If input is a single file, this can be a full file path or a directory. If not provided, results are saved to the current working directory (or a sub-directory for logs if --log is used).")
    io_group.add_argument("--skip_existing", action="store_true", help="Skip processing files that already have OCR results in the output directory.")

    image_processing_group = parser.add_argument_group("Image Processing Parameters")
    image_processing_group.add_argument(
        "--rotate_correction",
        action="store_true",
        help="Enable automatic rotation correction for input images. This requires Tesseract OCR to be installed and configured correctly.")
    image_processing_group.add_argument(
        "--max_dimension_pixels",
        type=int,
        default=4000,
        help="Maximum dimension (width or height) in pixels for input images. Images larger than this will be resized to fit within this limit while maintaining aspect ratio."
    )

    vlm_engine_group = parser.add_argument_group("VLM Engine Options")
    vlm_engine_group.add_argument("--vlm_engine", choices=["openai", "azure_openai", "ollama", "openai_compatible"], required=True, help="VLM engine.")
    vlm_engine_group.add_argument("--model", required=True, help="Model identifier for the VLM engine.")
    vlm_engine_group.add_argument("--max_new_tokens", type=int, default=4096, help="Max new tokens for VLM.")
    vlm_engine_group.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")

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

    processing_group = parser.add_argument_group("Processing Options")
    processing_group.add_argument(
        "--concurrent_batch_size",
        type=int,
        default=4,
        help="Number of images/pages to process concurrently. Set to 1 for sequential processing of VLM calls."
    )
    processing_group.add_argument(
        "--max_file_load",
        type=int,
        default=-1,
        help="Number of input files to pre-load. Set to -1 for automatic config: 2 * concurrent_batch_size."
    )
    # --verbose flag was removed by user in previous version provided
    processing_group.add_argument("--log", action="store_true", help="Enable writing logs to a timestamped file in the output directory.")
    processing_group.add_argument("--debug", action="store_true", help="Enable debug level logging for console (and file if --log is active).")

    args = parser.parse_args()
    
    current_timestamp_str = time.strftime("%Y%m%d_%H%M%S")

    # --- Configure Logger Level based on args ---
    if args.debug:
        logger.setLevel(logging.DEBUG)
        # Set root logger to DEBUG only if our specific logger is DEBUG, to avoid overly verbose library logs unless intended.
        if logger.getEffectiveLevel() <= logging.DEBUG:
            logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled for console.")
    else:
        logger.setLevel(logging.INFO) # Default for our CLI's own messages
        logging.getLogger().setLevel(logging.WARNING) # Keep external libraries quieter by default

    if args.concurrent_batch_size < 1:
        parser.error("--concurrent_batch_size must be 1 or greater.")

    # --- Determine Effective Output Directory (for logs and default OCR outputs) ---
    effective_output_dir = os.getcwd() # Default if no --output_path
    
    # Preliminary check to see if multiple files will be processed
    _is_multi_file_scenario = False
    if os.path.isdir(args.input_path):
        _temp_files_list = [f for f in os.listdir(args.input_path) if os.path.isfile(os.path.join(args.input_path, f)) and os.path.splitext(f)[1].lower() in SUPPORTED_IMAGE_EXTS_CLI]
        if len(_temp_files_list) > 1:
            _is_multi_file_scenario = True
            
    if args.output_path:
        if _is_multi_file_scenario: # Input is a dir with multiple files
            if os.path.exists(args.output_path) and not os.path.isdir(args.output_path):
                logger.critical(f"Output path '{args.output_path}' must be a directory when processing multiple files. It currently points to a file.")
                sys.exit(1)
            effective_output_dir = args.output_path # --output_path is the directory for outputs and logs
        else: # Single input file scenario
            # If args.output_path is a directory, use it.
            # If args.output_path is a file path, use its directory for logs.
            if os.path.isdir(args.output_path):
                effective_output_dir = args.output_path
            else: # Assumed to be a file path
                dir_name = os.path.dirname(args.output_path)
                if dir_name: # If output_path includes a directory
                    effective_output_dir = dir_name
                else: # output_path is just a filename, logs go to CWD
                    effective_output_dir = os.getcwd()
    
    if not os.path.exists(effective_output_dir):
        logger.info(f"Creating output directory: {effective_output_dir}")
        os.makedirs(effective_output_dir, exist_ok=True)

    # --- Setup File Logger (if --log is specified) ---
    if args.log:
        setup_file_logger(effective_output_dir, current_timestamp_str, args.debug)

    logger.debug(f"Parsed arguments: {args}")

    # --- Initialize VLM Engine ---
    vlm_engine_instance = None
    try:
        logger.info(f"Initializing VLM engine: {args.vlm_engine} with model: {args.model}")
        config = BasicVLMConfig(
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature
        )
        if args.vlm_engine == "openai":
            if not args.api_key: parser.error("--api_key (or OPENAI_API_KEY) is required for OpenAI.")
            vlm_engine_instance = OpenAIVLMEngine(model=args.model, api_key=args.api_key, config=config)
        elif args.vlm_engine == "openai_compatible":
            if not args.base_url: parser.error("--base_url is required for openai_compatible.")
            vlm_engine_instance = OpenAIVLMEngine(model=args.model, api_key=args.api_key, base_url=args.base_url, config=config)
        elif args.vlm_engine == "azure_openai":
            if not args.azure_api_key: parser.error("--azure_api_key (or AZURE_OPENAI_API_KEY) is required.")
            if not args.azure_endpoint: parser.error("--azure_endpoint (or AZURE_OPENAI_ENDPOINT) is required.")
            if not args.azure_api_version: parser.error("--azure_api_version (or AZURE_OPENAI_API_VERSION) is required.")
            vlm_engine_instance = AzureOpenAIVLMEngine(model=args.model, api_key=args.azure_api_key, azure_endpoint=args.azure_endpoint, api_version=args.azure_api_version, config=config)
        elif args.vlm_engine == "ollama":
            vlm_engine_instance = OllamaVLMEngine(model_name=args.model, host=args.ollama_host, num_ctx=args.ollama_num_ctx, keep_alive=args.ollama_keep_alive, config=config)
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
    
    # --- Skip existing files if --skip_existing is used ---
    if args.skip_existing:
        logger.info("Checking for existing OCR results in output path to skip...")        
        # Check each input file against the expected output file
        existing_files = os.listdir(effective_output_dir)
        filtered_input_files_to_process = []
        for input_file in input_files_to_process:
            expected_output_name = get_output_path_for_ocr_result(input_file, args.output_path, args.output_mode, len(input_files_to_process), effective_output_dir)
            if os.path.basename(expected_output_name) not in existing_files:
                filtered_input_files_to_process.append(input_file)

        original_num_files = len(input_files_to_process)
        after_filter_num_files = len(filtered_input_files_to_process)
        input_files_to_process = filtered_input_files_to_process
        logger.info(f"Dropped {original_num_files - after_filter_num_files} existing files. Number of input files to process after filtering: {len(input_files_to_process)}")

    else:
        logger.info("All input files will be processed (`--skip_existing=False`).")
    # This re-evaluation is useful if the initial _is_multi_file_scenario was just for log dir
    num_actual_files = len(input_files_to_process)

    # --- Run OCR ---
    try:
        logger.info(f"Processing with concurrent_batch_size: {args.concurrent_batch_size}.")

        async def process_and_write_concurrently():
            ocr_task_generator = ocr_engine_instance.concurrent_ocr(
                file_paths=input_files_to_process,
                rotate_correction=args.rotate_correction,
                max_dimension_pixels=args.max_dimension_pixels,
                concurrent_batch_size=args.concurrent_batch_size,
                max_file_load=args.max_file_load if args.max_file_load > 0 else None
            )
            
            # Progress bar always attempted if tqdm is available and files exist,
            # console verbosity controlled by logger level.
            show_progress_bar = (num_actual_files > 0) 

            iterator_wrapper = tqdm.asyncio.tqdm(
                ocr_task_generator, 
                total=num_actual_files, 
                desc="Processing files", 
                unit="file",
                disable=not show_progress_bar # disable if no files, or can remove this disable if tqdm handles total=0
            )
            
            async for result_object in iterator_wrapper:
                if not isinstance(result_object, OCRResult):
                    logger.warning(f"Received unexpected data type: {type(result_object)}")
                    continue

                input_file_path_from_result = result_object.input_dir
                # For get_output_path_for_ocr_result, effective_output_dir is the base if args.output_path isn't specific enough
                current_ocr_output_file_path = get_output_path_for_ocr_result(
                    input_file_path_from_result, args.output_path, args.output_mode,
                    num_actual_files, effective_output_dir 
                )
                
                if result_object.status == "error":
                    error_message = result_object.get_page(0) if len(result_object) > 0 else 'Unknown error during OCR'
                    logger.error(f"OCR failed for {result_object.filename}: {error_message}")
                else:
                    try:
                        content_to_write = result_object.to_string()
                        with open(current_ocr_output_file_path, "w", encoding="utf-8") as f:
                            f.write(content_to_write)
                        # Log less verbosely to console if progress bar is active
                        if not show_progress_bar or logger.getEffectiveLevel() <= logging.DEBUG:
                           logger.info(f"OCR result for '{input_file_path_from_result}' saved to: {current_ocr_output_file_path}")
                    except Exception as e:
                        logger.error(f"Error writing output for '{input_file_path_from_result}' to '{current_ocr_output_file_path}': {e}")
            
            if hasattr(iterator_wrapper, 'close') and isinstance(iterator_wrapper, tqdm.asyncio.tqdm):
                if iterator_wrapper.n < iterator_wrapper.total:
                    iterator_wrapper.n = iterator_wrapper.total 
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