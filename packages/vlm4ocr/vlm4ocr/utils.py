import os
import io
import base64
from typing import List
from pdf2image import convert_from_path
from PIL import Image

def get_images_from_pdf(file_path: str) -> List[Image.Image]:
    """ Extracts images from a PDF file. """
    try:
        images = convert_from_path(file_path)
        if not images:
            print(f"Warning: No images extracted from PDF: {file_path}")
        return images
    except Exception as e:
        print(f"Error converting PDF to images: {e}")
        raise ValueError(f"Failed to process PDF file '{os.path.basename(file_path)}'. Ensure poppler is installed and the file is valid.") from e


def get_image_from_file(file_path: str) -> Image.Image:
        """ Loads a single image file. """
        try:
            image = Image.open(file_path)
            image.load()
            return image
        except FileNotFoundError:
            raise FileNotFoundError(f"Image file not found: {file_path}")
        except Exception as e:
            raise ValueError(f"Failed to load image file '{os.path.basename(file_path)}': {e}") from e


def image_to_base64(image:Image.Image, format:str="png") -> List[str]:
    """ Converts an image to a base64 string. """
    try:
        buffered = io.BytesIO()
        image.save(buffered, format=format)
        img_bytes = buffered.getvalue()
        encoded_bytes = base64.b64encode(img_bytes)
        encoded_string = encoded_bytes.decode('utf-8')
        return f"data:image/{format};base64,{encoded_string}"
    except Exception as e:
        print(f"Error converting image to base64: {e}")
        raise ValueError(f"Failed to convert image to base64: {e}") from e
    
def clean_markdown(text:str) -> str:
    cleaned_text = text.replace("```markdown", "").replace("```", "")
    return cleaned_text