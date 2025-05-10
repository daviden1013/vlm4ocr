# vlm4ocr/cli.py

import argparse
import os
import sys
import logging

# Attempt to import from the local package structure
# This allows running the script directly for development,
# assuming the script is in vlm4ocr/vlm4ocr/cli.py and the package root is vlm4ocr/vlm4ocr
try:
    from .ocr_engines import OCREngine 
    from .vlm_engines import OpenAIVLMEngine, AzureOpenAIVLMEngine, OllamaVLMEngine
except ImportError:
    # Fallback for when the package is installed and cli.py is run as part of it
    from vlm4ocr.ocr_engines import OCREngine
    from vlm4ocr.vlm_engines import OpenAIVLMEngine, AzureOpenAIVLMEngine, OllamaVLMEngine

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Define supported extensions here, ideally this should be sourced from ocr_engines.py
SUPPORTED_IMAGE_EXTS_CLI = ['.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']
OUTPUT_EXTENSIONS = {'markdown': '.md', 'HTML':'.html', 'text':'txt'}

def main():
    """
    Main function for the vlm4ocr CLI.
    Parses arguments, initializes engines, runs OCR, and handles output.
    """
    parser = argparse.ArgumentParser(
        description="VLM4OCR: Perform OCR on images, PDFs, or TIFF files using Vision Language Models.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter 
    )

    # --- Input/Output Arguments ---
    io_group = parser.add_argument_group("Input/Output Options")
    io_group.add_argument(
        "--input_path",
        required=True,
        help="Path to the input image, PDF, or TIFF file, or a directory containing these files. " 
             "If a directory is provided, all supported files within will be processed."
    )
    io_group.add_argument(
        "--output_mode",
        choices=["markdown", "HTML", "text"],
        default="markdown",
        help="Desired output format for the OCR results."
    )
    io_group.add_argument(
        "--output_file",
        help="Optional: Path to a file to save the output. "
             "If input_path is a directory, this should be a directory where results will be saved "
             "(one file per input, with original name and new extension). "
             "If not provided, output is written to files in the current working directory "
             "(e.g., 'input_name_ocr.output_mode')."
    )

    # --- VLM Engine Selection ---
    vlm_engine_group = parser.add_argument_group("VLM Engine Selection")
    vlm_engine_group.add_argument(
        "--vlm_engine",
        choices=["openai", "azure_openai", "ollama", "openai_compatible"],
        required=True,
        help="Specify the VLM engine to use."
    )
    vlm_engine_group.add_argument( 
        "--model",
        required=True,
        help="The specific model identifier for the chosen VLM engine. "
             "E.g., 'gpt-4o' for OpenAI, 'deployment-name' for Azure, "
             "'Qwen/Qwen2.5-VL-7B-Instruct' for OpenAI-compatible, "
             "or 'llava:latest' for Ollama."
    )

    # --- OpenAI Engine Arguments ---
    openai_group = parser.add_argument_group("OpenAI & OpenAI-Compatible Options")
    openai_group.add_argument(
        "--api_key",
        default=os.environ.get("OPENAI_API_KEY"), 
        help="API key for OpenAI or OpenAI-compatible service. "
             "Can also be set via OPENAI_API_KEY environment variable."
    )
    openai_group.add_argument(
        "--base_url",
        help="Base URL for OpenAI-compatible services (e.g., vLLM endpoint like 'http://localhost:8000/v1'). "
             "Not used for official OpenAI API."
    )

    # --- Azure OpenAI Engine Arguments ---
    azure_group = parser.add_argument_group("Azure OpenAI Options")
    azure_group.add_argument(
        "--azure_api_key",
        default=os.environ.get("AZURE_OPENAI_API_KEY"), 
        help="API key for Azure OpenAI service. "
             "Can also be set via AZURE_OPENAI_API_KEY environment variable."
    )
    azure_group.add_argument(
        "--azure_endpoint",
        default=os.environ.get("AZURE_OPENAI_ENDPOINT"), 
        help="Endpoint URL for Azure OpenAI service. "
             "Can also be set via AZURE_OPENAI_ENDPOINT environment variable."
    )
    azure_group.add_argument(
        "--azure_api_version",
        default=os.environ.get("AZURE_OPENAI_API_VERSION"), 
        help="API version for Azure OpenAI service (e.g., '2024-02-01'). "
             "Can also be set via AZURE_OPENAI_API_VERSION environment variable."
    )

    # --- Ollama Engine Arguments ---
    ollama_group = parser.add_argument_group("Ollama Options")
    ollama_group.add_argument(
        "--ollama_host",
        default="http://localhost:11434",
        help="Host URL for the Ollama server."
    )
    ollama_group.add_argument(
        "--ollama_num_ctx",
        type=int,
        default=4096,
        help="Context length for Ollama models."
    )
    ollama_group.add_argument(
        "--ollama_keep_alive",
        type=int,
        default=300, # Default from OllamaVLMEngine
        help="Seconds to keep the Ollama model loaded after the last call."
    )


    # --- OCR Engine Parameters ---
    ocr_params_group = parser.add_argument_group("OCR Engine Parameters")
    ocr_params_group.add_argument(
        "--user_prompt",
        help="Optional: Custom user prompt to provide context about the image/PDF/TIFF."
    )
    # REMOVED --system_prompt argument
    ocr_params_group.add_argument(
        "--max_new_tokens",
        type=int,
        default=4096, # Default from OCREngine
        help="Maximum number of new tokens the VLM can generate."
    )
    ocr_params_group.add_argument(
        "--temperature",
        type=float,
        default=0.0, # Default from OCREngine
        help="Temperature for token sampling (0.0 for deterministic output)."
    )

    # --- Processing Options ---
    processing_group = parser.add_argument_group("Processing Options")
    processing_group.add_argument(
        "--concurrent",
        action="store_true", 
        help="Enable concurrent processing for multiple files or PDF/TIFF pages."
    )
    processing_group.add_argument(
        "--concurrent_batch_size",
        type=int,
        default=32, 
        help="Batch size for concurrent processing."
    )
    processing_group.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output from the OCR engine during processing. CLI will also log more info."
    )
    processing_group.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug level logging for more detailed information."
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG) 
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled.")
        logger.debug(f"Parsed arguments: {args}")
    elif args.verbose: 
        logger.setLevel(logging.INFO) # Ensure logger level is at least INFO for verbose CLI output

    # --- Validate Arguments ---
    # verbose is not supported with concurrent processing
    if args.verbose and args.concurrent:
        logger.warning("Verbose output is not supported with concurrent processing. "
                       "Verbose mode will be ignored.")
        args.verbose = False
        
    # --- Initialize VLM Engine ---
    vlm_engine_instance = None
    try:
        logger.info(f"Initializing VLM engine: {args.vlm_engine} with model: {args.model}")
        if args.vlm_engine == "openai":
            if not args.api_key:
                parser.error("--api_key (or OPENAI_API_KEY env var) is required for OpenAI engine.")
            vlm_engine_instance = OpenAIVLMEngine(
                model=args.model,
                api_key=args.api_key
                # reasoning_model removed
            )
        elif args.vlm_engine == "openai_compatible":
            if not args.api_key : 
                 logger.warning("API key not provided or empty for openai_compatible. This might be acceptable for some servers (e.g. if 'EMPTY' is expected).")
            if not args.base_url:
                parser.error("--base_url is required for openai_compatible engine.")
            vlm_engine_instance = OpenAIVLMEngine(
                model=args.model,
                api_key=args.api_key, 
                base_url=args.base_url
                # reasoning_model removed
            )
        elif args.vlm_engine == "azure_openai":
            if not args.azure_api_key:
                parser.error("--azure_api_key (or AZURE_OPENAI_API_KEY env var) is required for Azure OpenAI engine.")
            if not args.azure_endpoint:
                parser.error("--azure_endpoint (or AZURE_OPENAI_ENDPOINT env var) is required for Azure OpenAI engine.")
            if not args.azure_api_version:
                parser.error("--azure_api_version (or AZURE_OPENAI_API_VERSION env var) is required for Azure OpenAI engine.")
            vlm_engine_instance = AzureOpenAIVLMEngine(
                model=args.model, 
                api_key=args.azure_api_key,
                azure_endpoint=args.azure_endpoint,
                api_version=args.azure_api_version
                # reasoning_model removed
            )
        elif args.vlm_engine == "ollama":
            vlm_engine_instance = OllamaVLMEngine(
                model_name=args.model, # OllamaVLMEngine expects model_name
                host=args.ollama_host,
                num_ctx=args.ollama_num_ctx,
                keep_alive=args.ollama_keep_alive
            )
        else:
            # This case should be caught by argparse choices, but as a safeguard:
            logger.error(f"Invalid VLM engine specified: {args.vlm_engine}")
            sys.exit(1)
        logger.info("VLM engine initialized successfully.")

    except ImportError as e:
        logger.error(f"Failed to import a required library for {args.vlm_engine}: {e}. "
                     "Please ensure the necessary dependencies (e.g., 'openai', 'ollama') are installed.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error initializing VLM engine '{args.vlm_engine}': {e}")
        if args.debug:
            logger.exception("Traceback for VLM engine initialization error:")
        sys.exit(1)

    # --- Initialize OCR Engine ---
    try:
        logger.info(f"Initializing OCR engine with output mode: {args.output_mode}")
        ocr_engine_instance = OCREngine(
            vlm_engine=vlm_engine_instance,
            output_mode=args.output_mode,
            # system_prompt removed, OCREngine will use its default
            user_prompt=args.user_prompt      
        )
        logger.info("OCR engine initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing OCR engine: {e}")
        if args.debug:
            logger.exception("Traceback for OCR engine initialization error:")
        sys.exit(1)

    # --- Prepare input file paths ---
    input_files_to_process = []
    if os.path.isdir(args.input_path):
        logger.info(f"Input path is a directory: {args.input_path}. Scanning for supported files...")
        for item in os.listdir(args.input_path):
            item_path = os.path.join(args.input_path, item)
            if os.path.isfile(item_path):
                file_ext = os.path.splitext(item)[1].lower()
                if file_ext in SUPPORTED_IMAGE_EXTS_CLI: 
                    input_files_to_process.append(item_path)
        if not input_files_to_process:
            logger.error(f"No supported files (PDF, TIFF, PNG, JPG, etc.) found in directory: {args.input_path}")
            sys.exit(1)
        logger.info(f"Found {len(input_files_to_process)} supported files to process.")
    elif os.path.isfile(args.input_path):
        file_ext = os.path.splitext(args.input_path)[1].lower()
        if file_ext not in SUPPORTED_IMAGE_EXTS_CLI:
            logger.error(f"Input file '{args.input_path}' is not a supported file type. Supported: {SUPPORTED_IMAGE_EXTS_CLI}")
            sys.exit(1)
        input_files_to_process = [args.input_path]
        logger.info(f"Processing single input file: {args.input_path}")
    else:
        logger.error(f"Input path is not a valid file or directory: {args.input_path}")
        sys.exit(1)


    # --- Run OCR ---
    try:
        logger.info("Starting OCR processing...")
        ocr_results_list = ocr_engine_instance.run_ocr(
            file_paths=input_files_to_process,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            verbose=args.verbose, 
            concurrent=args.concurrent,
            concurrent_batch_size=args.concurrent_batch_size
        )
        logger.info("OCR processing completed.")

        # --- Handle Output ---
        if args.output_file:
            if os.path.isdir(args.input_path) and len(input_files_to_process) > 1 : 
                if not os.path.exists(args.output_file):
                    logger.info(f"Creating output directory: {args.output_file}")
                    os.makedirs(args.output_file, exist_ok=True)
                elif not os.path.isdir(args.output_file):
                    logger.error(f"Output path '{args.output_file}' exists and is not a directory, "
                                 "but multiple input files were processed. Please specify a directory for --output_file.")
                    sys.exit(1)
                
                output_target_dir = args.output_file
            elif not (os.path.isdir(args.input_path) and len(input_files_to_process) > 1):
                # Single input file, or directory with one file. output_file is a direct file path.
                # Ensure its directory exists.
                output_target_dir = os.path.dirname(args.output_file)
                if output_target_dir and not os.path.exists(output_target_dir):
                    logger.info(f"Creating output directory: {output_target_dir}")
                    os.makedirs(output_target_dir, exist_ok=True)
            else: # Should not happen if logic above is correct
                output_target_dir = os.getcwd()


            for i, input_file_path in enumerate(input_files_to_process):
                if os.path.isdir(args.input_path) and len(input_files_to_process) > 1:
                    # Multiple inputs, save into the directory specified by args.output_file
                    base_name = os.path.basename(input_file_path)
                    name_part, _ = os.path.splitext(base_name)
                    output_filename = f"{name_part}_ocr{OUTPUT_EXTENSIONS[args.output_mode]}"
                    full_output_path = os.path.join(args.output_file, output_filename)
                else:
                    # Single input, args.output_file is the exact path
                    full_output_path = args.output_file
                
                try:
                    with open(full_output_path, "w", encoding="utf-8") as f:
                        f.write(ocr_results_list[i])
                    logger.info(f"OCR result for '{input_file_path}' saved to: {full_output_path}")
                except Exception as e:
                    logger.error(f"Error writing output for '{input_file_path}' to '{full_output_path}': {e}")
        else:
            # No --output_file specified, save to current working directory
            current_dir = os.getcwd()
            logger.info(f"No --output_file specified. Results will be saved to the current working directory: {current_dir}")
            for i, input_file_path in enumerate(input_files_to_process):
                base_name = os.path.basename(input_file_path)
                name_part, _ = os.path.splitext(base_name)
                output_filename = f"{name_part}_ocr{OUTPUT_EXTENSIONS[args.output_mode]}"
                full_output_path = os.path.join(current_dir, output_filename)
                try:
                    with open(full_output_path, "w", encoding="utf-8") as f:
                        f.write(ocr_results_list[i])
                    logger.info(f"OCR result for '{input_file_path}' saved to: {full_output_path}")
                except Exception as e:
                    logger.error(f"Error writing output for '{input_file_path}' to '{full_output_path}': {e}")

    except FileNotFoundError as e:
        logger.error(f"File not found during OCR processing: {e}")
        sys.exit(1)
    except ValueError as e: 
        logger.error(f"Input Error or Value Error during processing: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during OCR processing: {e}")
        if args.debug:
            logger.exception("Traceback for OCR processing error:")
        sys.exit(1)

if __name__ == "__main__":
    main()
