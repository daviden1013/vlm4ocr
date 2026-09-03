import os
import json
import asyncio
from dataclasses import asdict
from PIL import Image
from markdown import markdown
import io
import base64
import traceback
import uuid
import zipfile
import queue
import threading
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Response, stream_with_context, jsonify, current_app, url_for, send_file
from . import cleanup_file

try:
    from vlm4ocr.ocr_engines import OCREngine
    from vlm4ocr.vlm_engines import OpenAIVLMEngine, AzureOpenAIVLMEngine, OllamaVLMEngine, BasicVLMConfig, ReasoningVLMConfig
    from vlm4ocr.pdf_backends import DEFAULT_PDF_DPI
    from vlm4ocr.exceptions import VLM4OCRError
except ImportError as e:
    print(f"Error importing from vlm4ocr in app_services.py: {e}")
    raise


def _initialize_ocr_engine(form_data):
    """
    Helper function to initialize the OCREngine based on form data.
    This consolidates the engine setup logic for both single and batch processing.
    """
    vlm_api = form_data.get('vlm_api', '')
    user_prompt = form_data.get('user_prompt', None)
    output_format = form_data.get('output_format', 'markdown')
    vlm_config_type = form_data.get('vlm_config', 'basic')

    try:
        # Handle empty strings from form fields before casting
        max_tokens_str = form_data.get('max_new_tokens', '4096')
        max_new_tokens = int(max_tokens_str) if max_tokens_str else 4096

        temperature_str = form_data.get('temperature', '0.0')
        temperature = float(temperature_str) if temperature_str else 0.0

    except (ValueError, TypeError):
        raise ValueError("Invalid value for Max New Tokens or Temperature.")

    # Advanced parameters (top_p, top_k, reasoning_effort, mm_processor_kwargs, ...).
    # These are collected from the UI as a JSON object and routed per-provider below.
    advanced_params = {}
    advanced_raw = form_data.get('advanced_params', None)
    if advanced_raw:
        try:
            advanced_params = json.loads(advanced_raw)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("Invalid Advanced Parameters: expected a JSON object.")
        if not isinstance(advanced_params, dict):
            raise ValueError("Invalid Advanced Parameters: expected a JSON object.")

    # Route advanced params to the right place for the target backend:
    #   - Ollama expects flat options, so pass them as top-level config kwargs.
    #   - OpenAI-SDK backends (openai, azure, openai_compatible) take them via extra_body.
    config_kwargs = {"max_new_tokens": max_new_tokens, "temperature": temperature}
    if advanced_params:
        if vlm_api == "ollama":
            config_kwargs.update(advanced_params)
        else:
            config_kwargs["extra_body"] = advanced_params

    print(f"Initializing VLM Engine for API: {vlm_api}")

    if vlm_config_type == 'reasoning':
        print("Using ReasoningVLMConfig")
        config = ReasoningVLMConfig(**config_kwargs)
    else:
        print("Using BasicVLMConfig")
        config = BasicVLMConfig(**config_kwargs)

    vlm_engine = None
    if vlm_api == "openai_compatible":
        # API key is optional for self-hosted servers (e.g. vLLM/SGLang without auth).
        # Fall back to the conventional "EMPTY" placeholder so an unauthenticated
        # server still receives a valid (ignored) bearer token instead of a blank one.
        vlm_engine = OpenAIVLMEngine(
            model=form_data.get('vlm_model'),
            api_key=form_data.get('openai_compatible_api_key') or "EMPTY",
            base_url=form_data.get('vlm_base_url'),
            config=config
        )
    elif vlm_api == "openai":
        vlm_engine = OpenAIVLMEngine(
            model=form_data.get('openai_model'),
            api_key=form_data.get('openai_api_key'),
            config=config
        )
    elif vlm_api == "azure_openai":
        vlm_engine = AzureOpenAIVLMEngine(
            model=form_data.get('azure_deployment_name'),
            api_key=form_data.get('azure_openai_api_key'),
            azure_endpoint=form_data.get('azure_endpoint'),
            api_version=form_data.get('azure_api_version'),
            config=config
        )
    elif vlm_api == "ollama":
        vlm_engine = OllamaVLMEngine(
            model_name=form_data.get('ollama_model'),
            host=form_data.get('ollama_host', 'http://localhost:11434'),
            config=config
        )
    else:
        raise ValueError(f'Unsupported VLM API type selected: {vlm_api}')

    print("VLM Engine configured. Initializing OCREngine.")
    pdf_config = current_app.config.get('pdf') or {}
    return OCREngine(
        vlm_engine=vlm_engine,
        output_mode=output_format,
        system_prompt=None,
        user_prompt=user_prompt,
        pdf_backend=pdf_config.get('backend'),
        pdf_dpi=pdf_config.get('dpi', DEFAULT_PDF_DPI)
    )


