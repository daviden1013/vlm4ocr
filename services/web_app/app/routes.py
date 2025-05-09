import traceback
from flask import render_template, request, jsonify, Response, stream_with_context
from . import app
from . import app_services

@app.route('/')
def index():
    """Renders the main index page with VLM options from app config."""
    vlm_api_options_data = app.app_config.get("vlm_api_options", [])

    return render_template(
        'index.html',
        vlm_api_options=vlm_api_options_data,
    )

@app.route('/api/run_ocr', methods=['POST'])
def handle_ocr_route():
    print("Request received at /api/run_ocr route.")
    try:
        # app_services.process_ocr_request returns the fully formed Response object
        response_object = app_services.process_ocr_request(request)
        
        # Directly return the Response object
        return response_object
    
    except ValueError as ve: # Catch setup errors from app_services before streaming starts
        print(f"Validation Error in OCR processing setup: {ve}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(ve)}), 400
    except Exception as e: # Catch other unexpected setup errors
        print(f"--- Unexpected Error in /api/run_ocr route before streaming ---")
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': f'An internal server error occurred: {str(e)}'}), 500


@app.route('/api/preview_tiff', methods=['POST'])
def handle_tiff_preview_route():
    """
    Handles the TIFF preview request by calling the service layer function.
    Returns a JSON response with the base64 encoded PNG of the first page or an error.
    """
    print("Request received at /api/preview_tiff route.")
    try:
        result = app_services.process_tiff_preview_request(request)
        return jsonify(result), 200
    except ValueError as ve:
        print(f"Validation Error in TIFF preview processing: {ve}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(ve)}), 400
    except Exception as e:
        print(f"--- Unexpected Error in /api/preview_tiff route ---")
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': f'An internal server error occurred during TIFF preview: {str(e)}'}), 500
