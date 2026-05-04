import abc
import os
import io
import base64
from typing import Dict, List
import json
import json_repair
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image
import asyncio
import warnings


class DataLoader(abc.ABC):
    def __init__(self, file_path: str):
        self.file_path = file_path
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

    @abc.abstractmethod
    def get_all_pages(self) -> List[Image.Image]:
        """ 
        Abstract method to get all pages from the file. 
        """
        pass

    @abc.abstractmethod
    def get_page(self, page_index:int) -> Image.Image:
        """ 
        Abstract method to get pages from the file. 
        
        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve. 
        """
        pass

    @abc.abstractmethod
    async def get_page_async(self, page_index:int) -> Image.Image:
        """ 
        Abstract method to get pages from the file. 
        
        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve.
        """
        pass

    @abc.abstractmethod
    def get_page_count(self) -> int:
        """ Returns the number of pages in the PDF file. """
        pass


class PDFDataLoader(DataLoader):
    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.info = pdfinfo_from_path(self.file_path, userpw=None, poppler_path=None)

    def get_all_pages(self) -> List[Image.Image]:
        """ 
        Extracts pages from a PDF file. 
        """
        try:
            return convert_from_path(self.file_path)

        except Exception as e:
            print(f"Error converting PDF to images: {e}")
            raise ValueError(f"Failed to process PDF file '{os.path.basename(self.file_path)}'. Ensure poppler is installed and the file is valid.") from e

    def get_page(self, page_index:int) -> Image.Image:
        """
        Extracts a page from a PDF file.

        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve.
        """
        try:
            return convert_from_path(self.file_path, first_page=page_index + 1, last_page=page_index + 1)[0]
        except Exception as e:
            print(f"Error converting PDF to images: {e}")
            raise ValueError(f"Failed to process PDF file '{os.path.basename(self.file_path)}'. Ensure poppler is installed and the file is valid.") from e


    async def get_page_async(self, page_index:int) -> Image.Image:
        """ 
        Asynchronously extracts a page from a PDF file. 
        
        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve. 
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_page, page_index)


    def get_page_count(self) -> int:
        """ Returns the number of pages in the PDF file. """
        return self.info['Pages'] if 'Pages' in self.info else 0
    

class TIFFDataLoader(DataLoader):
    def __init__(self, file_path: str):
        super().__init__(file_path)

    def get_all_pages(self) -> List[Image.Image]:
        """ 
        Extracts images from a TIFF file. 
        """
        try:
            img = Image.open(self.file_path)
            images = []
            for i in range(img.n_frames):
                img.seek(i)
                images.append(img.copy())
            return images
        except Exception as e:
            print(f"Error extracting images from TIFF: {e}")
            raise ValueError(f"Failed to process TIFF file '{os.path.basename(self.file_path)}'. Ensure the file is valid.") from e
        

    def get_page(self, page_index:int) -> Image.Image:
        """
        Extracts a page from a TIFF file.

        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve. 
        """
        try:
            img = Image.open(self.file_path)
            img.seek(page_index)
            return img.copy()
        except IndexError:
            raise ValueError(f"Page index {page_index} out of range for TIFF file '{os.path.basename(self.file_path)}'.") from None
        except Exception as e:
            print(f"Error extracting page {page_index} from TIFF: {e}")
            raise ValueError(f"Failed to process TIFF file '{os.path.basename(self.file_path)}'. Ensure the file is valid.") from e

    async def get_page_async(self, page_index:int) -> Image.Image:
        """ 
        Asynchronously extracts images from a TIFF file. 
        
        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_page, page_index)

    def get_page_count(self) -> int:
        """ Returns the number of images (pages) in the TIFF file. """
        try:
            img = Image.open(self.file_path)
            return img.n_frames 
        except Exception as e:
            print(f"Error getting page count from TIFF: {e}")
            raise ValueError(f"Failed to process TIFF file '{os.path.basename(self.file_path)}'. Ensure the file is valid.") from e


