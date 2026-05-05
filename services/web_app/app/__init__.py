import os
import yaml
from easydict import EasyDict
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
import logging

""" Define configuration Paths """
APP_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_APP_ROOT = os.path.dirname(APP_DIR) # This should be services/web_app/
UPLOAD_FOLDER = os.path.join(WEB_APP_ROOT, 'uploads')
CONFIG_PATH = os.path.join(WEB_APP_ROOT, 'config.yaml')

""" Utility Functions """
def load_app_config(config_path):
    """Loads configuration from the specified path safely."""
    try:
        with open(config_path) as yaml_file:
            config = EasyDict(yaml.safe_load(yaml_file))
            print(f"Configuration loaded successfully from {config_path}")
            return config
    except FileNotFoundError:
        print(f"Warning: {config_path} not found. Using empty config.")
        return EasyDict({})
    except yaml.YAMLError as e:
        print(f"Error parsing {config_path}: {e}. Using empty config.")
        return EasyDict({})
    except Exception as e:
        print(f"An unexpected error occurred loading config from {config_path}: {e}. Using empty config.")
        return EasyDict({})

def cleanup_file(file_path, context="cleanup"):
    """Safely removes a file if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"Removed temporary file ({context}): {file_path}")
        except OSError as e:
            print(f"Error removing temporary file ({context}) {file_path}: {e}")

""" Flask App Initialization """
print("Initializing Flask app...")
app = Flask(__name__,
            instance_relative_config=False,
            template_folder='../templates',
            static_folder='../static')

# Set for debugging
# app.logger.setLevel(logging.INFO)

""" Add the ProxyFix middleware """
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

""" Load App-Specific Config from YAML """
print(f"Loading app config from: {CONFIG_PATH}")
app.config.update(load_app_config(CONFIG_PATH))

""" Set the maximum file upload size from the config """
if 'file_upload' in app.config and app.config.get('file_upload').get('max_size_mb'):
    # This line configures Flask's internal request handling to reject requests with bodies larger than the specified size
    app.config['MAX_CONTENT_LENGTH'] = app.config['file_upload']['max_size_mb'] * 1024 * 1024

""" Create Temporary Directory """
# check if "temp_directory" key exists in config
if "temp_directory" not in app.config:
    raise ValueError("temp_directory key not found in app config")
# create temp directory if it doesn't exist
temp_dir = Path(app.config.get("temp_directory", "temp"))
temp_dir.mkdir(exist_ok=True)

""" Inject version info into all templates """
import tomllib

try:
    VLM4OCR_VERSION = version("vlm4ocr")
except PackageNotFoundError:
    VLM4OCR_VERSION = "unknown"

try:
    with open(os.path.join(WEB_APP_ROOT, "pyproject.toml"), "rb") as f:
        WEB_APP_VERSION = tomllib.load(f)["tool"]["poetry"]["version"]
except (FileNotFoundError, KeyError):
    WEB_APP_VERSION = "unknown"

@app.context_processor
def inject_version():
    return {
        "vlm4ocr_version": VLM4OCR_VERSION,
        "web_app_version": WEB_APP_VERSION,
    }

""" Import Routes (must be done after app is created) """
print("Importing routes...")
from . import routes
print("Routes imported.")

print("Flask app initialization complete.")