def render_markdown_text(request):
    """Renders a given text string as HTML."""
    data = request.get_json()
    if 'text' not in data:
        raise ValueError("No text provided for rendering.")
    html = markdown(data['text'], extensions=['fenced_code', 'tables'])
    return jsonify({'status': 'success', 'html': html})


def process_tiff_preview_request(request):
    """Handles a TIFF preview request."""
    directory = Path(current_app.config["temp_directory"])
    try:
        if 'tiff_file' not in request.files:
            raise ValueError("No tiff_file part in request")
        file = request.files['tiff_file']
        if not file or file.filename == '' or not (file.filename.lower().endswith('.tif') or file.filename.lower().endswith('.tiff')):
            raise ValueError("Invalid TIFF file provided.")

        filename = secure_filename(file.filename)
        temp_file_path = os.path.join(directory, f"preview_{filename}")
        file.save(temp_file_path)

        base64_png_pages = []
        with Image.open(temp_file_path) as img:
            for i in range(img.n_frames):
                img.seek(i)
                page_image = img.convert('RGB')
                buffered = io.BytesIO()
                page_image.save(buffered, format="PNG")
                base64_png_pages.append(base64.b64encode(buffered.getvalue()).decode('utf-8'))
        
        return {'status': 'success', 'pages_data': base64_png_pages, 'format': 'png'}
    finally:
        if temp_file_path:
            cleanup_file(temp_file_path, "tiff preview cleanup")


def process_ocr_request(request):
    """
    Handles the core logic for a SINGLE FILE OCR request.
    This version now uses the configurable TEMP_DIR for its uploads.
    """
    temp_file_path = None
    try:
        if 'input_file' not in request.files:
            raise ValueError("No input file part in request")
        file = request.files['input_file']
        if not file or file.filename == '':
            raise ValueError("No selected file")

        # Save the file to the configurable temp directory
        filename = secure_filename(file.filename)
        temp_file_path = str(Path(current_app.config["temp_directory"]) / filename) 
        file.save(temp_file_path)

        ocr_engine = _initialize_ocr_engine(request.form)

        def generate_ocr_stream(ocr_eng, file_to_process_path):
            emitted_error = False
            try:
                for item_dict in ocr_eng.stream_ocr(file_path=file_to_process_path):
                    if item_dict.get("type") == "error":
                        emitted_error = True
                    yield json.dumps(item_dict) + '\n'
            except Exception as e:
                # stream_ocr emits its own error event for a document it cannot load, then
                # raises; only report here if nothing was emitted, to avoid a duplicate.
                if not emitted_error:
                    error_obj = {"type": "error", "data": f"Streaming Failed: {str(e)}"}
                    if isinstance(e, VLM4OCRError):
                        error_obj["error"] = e.to_dict()
                    yield json.dumps(error_obj) + '\n'
                traceback.print_exc()
            finally:
                cleanup_file(file_to_process_path, "post-stream cleanup")

        return Response(stream_with_context(generate_ocr_stream(ocr_engine, temp_file_path)), mimetype='application/x-ndjson')

    except (ValueError, FileNotFoundError) as setup_err:
        if temp_file_path:
            cleanup_file(temp_file_path, "setup error cleanup")
        raise setup_err
    except Exception as setup_err:
        if temp_file_path:
            cleanup_file(temp_file_path, "setup general error cleanup")
        raise Exception(f"Failed during OCR setup: {setup_err}")