class ImageDataLoader(DataLoader):
    def get_all_pages(self) -> List[Image.Image]:
        """ 
        Loads a single image file. 
        """
        try:
            image = Image.open(self.file_path)
            image.load()
            return [image]
        except FileNotFoundError:
            raise FileNotFoundError(f"Image file not found: {self.file_path}")
        except Exception as e:
            raise ValueError(f"Failed to load image file '{os.path.basename(self.file_path)}': {e}") from e
        
    def get_page(self, page_index:int) -> Image.Image:
        """ 
        Loads a single image file. 
        
        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve. Not applicable for single image files.
        """
        try:
            image = Image.open(self.file_path)
            image.load()
            return image
        except FileNotFoundError:
            raise FileNotFoundError(f"Image file not found: {self.file_path}")
        except Exception as e:
            raise ValueError(f"Failed to load image file '{os.path.basename(self.file_path)}': {e}") from e
        
    async def get_page_async(self, page_index:int) -> Image.Image:
        """ 
        Asynchronously loads a single image file. 
        
        Parameters:
        ----------
        page_index : int
            Index of the page to retrieve. Not applicable for single image files.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_page, page_index)

    def get_page_count(self) -> int:
        """ Returns 1 as there is only one image in a single image file. """
        return 1


def image_to_base64(image:Image.Image, format:str="png") -> str:
    """ Converts an image to a base64 string. """
    try:
        buffered = io.BytesIO()
        image.save(buffered, format=format)
        img_bytes = buffered.getvalue()
        encoded_bytes = base64.b64encode(img_bytes)
        base64_encoded_string = encoded_bytes.decode('utf-8')
        return base64_encoded_string
    except Exception as e:
        print(f"Error converting image to base64: {e}")
        raise ValueError(f"Failed to convert image to base64: {e}") from e
    
def clean_markdown(text:str) -> str:
    cleaned_text = text.replace("```markdown", "").replace("```", "")
    return cleaned_text

def _find_dict_strings( text: str) -> List[str]:
    """
    Extracts balanced JSON-like dictionaries from a string, even if nested.

    Parameters:
    -----------
    text : str
        the input text containing JSON-like structures.

    Returns : List[str]
        A list of valid JSON-like strings representing dictionaries.
    """
    open_brace = 0
    start = -1
    json_objects = []

    for i, char in enumerate(text):
        if char == '{':
            if open_brace == 0:
                # start of a new JSON object
                start = i 
            open_brace += 1
        elif char == '}':
            open_brace -= 1
            if open_brace == 0 and start != -1:
                json_objects.append(text[start:i + 1])
                start = -1

    return json_objects

def extract_json(gen_text:str) -> List[Dict[str, str]]:
    """ 
    This method inputs a generated text and output a JSON of information tuples
    """
    out = []
    dict_str_list = _find_dict_strings(gen_text)
    for dict_str in dict_str_list:
        try:
            dict_obj = json.loads(dict_str)
            out.append(dict_obj)
        except json.JSONDecodeError:
            dict_obj = json_repair.repair_json(dict_str, skip_json_loads=True, return_objects=True)
            if dict_obj:
                warnings.warn(f'JSONDecodeError detected, fixed with repair_json:\n{dict_str}', RuntimeWarning)
                out.append(dict_obj)
            else:
                warnings.warn(f'JSONDecodeError could not be fixed:\n{dict_str}', RuntimeWarning)
    return out

def get_default_page_delimiter(output_mode:str) -> str:
    """ 
    Returns the default page delimiter based on the environment variable.

    Parameters:
    ----------
    output_mode : str
        The output mode, which can be "markdown", "HTML", or "text".
    
    Returns:
    -------
    str
        The default page delimiter.
    """
    if output_mode not in ["markdown", "HTML", "text", "JSON", "bbox"]:
        raise ValueError("output_mode must be 'markdown', 'HTML', 'text', 'JSON', or 'bbox'")

    if output_mode == "markdown":
        return "\n\n---\n\n"
    elif output_mode == "HTML":
        return "<br><br>"
    elif output_mode == "text":
        return "\n\n---\n\n"
    elif output_mode == "JSON":
        return "\n\n---\n\n"
    elif output_mode == "bbox":
        return "\n\n---\n\n"