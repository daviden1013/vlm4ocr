import abc
import os
import io
import base64
from typing import Union, List, Tuple
import importlib.util
from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image
import asyncio


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
    if output_mode not in ["markdown", "HTML", "text"]:
        raise ValueError("output_mode must be 'markdown', 'HTML', or 'text'")
    
    if output_mode == "markdown":
        return "\n\n---\n\n"
    elif output_mode == "HTML":
        return "<br><br>"
    elif output_mode == "text":
        return "\n\n---\n\n"


class ImageProcessor:
    def __init__(self):
        self.has_tesseract = importlib.util.find_spec("pytesseract") is not None

    def rotate_correction(self, image: Image.Image) -> Tuple[Image.Image, int]:
        """ 
        This method use Tesseract OSD to correct the rotation of the image. 
        
        Parameters:
        ----------
        image : Image.Image
            The image to be corrected.

        Returns:
        -------
        Image.Image
            The corrected image.
        int
            The rotation angle in degrees.
        """
        if importlib.util.find_spec("pytesseract") is None:
            raise ImportError("pytesseract is not installed. Please install it to use this feature.")
        
        import pytesseract

        try:
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
            rotation_angle = osd['rotate']
            if rotation_angle != 0:
                return image.rotate(rotation_angle, expand=True), rotation_angle
            
            return image, 0
        except Exception as e:
            print(f"Error correcting image rotation: {e}")
            raise ValueError(f"Failed to correct image rotation: {e}") from e

    async def rotate_correction_async(self, image: Image.Image) -> Tuple[Image.Image, int]:
        """ 
        Asynchronous version of rotate_correction method.

        Parameters:
        ----------
        image : Image.Image
            The image to be corrected.

        Returns:
        -------
        Image.Image
            The corrected image.
        int
            The rotation angle in degrees.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.rotate_correction, image)

    def resize(self, image: Image.Image, max_dimension_pixels:int=4000) -> Tuple[Image.Image, bool]:
        """ 
        Resizes the image to fit within the specified maximum dimension while maintaining aspect ratio.
        
        Parameters:
        ----------
        max_dimension_pixels : int
            The maximum dimension (width or height) in pixels.

        Returns:
        -------
        Image.Image
            The resized image.
        bool
            True if the image was resized, False otherwise.
        """
        width, height = image.size
        if width > max_dimension_pixels or height > max_dimension_pixels:
            if width > height:
                new_width = max_dimension_pixels
                new_height = int((max_dimension_pixels / width) * height)
            else:
                new_height = max_dimension_pixels
                new_width = int((max_dimension_pixels / height) * width)
            return image.resize((new_width, new_height), resample=Image.Resampling.LANCZOS), True  # Resizing was done
        
        return image, False  # No resizing needed

    async def resize_async(self, image: Image.Image, max_dimension_pixels:int=4000) -> Tuple[Image.Image, bool]:
        """ 
        Asynchronous version of resize method.
        
        Parameters:
        ----------
        max_dimension_pixels : int
            The maximum dimension (width or height) in pixels.

        Returns:
        -------
        Image.Image
            The resized image.
        bool
            True if the image was resized, False otherwise.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.resize, image, max_dimension_pixels)