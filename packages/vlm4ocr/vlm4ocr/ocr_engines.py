import os
from typing import List, Dict, Union, Generator, AsyncGenerator, Iterable
import importlib
import asyncio
from PIL import Image
from vlm4ocr.utils import get_images_from_pdf, get_images_from_tiff, get_image_from_file, clean_markdown
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


    def stream_ocr(self, file_path: str, max_new_tokens:int=4096, temperature:float=0.0, **kwrs) -> Generator[Dict[str, str], None, None]:
        """
        This method inputs a file path (image or PDF) and stream OCR results in real-time. This is useful for frontend applications.
        Yields dictionaries with 'type' ('ocr_chunk' or 'page_delimiter') and 'data'.

        Parameters:
        -----------
        file_path : str
            The path to the image or PDF file. Must be one of '.pdf', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        max_new_tokens : int, Optional
            The maximum number of tokens to generate.
        temperature : float, Optional
            The temperature to use for sampling.

        Returns:
        --------
        Generator[Dict[str, str], None, None]
            A generator that yields the output:
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

        # PDF or TIFF
        if file_ext in ['.pdf', '.tif', '.tiff']:
            images = get_images_from_pdf(file_path) if file_ext == '.pdf' else get_images_from_tiff(file_path)
            if not images:
                raise ValueError(f"No images extracted from file: {file_path}")
            for i, image in enumerate(images):
                messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
                response_stream = self.vlm_engine.chat(
                    messages,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    stream=True,
                    **kwrs
                )
                for chunk in response_stream:
                    yield {"type": "ocr_chunk", "data": chunk}

                if i < len(images) - 1:
                    yield {"type": "page_delimiter", "data": self.page_delimiter}

        # Image
        else:
            image = get_image_from_file(file_path)
            messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
            response_stream = self.vlm_engine.chat(
                    messages,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    stream=True,
                    **kwrs
                )
            for chunk in response_stream:
                yield {"type": "ocr_chunk", "data": chunk}
            

    def sequential_ocr(self, file_paths: Union[str, Iterable[str]], max_new_tokens:int=4096, 
                 temperature:float=0.0, verbose:bool=False, **kwrs) -> List[OCRResult]:
        """
        This method inputs a file path or a list of file paths (image, PDF, TIFF) and performs OCR using the VLM inference engine.

        Parameters:
        -----------
        file_paths : Union[str, Iterable[str]]
            A file path or a list of file paths to process. Must be one of '.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        max_new_tokens : int, Optional
            The maximum number of tokens to generate.
        temperature : float, Optional
            The temperature to use for sampling.
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
                ocr_result.status = "error"
                ocr_result.add_page(f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}")
                ocr_results.append(ocr_result)
                continue

            filename = os.path.basename(file_path)
            
            try:
                # PDF or TIFF
                if file_ext in ['.pdf', '.tif', '.tiff']:
                    images = get_images_from_pdf(file_path) if file_ext == '.pdf' else get_images_from_tiff(file_path)
                # Image
                else:
                    images = [get_image_from_file(file_path)]
            except Exception as e:
                ocr_result.status = "error"
                ocr_result.add_page(f"Error processing file {filename}: {str(e)}")
                ocr_results.append(ocr_result)
                continue

            # Check if images were extracted
            if not images:
                ocr_result.status = "error"
                ocr_result.add_page(f"No images extracted from file: {filename}. It might be empty or corrupted.")
                ocr_results.append(ocr_result)
                continue
            
            # Process images
            for image in images:
                try:
                    messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
                    response = self.vlm_engine.chat(
                        messages,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature,
                        verbose=verbose,
                        stream=False,
                        **kwrs
                    )
                    if self.output_mode == "markdown":
                        response = clean_markdown(response)
                    
                    ocr_result.add_page(response)
                
                except Exception as page_e:
                    ocr_result.status = "error"
                    ocr_result.add_page(f"Error during OCR for a page in {filename}: {str(page_e)}")
                    if verbose:
                        print(f"Error during OCR for a page in {filename}: {page_e}")

            # Add the OCR result to the list
            ocr_result.status = "success"
            ocr_results.append(ocr_result)

            if verbose:
                print(f"Successfully processed {filename} with {len(ocr_result)} pages.")
                for page in ocr_result:
                    print(page)
                    print("-" * 80)

        return ocr_results


    def concurrent_ocr(self, file_paths: Union[str, Iterable[str]], max_new_tokens: int = 4096,
                       temperature: float = 0.0, concurrent_batch_size: int = 32, **kwrs) -> AsyncGenerator[OCRResult, None]:
        """
        First complete first out. Input and output order not guaranteed.
        This method inputs a file path or a list of file paths (image, PDF, TIFF) and performs OCR using the VLM inference engine. 
        Results are processed concurrently using asyncio.

        Parameters:
        -----------
        file_paths : Union[str, Iterable[str]]
            A file path or a list of file paths to process. Must be one of '.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        max_new_tokens : int, Optional
            The maximum number of tokens to generate.
        temperature : float, Optional
            The temperature to use for sampling.
        concurrent_batch_size : int, Optional
            The number of concurrent VLM calls to make. 
        
        Returns:
        --------
        AsyncGenerator[OCRResult, None]
            A generator that yields OCR result objects as they complete.
        """
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        
        return self._ocr_async(file_paths, max_new_tokens, temperature, concurrent_batch_size, **kwrs)
    

    async def _ocr_page_with_semaphore(self, semaphore_for_vlm: asyncio.Semaphore, filename: str, 
                                       image:Image.Image, max_new_tokens:int, temperature:float, **kwrs) -> str:
        """
        This internal method takes a semaphore and OCR a single image/page using the VLM inference engine.
        """
        async with semaphore_for_vlm:
            messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
            ocr_text = await self.vlm_engine.chat_async( 
                messages,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                **kwrs
            )
            if self.output_mode == "markdown":
                ocr_text = clean_markdown(ocr_text)
            return ocr_text
            

    async def _ocr_file_with_semaphore(self, semaphore_for_vlm:asyncio.Semaphore, file_path:str, 
                                       max_new_tokens:int, temperature:float, **kwrs) -> OCRResult:
        """
        This internal method takes a semaphore and OCR a single file using the VLM inference engine.
        """
        filename = os.path.basename(file_path)
        file_ext = os.path.splitext(file_path)[1].lower()
        result = OCRResult(input_dir=file_path, output_mode=self.output_mode)
        # check file extension
        if file_ext not in SUPPORTED_IMAGE_EXTS:
            result.status = "error"
            result.add_page(f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}")
            return result
        
        try:
            if file_ext in ['.pdf', '.tif', '.tiff']:
                images = get_images_from_pdf(file_path) if file_ext == '.pdf' else get_images_from_tiff(file_path)
                if not images:
                    print(f"Warning: No images extracted from {filename}. It might be empty or corrupted.")

            else: 
                images = [get_image_from_file(file_path)]
        except Exception as e:
            result.status = "error"
            result.add_page(f"Error processing file {filename}: {str(e)}")
            return result

        try:
            page_processing_tasks = []
            for image in images:
                task = self._ocr_page_with_semaphore(
                    semaphore_for_vlm,
                    filename=filename,
                    image=image,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    **kwrs 
                )
                page_processing_tasks.append(task)

            
            if page_processing_tasks:
                processed_page_texts = await asyncio.gather(*page_processing_tasks)
                for text in processed_page_texts:
                    result.add_page(text)

        except Exception as e:
            result.status = "error"
            result.add_page(f"Error during OCR for {filename}: {str(e)}")
            return result

        # Set status to success if no errors occurred
        result.status = "success"
        return result
    

    async def _ocr_async(self, file_paths: Iterable[str], max_new_tokens: int,
                         temperature: float, concurrent_batch_size: int, **kwrs) -> AsyncGenerator[OCRResult, None]:
        """
        Internal method to asynchronously process an iterable of file paths.
        Yields OCRResult objects as they complete. Order not guaranteed.
        concurrent_batch_size controls how many VLM calls are made concurrently.
        """
        vlm_call_semaphore = asyncio.Semaphore(concurrent_batch_size)

        tasks = []
        for file_path in file_paths:
            task = self._ocr_file_with_semaphore(vlm_call_semaphore, file_path, max_new_tokens, temperature, **kwrs)
            tasks.append(task)

        
        for future in asyncio.as_completed(tasks):
            result: OCRResult = await future
            yield result
        