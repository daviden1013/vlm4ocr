import os
from typing import Tuple, List, Dict, Union, Generator, AsyncGenerator, Iterable
import importlib
import asyncio
from colorama import Fore, Style   
from PIL import Image
from vlm4ocr.utils import DataLoader, PDFDataLoader, TIFFDataLoader, ImageDataLoader, ImageProcessor, clean_markdown, get_default_page_delimiter
from vlm4ocr.data_types import OCRResult
from vlm4ocr.vlm_engines import VLMEngine

SUPPORTED_IMAGE_EXTS = ['.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']


class OCREngine:
    def __init__(self, vlm_engine:VLMEngine, output_mode:str="markdown", system_prompt:str=None, user_prompt:str=None):
        """
        This class inputs a image or PDF file path and processes them using a VLM inference engine. Outputs plain text or markdown.

        Parameters:
        -----------
        inference_engine : InferenceEngine
            The inference engine to use for OCR.
        output_mode : str, Optional
            The output format. Must be 'markdown', 'HTML', or 'text'.
        system_prompt : str, Optional
            Custom system prompt. We recommend use a default system prompt by leaving this blank. 
        user_prompt : str, Optional
            Custom user prompt. It is good to include some information regarding the document. If not specified, a default will be used.
        """
        # Check inference engine
        if not isinstance(vlm_engine, VLMEngine):
            raise TypeError("vlm_engine must be an instance of VLMEngine")
        self.vlm_engine = vlm_engine

        # Check output mode
        if output_mode not in ["markdown", "HTML", "text"]:
            raise ValueError("output_mode must be 'markdown', 'HTML', or 'text'")
        self.output_mode = output_mode

        # System prompt
        if isinstance(system_prompt, str) and system_prompt:
            self.system_prompt = system_prompt
        else:
            prompt_template_path = importlib.resources.files('vlm4ocr.assets.default_prompt_templates').joinpath(f'ocr_{self.output_mode}_system_prompt.txt')
            with prompt_template_path.open('r', encoding='utf-8') as f:
                self.system_prompt =  f.read()

        # User prompt
        if isinstance(user_prompt, str) and user_prompt:
            self.user_prompt = user_prompt
        else:
            prompt_template_path = importlib.resources.files('vlm4ocr.assets.default_prompt_templates').joinpath(f'ocr_{self.output_mode}_user_prompt.txt')
            with prompt_template_path.open('r', encoding='utf-8') as f:
                self.user_prompt =  f.read()

        # Image processor
        self.image_processor = ImageProcessor()


    def stream_ocr(self, file_path: str, rotate_correction:bool=False, max_dimension_pixels:int=None) -> Generator[Dict[str, str], None, None]:
        """
        This method inputs a file path (image or PDF) and stream OCR results in real-time. This is useful for frontend applications.
        Yields dictionaries with 'type' ('ocr_chunk' or 'page_delimiter') and 'data'.

        Parameters:
        -----------
        file_path : str
            The path to the image or PDF file. Must be one of '.pdf', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        rotate_correction : bool, Optional
            If True, applies rotate correction to the images using pytesseract.
        max_dimension_pixels : int, Optional
            The maximum dimension of the image in pixels. Original dimensions will be resized to fit in. If None, no resizing is applied.

        Returns:
        --------
        Generator[Dict[str, str], None, None]
            A generator that yields the output:
            {"type": "info", "data": msg}
            {"type": "ocr_chunk", "data": chunk}
            {"type": "page_delimiter", "data": page_delimiter}
        """
        # Check file path
        if not isinstance(file_path, str):
            raise TypeError("file_path must be a string")
        
        # Check file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in SUPPORTED_IMAGE_EXTS:
            raise ValueError(f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}")
        
        # Check if image preprocessing can be applied
        if self.image_processor.has_tesseract==False and rotate_correction:
            raise ImportError("pytesseract is not installed. Please install it to use rotate correction.")

        # PDF or TIFF
        if file_ext in ['.pdf', '.tif', '.tiff']:
            data_loader = PDFDataLoader(file_path) if file_ext == '.pdf' else TIFFDataLoader(file_path)
            images = data_loader.get_all_pages()
            # Check if images were extracted
            if not images:
                raise ValueError(f"No images extracted from file: {file_path}")
            
            # OCR each image
            for i, image in enumerate(images):
                # Apply rotate correction if specified and tesseract is available
                if rotate_correction and self.image_processor.has_tesseract:
                    try:
                        image, _ = self.image_processor.rotate_correction(image)
                        
                    except Exception as e:
                        yield {"type": "info", "data": f"Error during rotate correction: {str(e)}"}
                        
                # Resize the image if max_dimension_pixels is specified
                if max_dimension_pixels is not None:
                    try:
                        image, _ = self.image_processor.resize(image, max_dimension_pixels=max_dimension_pixels)
                    except Exception as e:
                        yield {"type": "info", "data": f"Error resizing image: {str(e)}"}

                messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
                response_stream = self.vlm_engine.chat(
                    messages,
                    stream=True
                )
                for chunk in response_stream:
                    yield {"type": "ocr_chunk", "data": chunk}

                if i < len(images) - 1:
                    yield {"type": "page_delimiter", "data": get_default_page_delimiter(self.output_mode)}

        # Image
        else:
            data_loader = ImageDataLoader(file_path)
            image = data_loader.get_page(0)

            # Apply rotate correction if specified and tesseract is available
            if rotate_correction and self.image_processor.has_tesseract:
                try:
                    image, _ = self.image_processor.rotate_correction(image)
                    
                except Exception as e:
                    yield {"type": "info", "data": f"Error during rotate correction: {str(e)}"}
                    
            # Resize the image if max_dimension_pixels is specified
            if max_dimension_pixels is not None:
                try:
                    image, _ = self.image_processor.resize(image, max_dimension_pixels=max_dimension_pixels)
                except Exception as e:
                    yield {"type": "info", "data": f"Error resizing image: {str(e)}"}

            messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
            response_stream = self.vlm_engine.chat(
                    messages,
                    stream=True
                )
            for chunk in response_stream:
                yield {"type": "ocr_chunk", "data": chunk}
            

    def sequential_ocr(self, file_paths: Union[str, Iterable[str]], rotate_correction:bool=False, 
                       max_dimension_pixels:int=None, verbose:bool=False) -> List[OCRResult]:
        """
        This method inputs a file path or a list of file paths (image, PDF, TIFF) and performs OCR using the VLM inference engine.

        Parameters:
        -----------
        file_paths : Union[str, Iterable[str]]
            A file path or a list of file paths to process. Must be one of '.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        rotate_correction : bool, Optional
            If True, applies rotate correction to the images using pytesseract.
        max_dimension_pixels : int, Optional
            The maximum dimension of the image in pixels. Original dimensions will be resized to fit in. If None, no resizing is applied.
        verbose : bool, Optional
            If True, the function will print the output in terminal.
        
        Returns:
        --------
        List[OCRResult]
            A list of OCR result objects.
        """
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        ocr_results = []
        for file_path in file_paths:
            # Define OCRResult object
            ocr_result = OCRResult(input_dir=file_path, output_mode=self.output_mode)
            # get file extension
            file_ext = os.path.splitext(file_path)[1].lower()
            # Check file extension
            if file_ext not in SUPPORTED_IMAGE_EXTS:
                if verbose:
                    print(f"{Fore.RED}Unsupported file type:{Style.RESET_ALL} {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}")
                ocr_result.status = "error"
                ocr_result.add_page(text=f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}",
                                    image_processing_status={})
                ocr_results.append(ocr_result)
                continue

            filename = os.path.basename(file_path)
            
            try:
                # Load images from file
                if file_ext == '.pdf':
                    data_loader = PDFDataLoader(file_path) 
                elif file_ext in ['.tif', '.tiff']:
                    data_loader = TIFFDataLoader(file_path)
                else:
                    data_loader = ImageDataLoader(file_path)
                
                images = data_loader.get_all_pages()
            except Exception as e:
                if verbose:
                    print(f"{Fore.RED}Error processing file {filename}:{Style.RESET_ALL} {str(e)}")
                ocr_result.status = "error"
                ocr_result.add_page(text=f"Error processing file {filename}: {str(e)}", image_processing_status={})
                ocr_results.append(ocr_result)
                continue

            # Check if images were extracted
            if not images:
                if verbose:
                    print(f"{Fore.RED}No images extracted from file:{Style.RESET_ALL} {filename}. It might be empty or corrupted.")
                ocr_result.status = "error"
                ocr_result.add_page(text=f"No images extracted from file: {filename}. It might be empty or corrupted.",
                                    image_processing_status={})
                ocr_results.append(ocr_result)
                continue
            
            # OCR images
            for i, image in enumerate(images):
                image_processing_status = {}
                # Apply rotate correction if specified and tesseract is available
                if rotate_correction and self.image_processor.has_tesseract:
                    try:
                        image, rotation_angle = self.image_processor.rotate_correction(image)
                        image_processing_status["rotate_correction"] = {
                            "status": "success",
                            "rotation_angle": rotation_angle
                        }
                        if verbose:
                            print(f"{Fore.GREEN}Rotate correction applied for {filename} page {i} with angle {rotation_angle} degrees.{Style.RESET_ALL}")
                    except Exception as e:
                        image_processing_status["rotate_correction"] = {
                            "status": "error",
                            "error": str(e)
                        }
                        if verbose:
                            print(f"{Fore.RED}Error during rotate correction for {filename}:{Style.RESET_ALL} {rotation_angle['error']}. OCR continues without rotate correction.")

                # Resize the image if max_dimension_pixels is specified
                if max_dimension_pixels is not None:
                    try:
                        image, resized = self.image_processor.resize(image, max_dimension_pixels=max_dimension_pixels)
                        image_processing_status["resize"] = {
                            "status": "success",
                            "resized": resized
                        }
                        if verbose and resized:
                            print(f"{Fore.GREEN}Image resized for {filename} page {i} to fit within {max_dimension_pixels} pixels.{Style.RESET_ALL}")
                    except Exception as e:
                        image_processing_status["resize"] = {
                            "status": "error",
                            "error": str(e)
                        }
                        if verbose:
                            print(f"{Fore.RED}Error resizing image for {filename}:{Style.RESET_ALL} {resized['error']}. OCR continues without resizing.")

                try:
                    messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
                    response = self.vlm_engine.chat(
                        messages,
                        verbose=verbose,
                        stream=False
                    )
                    # Clean the response if output mode is markdown
                    if self.output_mode == "markdown":
                        response = clean_markdown(response)
                    
                    # Add the page to the OCR result
                    ocr_result.add_page(text=response, 
                                        image_processing_status=image_processing_status)
                
                except Exception as page_e:
                    ocr_result.status = "error"
                    ocr_result.add_page(text=f"Error during OCR for a page in {filename}: {str(page_e)}",
                                        image_processing_status={})
                    if verbose:
                        print(f"{Fore.RED}Error during OCR for a page in {filename}:{Style.RESET_ALL} {page_e}")

            # Add the OCR result to the list
            ocr_result.status = "success"
            ocr_results.append(ocr_result)

            if verbose:
                print(f"{Fore.BLUE}Successfully processed {filename} with {len(ocr_result)} pages.{Style.RESET_ALL}")
                for page in ocr_result:
                    print(page)
                    print("-" * 80)

        return ocr_results


    def concurrent_ocr(self, file_paths: Union[str, Iterable[str]], rotate_correction:bool=False, 
                       max_dimension_pixels:int=None, concurrent_batch_size: int=32, max_file_load: int=None) -> AsyncGenerator[OCRResult, None]:
        """
        First complete first out. Input and output order not guaranteed.
        This method inputs a file path or a list of file paths (image, PDF, TIFF) and performs OCR using the VLM inference engine. 
        Results are processed concurrently using asyncio.

        Parameters:
        -----------
        file_paths : Union[str, Iterable[str]]
            A file path or a list of file paths to process. Must be one of '.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        rotate_correction : bool, Optional
            If True, applies rotate correction to the images using pytesseract.
        max_dimension_pixels : int, Optional
            The maximum dimension of the image in pixels. Origianl dimensions will be resized to fit in. If None, no resizing is applied.
        concurrent_batch_size : int, Optional
            The number of concurrent VLM calls to make. 
        max_file_load : int, Optional
            The maximum number of files to load concurrently. If None, defaults to 2 times of concurrent_batch_size.
        
        Returns:
        --------
        AsyncGenerator[OCRResult, None]
            A generator that yields OCR result objects as they complete.
        """
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        
        if max_file_load is None:
            max_file_load = concurrent_batch_size * 2

        if not isinstance(max_file_load, int) or max_file_load <= 0:
            raise ValueError("max_file_load must be a positive integer")
        
        if self.image_processor.has_tesseract==False and rotate_correction:
            raise ImportError("pytesseract is not installed. Please install it to use rotate correction.")

        return self._ocr_async(file_paths=file_paths, 
                               rotate_correction=rotate_correction,
                               max_dimension_pixels=max_dimension_pixels,
                               concurrent_batch_size=concurrent_batch_size, 
                               max_file_load=max_file_load)
    

    async def _ocr_async(self, file_paths: Iterable[str], rotate_correction:bool=False, max_dimension_pixels:int=None, 
                         concurrent_batch_size: int=32, max_file_load: int=None) -> AsyncGenerator[OCRResult, None]:
        """
        Internal method to asynchronously process an iterable of file paths.
        Yields OCRResult objects as they complete. Order not guaranteed.
        concurrent_batch_size controls how many VLM calls are made concurrently.
        """
        vlm_call_semaphore = asyncio.Semaphore(concurrent_batch_size)
        file_load_semaphore = asyncio.Semaphore(max_file_load) 

        tasks = []
        for file_path in file_paths:
            task = self._ocr_file_with_semaphore(file_load_semaphore=file_load_semaphore, 
                                                 vlm_call_semaphore=vlm_call_semaphore, 
                                                 file_path=file_path, 
                                                 rotate_correction=rotate_correction,
                                                 max_dimension_pixels=max_dimension_pixels)
            tasks.append(task)

        
        for future in asyncio.as_completed(tasks):
            result: OCRResult = await future
            yield result
        
    async def _ocr_file_with_semaphore(self, file_load_semaphore:asyncio.Semaphore, vlm_call_semaphore:asyncio.Semaphore, 
                                       file_path:str, rotate_correction:bool=False, max_dimension_pixels:int=None) -> OCRResult:
        """
        This internal method takes a semaphore and OCR a single file using the VLM inference engine.
        """
        async with file_load_semaphore:
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            result = OCRResult(input_dir=file_path, output_mode=self.output_mode)
            # check file extension
            if file_ext not in SUPPORTED_IMAGE_EXTS:
                result.status = "error"
                result.add_page(text=f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}", 
                                image_processing_status={})
                return result
            
            try:
                # Load images from file
                if file_ext == '.pdf':
                    data_loader = PDFDataLoader(file_path) 
                elif file_ext in ['.tif', '.tiff']:
                    data_loader = TIFFDataLoader(file_path)
                else:
                    data_loader = ImageDataLoader(file_path)

            except Exception as e:
                result.status = "error"
                result.add_page(text=f"Error processing file {filename}: {str(e)}", image_processing_status={})
                return result

            try:
                page_processing_tasks = []
                for page_index in range(data_loader.get_page_count()):
                    task = self._ocr_page_with_semaphore(
                        vlm_call_semaphore=vlm_call_semaphore,
                        data_loader=data_loader,
                        page_index=page_index,
                        rotate_correction=rotate_correction,
                        max_dimension_pixels=max_dimension_pixels
                    )
                    page_processing_tasks.append(task)
                
                if page_processing_tasks:
                    processed_page_results = await asyncio.gather(*page_processing_tasks)
                    for text, image_processing_status in processed_page_results:
                        result.add_page(text=text, image_processing_status=image_processing_status)

            except Exception as e:
                result.status = "error"
                result.add_page(text=f"Error during OCR for {filename}: {str(e)}", image_processing_status={})
                return result

        # Set status to success if no errors occurred
        result.status = "success"
        return result

    async def _ocr_page_with_semaphore(self, vlm_call_semaphore: asyncio.Semaphore, data_loader: DataLoader,
                                       page_index:int, rotate_correction:bool=False, max_dimension_pixels:int=None) -> Tuple[str, Dict[str, str]]:
        """
        This internal method takes a semaphore and OCR a single image/page using the VLM inference engine.

        Returns:
        -------
        Tuple[str, Dict[str, str]]
            A tuple containing the OCR text and a dictionary with image processing status.
        """
        async with vlm_call_semaphore:
            image = await data_loader.get_page_async(page_index)
            image_processing_status = {}
            # Apply rotate correction if specified and tesseract is available
            if rotate_correction and self.image_processor.has_tesseract:
                try:
                    image, rotation_angle = await self.image_processor.rotate_correction_async(image)
                    image_processing_status["rotate_correction"] = {
                        "status": "success",
                        "rotation_angle": rotation_angle
                    }
                except Exception as e:
                    image_processing_status["rotate_correction"] = {
                        "status": "error",
                        "error": str(e)
                    }

            # Resize the image if max_dimension_pixels is specified
            if max_dimension_pixels is not None:
                try:
                    image, resized = await self.image_processor.resize_async(image, max_dimension_pixels=max_dimension_pixels)
                    image_processing_status["resize"] = {
                        "status": "success",
                        "resized": resized
                    }
                except Exception as e:
                    image_processing_status["resize"] = {
                        "status": "error",
                        "error": str(e)
                    }

            messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
            ocr_text = await self.vlm_engine.chat_async( 
                messages,
            )
            if self.output_mode == "markdown":
                ocr_text = clean_markdown(ocr_text)
            return ocr_text, image_processing_status