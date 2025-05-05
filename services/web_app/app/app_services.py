import os
import traceback
from werkzeug.utils import secure_filename
from flask import Response, stream_with_context
from . import app, cleanup_file


try:
    from vlm4ocr.ocr_engines import OCREngine
    from vlm4ocr.vlm_engines import OpenAIVLMEngine, AzureOpenAIVLMEngine, OllamaVLMEngine
except ImportError as e:
    print(f"Error importing from vlm4ocr in app_services.py: {e}")
    raise

def process_ocr_request(request):
    """
    Handles the core logic for an OCR request.
    - Validates input file.
    - Saves the file temporarily.
    - Initializes VLM and OCR engines based on form data (validating required API keys).
    - Uses default system prompt from OCREngine.
    - Returns a streaming Flask Response.
    - Ensures cleanup of the temporary file.
    """
    print("Entering app_services.process_ocr_request")
    temp_file_path = None
    vlm_engine = None
    ocr_engine = None

    try:
        # 1. File Validation (remains the same)
        if 'input_file' not in request.files:
            raise ValueError("No input file part in request")
        file = request.files['input_file']
        if not file or file.filename == '':
            raise ValueError("No selected file")

        # 2. Save File Securely (remains the same)
        filename = secure_filename(file.filename)
        temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        print(f"Saving temporary file to: {temp_file_path}")
        file.save(temp_file_path)
        print("Temporary file saved.")

        # 3. Get Form Data (remains the same)
        vlm_api = request.form.get('vlm_api', '')
        user_prompt = request.form.get('ocr_user_prompt', None)
        vlm_model_compatible = request.form.get('vlm_model', None)
        openai_model_openai = request.form.get('openai_model', None)
        azure_deployment_name = request.form.get('azure_deployment_name', None)
        vlm_base_url = request.form.get('vlm_base_url', None)
        azure_endpoint = request.form.get('azure_endpoint', None)
        azure_api_version = request.form.get('azure_api_version', None)
        ollama_host = request.form.get('ollama_host', 'http://localhost:11434')
        ollama_model = request.form.get('ollama_model', None)

        print(f"Extracted form data: vlm_api={vlm_api}")

        # 4. Initialize VLM Engine (Added API key validation for compatible mode)
        print("Initializing VLM Engine...")
        vlm_api_key = None
        if vlm_api == "openai_compatible":
            vlm_api_key = request.form.get('openai_compatible_api_key', None)
            # --- ADDED VALIDATION ---
            if not vlm_api_key: raise ValueError("API Key is required for OpenAI Compatible mode.")
            # --- END ADDED VALIDATION ---
            if not vlm_model_compatible: raise ValueError("Model name is required for OpenAI Compatible mode.")
            if not vlm_base_url: raise ValueError("Base URL is required for OpenAI Compatible mode.")
            print(f"Configuring OpenAIVLMEngine (Compatible): model={vlm_model_compatible}, base_url={vlm_base_url}")
            vlm_engine = OpenAIVLMEngine(
                model=vlm_model_compatible,
                # Use the specific required key, removed 'or "EMPTY"'
                api_key=vlm_api_key,
                base_url=vlm_base_url
            )
        elif vlm_api == "openai":
            vlm_api_key = request.form.get('openai_api_key', None)
            if not openai_model_openai: raise ValueError("Model name is required for OpenAI mode.")
            if not vlm_api_key: raise ValueError("OpenAI API Key is required for OpenAI mode.")
            print(f"Configuring OpenAIVLMEngine (OpenAI): model={openai_model_openai}")
            vlm_engine = OpenAIVLMEngine(model=openai_model_openai, api_key=vlm_api_key)
        elif vlm_api == "azure_openai":
            vlm_api_key = request.form.get('azure_openai_api_key', None)
            if not azure_deployment_name: raise ValueError("Model/Deployment Name is required for Azure OpenAI mode.")
            if not azure_endpoint: raise ValueError("Azure Endpoint is required for Azure OpenAI mode.")
            if not azure_api_version: raise ValueError("Azure API Version is required for Azure OpenAI mode.")
            if not vlm_api_key: raise ValueError("Azure API Key is required for Azure OpenAI mode.")
            print(f"Configuring AzureOpenAIVLMEngine: model={azure_deployment_name}, endpoint={azure_endpoint}, api_version={azure_api_version}")
            vlm_engine = AzureOpenAIVLMEngine(model=azure_deployment_name, api_key=vlm_api_key, azure_endpoint=azure_endpoint, api_version=azure_api_version)
        elif vlm_api == "ollama": 
            if not ollama_model: raise ValueError("Model name is required for Ollama mode.")
            host_to_use = ollama_host if ollama_host else 'http://localhost:11434'
            print(f"Configuring OllamaVLMEngine: model={ollama_model}, host={host_to_use}")
            vlm_engine = OllamaVLMEngine(
                model_name=ollama_model,
                host=host_to_use
            )
        
        else:
            raise ValueError(f'Unsupported VLM API type selected: {vlm_api}')
        print("VLM Engine configured.")

        # 5. Initialize OCREngine (remains the same)
        print("Initializing OCREngine...")
        ocr_engine = OCREngine(
            vlm_engine=vlm_engine,
            output_mode="markdown",
            system_prompt=None,
            user_prompt=user_prompt,
            page_delimiter="\n\n---\n\n"
        )
        print("OCREngine initialized.")

        # 6. Define the Streaming Generator (remains the same)
        def generate_ocr_stream(ocr_eng, file_to_process):
            print(f"generate_ocr_stream called for: {file_to_process}")
            try:
                print(f"Starting OCREngine.stream_ocr for: {file_to_process}")
                yield from ocr_eng.stream_ocr(file_path=file_to_process)
                print(f"Finished OCREngine.stream_ocr for: {file_to_process}")
            except ValueError as val_err:
                print(f"--- Value Error during OCR stream: {val_err} ---")
                traceback.print_exc()
                yield f"\n\n[STREAMING ERROR] {val_err}\n\n"
            except Exception as stream_err:
                print(f"--- Error Traceback during OCR stream generation ---")
                traceback.print_exc()
                yield f"\n\n[STREAMING ERROR] Failed to process: {stream_err}\n\n"
            finally:
                print(f"Calling cleanup_file from generate_ocr_stream finally block for {file_to_process}")
                cleanup_file(file_to_process, "post-stream cleanup")

        # 7. Return Streaming Response (remains the same)
        print("Setup complete. Returning streaming response object.")
        return Response(stream_with_context(generate_ocr_stream(ocr_engine, temp_file_path)), mimetype='text/plain; charset=utf-8')

    # Error handling remains the same
    except (ValueError, FileNotFoundError) as setup_val_err:
        print(f"--- Setup Validation Error in app_services: {setup_val_err} ---")
        if temp_file_path:
             print(f"Calling cleanup_file due to setup error for {temp_file_path}")
             cleanup_file(temp_file_path, "setup validation error cleanup")
        raise setup_val_err
    except Exception as setup_err:
        print(f"--- Unexpected Setup Error in app_services: {setup_err} ---")
        traceback.print_exc()
        if temp_file_path:
             print(f"Calling cleanup_file due to unexpected setup error for {temp_file_path}")
             cleanup_file(temp_file_path, "setup general error cleanup")
        raise Exception(f"Failed during OCR setup: {setup_err}")