def initiate_batch_job(request):
    """
    Saves files and form data for a new batch job and returns the job ID.
    """
    batch_id = str(uuid.uuid4())
    batch_dir = Path(current_app.config["temp_directory"]) / batch_id
    batch_dir.mkdir(exist_ok=True)

    # Save form data
    form_data_path = batch_dir / 'form_data.json'
    with open(form_data_path, 'w') as f:
        json.dump(request.form.to_dict(), f)

    # Save files
    files = request.files.getlist('batch_input_files')
    if not files or all(f.filename == '' for f in files):
        raise ValueError("No files were provided for batch processing.")

    # Check against the maximum number of files allowed
    max_files = current_app.config.get('batch_processing', {}).get('max_files', 100)
    if len(files) > max_files:
        raise ValueError(f"Too many files. The maximum is {max_files}.")

    for file in files:
        filename = secure_filename(file.filename)
        file.save(batch_dir / filename)

    return batch_id


# Maps batch_id -> threading.Event; set the event to cancel that batch job
_batch_cancel_events: dict = {}


def cancel_batch_job(batch_id: str):
    event = _batch_cancel_events.get(batch_id)
    if event:
        event.set()


def process_batch_ocr_stream(batch_id, base_url):
    """
    Finds a batch job by its ID, processes it, and streams results.
    This function now correctly handles URL generation in the main thread.
    """
    q = queue.Queue()
    cancel_event = threading.Event()
    _batch_cancel_events[batch_id] = cancel_event
    # Get a safe reference to the current Flask app object
    app = current_app._get_current_object()

    def run_async_ocr_worker():
        """
        This worker function runs in a separate background thread.
        It is now only responsible for OCR processing.
        """
        # Establish an application context for this background thread
        with app.app_context():
            # Create a new asyncio event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                batch_dir = Path(current_app.config["temp_directory"]) / batch_id
                form_data_path = batch_dir / 'form_data.json'

                if not batch_dir.exists() or not form_data_path.exists():
                    q.put(json.dumps({'type': 'error', 'data': f'Batch job {batch_id} not found.'}))
                    return

                with open(form_data_path, 'r') as f:
                    form_data = json.load(f)

                ocr_engine = _initialize_ocr_engine(form_data)
                output_format_ext_map = {"text": "txt", "markdown": "md", "HTML": "html", "JSON": "json"}
                output_format = form_data.get('output_format', 'markdown')
                output_format_ext = output_format_ext_map.get(output_format, 'md')
                image_paths = [str(p) for p in batch_dir.iterdir() if p.is_file() and p.suffix.lower() not in ['.json']]

                async def process_and_queue_results(concurrent_batch_size: int):
                    """The async coroutine that calls the OCR library."""
                    response_generator = ocr_engine.concurrent_ocr(
                        file_paths=image_paths,
                        concurrent_batch_size=concurrent_batch_size
                    )
                    try:
                        async for result in response_generator:
                            if cancel_event.is_set():
                                break
                            if result.status == "success":
                                if output_format == "bbox":
                                    stem = Path(result.filename).stem
                                    bbox_data = []
                                    user_prompt = form_data.get('user_prompt') or ""
                                    for page_idx, page in enumerate(result.pages):
                                        if page.bboxes:
                                            if user_prompt:
                                                marked = page.plot_bboxes(show_label=True, show_text=True, color="label")
                                            else:
                                                marked = page.plot_bboxes(show_label=False, show_text=True, color="random")
                                            png_name = f"{stem}_page_{page_idx}_bbox.png"
                                            marked.save(batch_dir / png_name)
                                            q.put(json.dumps({'type': 'result', 'filename': png_name}))
                                            bbox_data.append({
                                                "page_idx": page_idx,
                                                "bboxes": [asdict(b) for b in page.bboxes],
                                            })
                                    json_name = f"{stem}_bbox.json"
                                    (batch_dir / json_name).write_text(json.dumps(bbox_data, indent=2))
                                    q.put(json.dumps({'type': 'result', 'filename': json_name}))
                                else:
                                    output_filename = f"{Path(result.filename).stem}.{output_format_ext}"
                                    output_content = result.to_string()
                                    with open(batch_dir / output_filename, "w", encoding="utf-8") as f:
                                        f.write(output_content)
                                    q.put(json.dumps({'type': 'result', 'filename': output_filename}))
                            else:
                                error_obj = {'type': 'error', 'filename': Path(result.filename).name}
                                if result.error is not None:
                                    # Structured error from vlm4ocr. 'data' stays a string
                                    # for the UI; 'error' carries the machine-readable detail
                                    # (which step failed, which backend, the raw library message).
                                    error_obj['data'] = str(result.error)
                                    error_obj['error'] = result.error.to_dict()
                                else:
                                    error_obj['data'] = (result.pages and result.pages[0].get('text')) or 'Unknown error.'
                                q.put(json.dumps(error_obj))
                    finally:
                        await response_generator.aclose()

                batch_processing_config = current_app.config.get("batch_processing", {})
                concurrent_batch_size = batch_processing_config.get("concurrent_batch_size", 4)
                loop.run_until_complete(process_and_queue_results(concurrent_batch_size))

            except Exception as e:
                print("--- CRITICAL ERROR IN BATCH WORKER THREAD ---")
                traceback.print_exc()
                error_trace = traceback.format_exc()
                q.put(json.dumps({'type': 'error', 'data': f'A critical server error occurred:\n{error_trace}'}))
            finally:
                _batch_cancel_events.pop(batch_id, None)
                q.put(None)  # Sentinel value to signal completion

    # The base_url is NOT passed to the worker thread
    thread = threading.Thread(target=run_async_ocr_worker)
    thread.start()

    # This loop runs in the main thread with the request context
    while True:
        message_json = q.get()
        if message_json is None:
            if not cancel_event.is_set():
                yield json.dumps({'type': 'completed', 'batch_id': batch_id})
            break

        message = json.loads(message_json)

        # If the message is a successful result, build the URL here
        if message['type'] == 'result':
            relative_url = url_for('download_file', batch_id=batch_id, filename=message['filename'])
            download_url = f"{base_url.rstrip('/')}{relative_url}"
            message['download_url'] = download_url
            yield json.dumps(message)
        else:
            # For errors or other message types, just pass them along
            yield message_json


