import os
import yaml
from easydict import EasyDict
from flask import Flask

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

""" App Configuration """
print(f"Setting UPLOAD_FOLDER to: {UPLOAD_FOLDER}")
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

""" Load App-Specific Config from YAML """
print(f"Loading app config from: {CONFIG_PATH}")
app.app_config = load_app_config(CONFIG_PATH)

""" Ensure Upload Folder Exists """
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    print(f"Upload folder ensured: {UPLOAD_FOLDER}")
except OSError as e:
    print(f"Error creating upload folder {UPLOAD_FOLDER}: {e}")

""" Import Routes (must be done after app is created) """
print("Importing routes...")
# Use a relative import to import routes from the same package
from . import routes
print("Routes imported.")

print("Flask app initialization complete.")