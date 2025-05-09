import os
import json
from PIL import Image
import io
import base64
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
        def generate_ocr_stream(ocr_eng, file_to_process_path): # Renamed arg for clarity
            print(f"generate_ocr_stream called for: {file_to_process_path}")
            try:
                print(f"Starting OCREngine.stream_ocr for: {file_to_process_path}")
                for item_dict in ocr_eng.stream_ocr(file_path=file_to_process_path):
                    # item_dict is now {"type": "...", "data": "..."}
                    yield json.dumps(item_dict) + '\n' # Convert dict to JSON string and add newline
                print(f"Finished OCREngine.stream_ocr for: {file_to_process_path}")
            except ValueError as val_err: # Catch errors from OCREngine (e.g., file not found, unsupported type)
                print(f"--- Value Error during OCR stream: {val_err} ---")
                traceback.print_exc()
                error_obj = {"type": "error", "data": f"Streaming Error: {str(val_err)}"}
                yield json.dumps(error_obj) + '\n'
            except Exception as stream_err:
                print(f"--- Error Traceback during OCR stream generation ---")
                traceback.print_exc()
                error_obj = {"type": "error", "data": f"Streaming Failed: An unexpected error occurred during processing: {str(stream_err)}"}
                yield json.dumps(error_obj) + '\n'
            finally:
                print(f"Calling cleanup_file from generate_ocr_stream finally block for {file_to_process_path}")
                cleanup_file(file_to_process_path, "post-stream cleanup")

        # 7. Return Streaming Response (remains the same)
        print("Setup complete. Returning streaming response object.")
        return Response(stream_with_context(generate_ocr_stream(ocr_engine, temp_file_path)), mimetype='application/x-ndjson')

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

def process_tiff_preview_request(request):
    """
    Handles a TIFF preview request.
    - Validates input file.
    - Saves the TIFF temporarily.
    - Converts ALL pages of the TIFF to PNGs.
    - Returns a list of PNGs as base64 encoded strings.
    - Ensures cleanup of the temporary file.
    """
    print("Entering app_services.process_tiff_preview_request for all pages")
    temp_file_path = None
    try:
        if 'tiff_file' not in request.files:
            raise ValueError("No tiff_file part in request")
        file = request.files['tiff_file']
        if not file or file.filename == '':
            raise ValueError("No selected TIFF file")

        if not (file.filename.lower().endswith('.tif') or file.filename.lower().endswith('.tiff')):
            raise ValueError("Invalid file type. Expected a TIFF file.")

        filename = secure_filename(file.filename)
        # Add a unique prefix or use a subdirectory for preview files to avoid potential clashes
        temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"preview_tiff_{filename}")
        print(f"Saving temporary TIFF for preview to: {temp_file_path}")
        file.save(temp_file_path)
        print("Temporary TIFF saved.")

        base64_png_pages = []
        with Image.open(temp_file_path) as img:
            print(f"TIFF file opened. Number of frames: {img.n_frames}")
            for i in range(img.n_frames):
                img.seek(i) # Go to the i-th frame/page
                
                # Convert to RGB if it's not, to ensure broader PNG compatibility
                page_image = img
                if page_image.mode != 'RGB':
                    page_image = page_image.convert('RGB')
                
                buffered = io.BytesIO()
                page_image.save(buffered, format="PNG")
                png_bytes = buffered.getvalue()
                base64_png_string = base64.b64encode(png_bytes).decode('utf-8')
                base64_png_pages.append(base64_png_string)
                print(f"Converted page {i+1}/{img.n_frames} of TIFF to base64 PNG string.")
        
        if not base64_png_pages:
            raise ValueError("No pages could be extracted or converted from the TIFF file.")

        print(f"All {len(base64_png_pages)} TIFF pages converted to base64 PNG strings.")
        return {'status': 'success', 'pages_data': base64_png_pages, 'format': 'png'}

    except Exception as e:
        print(f"--- Error in process_tiff_preview_request: {e} ---")
        traceback.print_exc()
        raise ValueError(f"Failed to process TIFF for preview: {str(e)}")
    finally:
        if temp_file_path:
            print(f"Calling cleanup_file from process_tiff_preview_request finally block for {temp_file_path}")
            cleanup_file(temp_file_path, "tiff preview cleanup")