def download_processed_file(batch_id, filename):
    """
Vlm4ocr/vlm4ocr-7595f2b3c10725d9ce590c3e8dbdf49b537588a8/services/web_app/app/app_services.py
    Finds a specific processed file within a batch directory and sends it,
    now using a robust method to construct the absolute path.
    """
    try:
        relative_path = Path(current_app.config["temp_directory"]) / str(batch_id) / filename
        absolute_path = Path("/app") / relative_path
        return send_file(absolute_path, as_attachment=True)

    except FileNotFoundError as e:
        current_app.logger.error(f"Caught FileNotFoundError in service: {e}")
        raise e
    except Exception as e:
        current_app.logger.error(f"An unexpected exception occurred in download_processed_file: {e}")
        traceback.print_exc()
        raise e


def download_batch_as_zip(batch_id):
    """
    Zips the processed output files and cleans up the temporary directory
    after the request is complete.
    """
    directory = Path(current_app.config["temp_directory"]) / str(batch_id)
    memory_file = io.BytesIO()
    
    output_extensions = ('.md', '.txt', '.html', '.json', '.png')

    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in directory.iterdir():
            if f.is_file() and (f.name.lower().endswith(output_extensions) or f.name.lower() == "form_data.json"):
                zf.write(f, arcname=f.name)
                
    memory_file.seek(0)

    if not memory_file.getbuffer().nbytes:
        return "No processed files found to download.", 404

    return send_file(
        memory_file,
        download_name=f'batch_results_{batch_id}.zip',
        as_attachment=True,
        mimetype='application/zip'
    )