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
    """
    Handles the OCR request by calling the service layer function.
    Returns a streaming response or a JSON error.
    """
    print("Request received at /api/run_ocr route.")
    try:
        # Pass the request object to the service layer to handle processing
        response = app_services.process_ocr_request(request)
        print("Returning response from app_services.process_ocr_request.")
        return response
    except ValueError as ve:
        # Catch specific validation errors raised by app_services
        print(f"Validation Error in OCR processing: {ve}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(ve)}), 400
    except Exception as e:
        # Catch unexpected errors during route handling/service call setup
        print(f"--- Unexpected Error in /api/run_ocr route ---")
        traceback.print_exc()
        print("--- End Traceback ---")
        # Ensure temporary files are cleaned up if possible (though ideally done in app_services)
        # app_services.attempt_cleanup(request) # Consider adding a cleanup helper
        return jsonify({'status': 'error', 'error': f'An internal server error occurred: {str(e)}'}), 500
