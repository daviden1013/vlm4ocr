import os
from typing import List, Dict, Union, Generator, Iterable
import importlib
import asyncio
from vlm4ocr.utils import get_images_from_pdf, get_images_from_tiff, get_image_from_file, clean_markdown
from vlm4ocr.vlm_engines import VLMEngine

SUPPORTED_IMAGE_EXTS = ['.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']


class OCREngine:
    def __init__(self, vlm_engine:VLMEngine, output_mode:str="markdown", system_prompt:str=None, user_prompt:str=None, page_delimiter:str="auto"):
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
        page_delimiter : str, Optional
            The delimiter to use between PDF pages. 
            if 'auto', it will be set to the default page delimiter for the output mode: 
            'markdown' -> '\n\n---\n\n'
            'HTML' -> '<br><br>'
            'text' -> '\n\n---\n\n'
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
            file_path = importlib.resources.files('vlm4ocr.assets.default_prompt_templates').joinpath(f'ocr_{self.output_mode}_system_prompt.txt')
            with open(file_path, 'r', encoding='utf-8') as f:
                self.system_prompt =  f.read()

        # User prompt
        if isinstance(user_prompt, str) and user_prompt:
            self.user_prompt = user_prompt
        else:
            file_path = importlib.resources.files('vlm4ocr.assets.default_prompt_templates').joinpath(f'ocr_{self.output_mode}_user_prompt.txt')
            with open(file_path, 'r', encoding='utf-8') as f:
                self.user_prompt =  f.read()

        # Page delimiter
        if isinstance(page_delimiter, str):
            if page_delimiter == "auto":
                if self.output_mode == "markdown":
                    self.page_delimiter = "\n\n---\n\n"
                elif self.output_mode == "HTML":
                    self.page_delimiter = "<br><br>"
                else:
                    self.page_delimiter = "\n\n---\n\n"
            else:
                self.page_delimiter = page_delimiter
        else:
            raise ValueError("page_delimiter must be a string")
        

    def stream_ocr(self, file_path: str, max_new_tokens:int=4096, temperature:float=0.0, **kwrs) -> Generator[str, None, None]:
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
        Generator[str, None, None]
            A generator that yields the output.
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
            

    def run_ocr(self, file_paths: Union[str, Iterable[str]], max_new_tokens:int=4096, temperature:float=0.0, 
                verbose:bool=False, concurrent:bool=False, concurrent_batch_size:int=32, **kwrs) -> Union[str, Generator[str, None, None]]:
        """
        This method takes a list of file paths (image, PDF, TIFF) and perform OCR using the VLM inference engine.

        Parameters:
        -----------
        file_paths : Union[str, Iterable[str]]
            A file path or a list of file paths to process. Must be one of '.pdf', '.tif', '.tiff, '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        max_new_tokens : int, Optional
            The maximum number of tokens to generate. 
        temperature : float, Optional
            The temperature to use for sampling. 
        verbose : bool, Optional
            If True, the function will print the output in terminal. 
        concurrent : bool, Optional
            If True, the function will process the files concurrently.
        concurrent_batch_size : int, Optional
            The number of images/pages to process concurrently. 
        """
        # if file_paths is a string, convert it to a list
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        
        if not isinstance(file_paths, Iterable):
            raise TypeError("file_paths must be a string or an iterable of strings")
        
        # check if all file paths are valid
        for file_path in file_paths:
            if not isinstance(file_path, str):
                raise TypeError("file_paths must be a string or an iterable of strings")
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext not in SUPPORTED_IMAGE_EXTS:
                raise ValueError(f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}")

        # Concurrent processing
        if concurrent:
            # Check concurrent_batch_size
            if concurrent_batch_size <= 0:
                raise ValueError("concurrent_batch_size must be greater than 0")

            if verbose:
                Warning("verbose is not supported for concurrent processing.", UserWarning)

            return asyncio.run(self._run_ocr_async(file_paths, 
                                                   max_new_tokens=max_new_tokens, 
                                                   temperature=temperature, 
                                                   concurrent_batch_size=concurrent_batch_size, 
                                                   **kwrs))
        
        # Sync processing
        return self._run_ocr(file_paths, max_new_tokens=max_new_tokens, temperature=temperature, verbose=verbose, **kwrs)
    

    def _run_ocr(self, file_paths: Union[str, Iterable[str]], max_new_tokens:int=4096, 
                 temperature:float=0.0, verbose:bool=False, **kwrs) -> Iterable[str]:
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
        Iterable[str]
            A list of strings containing the OCR results.
        """
        ocr_results = []
        for file_path in file_paths:
            file_ext = os.path.splitext(file_path)[1].lower()
            # PDF or TIFF
            if file_ext in ['.pdf', '.tif', '.tiff']:
                images = get_images_from_pdf(file_path) if file_ext == '.pdf' else get_images_from_tiff(file_path)
                if not images:
                    raise ValueError(f"No images extracted from file: {file_path}")
                results = []
                for image in images:
                    messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
                    response = self.vlm_engine.chat(
                        messages,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature,
                        verbose=verbose,
                        stream=False,
                        **kwrs
                    )
                    results.append(response)

                ocr_text = self.page_delimiter.join(results)
            # Image
            else:
                image = get_image_from_file(file_path)
                messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, image)
                ocr_text = self.vlm_engine.chat(
                    messages,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    verbose=verbose,
                    stream=False,
                    **kwrs
                )
            
            # Clean markdown
            if self.output_mode == "markdown":
                ocr_text = clean_markdown(ocr_text)
            ocr_results.append(ocr_text)

        return ocr_results


    async def _run_ocr_async(self, file_paths: Union[str, Iterable[str]], max_new_tokens:int=4096, 
                       temperature:float=0.0, concurrent_batch_size:int=32, **kwrs) -> List[str]:
        """
        This is the async version of the _run_ocr method. 
        """
        # flatten pages/images in file_paths
        flat_page_list = []
        for file_path in file_paths:
            file_ext = os.path.splitext(file_path)[1].lower()
            # PDF or TIFF
            if file_ext in ['.pdf', '.tif', '.tiff']:
                images = get_images_from_pdf(file_path) if file_ext == '.pdf' else get_images_from_tiff(file_path)
                if not images:
                    flat_page_list.append({'file_path': file_path, 'file_type': "PDF/TIFF", "image": image, "page_num": 0, "total_page_count": 0})
                for page_num, image in enumerate(images):
                    flat_page_list.append({'file_path': file_path, 'file_type': "PDF/TIFF", "image": image, "page_num": page_num, "total_page_count": len(images)})
            # Image
            else:
                image = get_image_from_file(file_path)
                flat_page_list.append({'file_path': file_path, 'file_type': "image", "image": image})

        # Process images with asyncio.Semaphore
        semaphore = asyncio.Semaphore(concurrent_batch_size)
        async def semaphore_helper(page:List[Dict[str,str]], max_new_tokens:int, temperature:float, **kwrs):
            try:
                messages = self.vlm_engine.get_ocr_messages(self.system_prompt, self.user_prompt, page["image"])
                async with semaphore:
                    async_task = self.vlm_engine.chat_async(
                        messages,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature,
                        **kwrs
                    )
                return await async_task
            except Exception as e:
                print(f"Error processing image: {e}")
                return f"[Error: {e}]"

        tasks = []
        for page in flat_page_list:
            async_task = semaphore_helper(
                page,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                **kwrs
            )
            tasks.append(asyncio.create_task(async_task))

        responses = await asyncio.gather(*tasks)

        # Restructure the results
        ocr_results = []
        page_text_buffer = ""
        for page, ocr_text in zip(flat_page_list, responses):
            # PDF or TIFF
            if page['file_type'] == "PDF/TIFF":                
                page_text_buffer += ocr_text + self.page_delimiter
                if page['page_num'] == page['total_page_count'] - 1:
                    if self.output_mode == "markdown":
                        page_text_buffer = clean_markdown(page_text_buffer)
                    ocr_results.append(page_text_buffer)
                    page_text_buffer = ""
            # Image
            if page['file_type'] == "image":
                if self.output_mode == "markdown":
                    ocr_text = clean_markdown(ocr_text)
                ocr_results.append(ocr_text)
            
        return ocr_results

