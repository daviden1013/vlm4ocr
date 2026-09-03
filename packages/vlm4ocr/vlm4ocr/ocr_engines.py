import os
from typing import Any, Tuple, List, Dict, Union, Generator, AsyncGenerator, Iterable, Literal
import importlib
import asyncio
from dataclasses import asdict
from colorama import Fore, Style
import json
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from vlm4ocr.utils import (DataLoader, clean_markdown, extract_json, get_default_page_delimiter,
                           get_data_loader, default_page_load_workers, SUPPORTED_IMAGE_EXTS)
from vlm4ocr.pdf_backends import DEFAULT_PDF_DPI
from vlm4ocr.preprocessing import ImageProcessor, RotateCorrectionMethod
from vlm4ocr.data_types import OCRResult, OCRPage, FewShotExample, BBoxFormat
from vlm4ocr.exceptions import VLM4OCRError, DocumentLoadError, VLMError
from vlm4ocr.vlm_engines import VLMEngine, MessagesLogger


class OCREngine:
    def __init__(self, vlm_engine: VLMEngine, output_mode: str = "markdown",
                 system_prompt: Union[str, None, Literal[False]] = None,
                 user_prompt: Union[str, None, Literal[False]] = None,
                 bbox_format: Union[BBoxFormat, None] = None,
                 page_load_workers: Union[int, None] = None,
                 pdf_backend: Union[str, None] = None,
                 pdf_dpi: int = DEFAULT_PDF_DPI):
        """
        This class inputs a image or PDF file path and processes them using a VLM inference engine. Outputs plain text or markdown.

        Parameters:
        -----------
        vlm_engine : VLMEngine
            The VLM inference engine to use for OCR.
        output_mode : str, Optional
            The output format. Must be 'markdown', 'HTML', 'text', 'JSON', or 'bbox'.
        system_prompt : str | None | False, Optional
            Controls the system prompt sent to the model.
            - None (default): use the built-in default system prompt for the selected output_mode.
            - str: use this custom system prompt.
            - False: send no system prompt at all.
        user_prompt : str | None | False, Optional
            Controls the user-turn text sent alongside the image.
            - None (default): use the built-in default user prompt, or empty string in bbox mode
              (triggers full-text OCR).
            - str: custom user prompt. In bbox mode a non-empty string triggers targeted extraction.
            - False: send no user prompt text (image only).
        bbox_format : BBoxFormat | None, Optional
            Override the auto-resolved BBoxFormat for bbox output mode. When None (default) the
            format is resolved from the registry based on vlm_engine.model.
        page_load_workers : int | None, Optional
            Size of the thread pool used to load/rasterize pages in the async methods.
            Defaults to one worker per CPU, capped at 32. This pool is separate from
            asyncio's default executor, so page loading cannot starve the preprocessing
            work (resize, tesseract OSD) that also runs in threads. It is independent of
            concurrent_batch_size, which caps VLM calls rather than page loads.
        pdf_backend : str | None, Optional
            Which PDF rendering backend to use: 'pypdfium2', 'pdf2image', or 'pymupdf'.
            Required to process PDF input — vlm4ocr depends on no PDF library, so there is
            no default and no automatic fallback. Ignored for image and TIFF input.
        pdf_dpi : int, Optional
            Resolution at which PDF pages are rendered, applied identically across
            backends so page images are comparable. Defaults to 200.
        """
        # Check inference engine
        if not isinstance(vlm_engine, VLMEngine):
            raise TypeError("vlm_engine must be an instance of VLMEngine")
        self.vlm_engine = vlm_engine

        # Check output mode
        if output_mode not in ["markdown", "HTML", "text", "JSON", "bbox"]:
            raise ValueError("output_mode must be 'markdown', 'HTML', 'text', 'JSON', or 'bbox'.")
        self.output_mode = output_mode

        # Resolve BBoxFormat (only used in bbox mode, but resolved eagerly so init fails fast)
        if output_mode == "bbox":
            from vlm4ocr.bbox import resolve_bbox_format
            if bbox_format is not None:
                if not isinstance(bbox_format, BBoxFormat):
                    raise TypeError("bbox_format must be a BBoxFormat instance or None")
                self.bbox_format = bbox_format
            else:
                self.bbox_format = resolve_bbox_format(self.vlm_engine.model)
        else:
            self.bbox_format = None

        # System prompt
        if system_prompt is False:
            self.system_prompt = None
        elif isinstance(system_prompt, str) and system_prompt:
            self.system_prompt = system_prompt
        else:
            if output_mode == "bbox":
                prompt_file = self.bbox_format.system_prompt_file
            else:
                prompt_file = f'ocr_{self.output_mode}_system_prompt.txt'
            prompt_template_path = importlib.resources.files('vlm4ocr.assets.default_prompt_templates').joinpath(prompt_file)
            with prompt_template_path.open('r', encoding='utf-8') as f:
                self.system_prompt = f.read()

        # User prompt
        if user_prompt is False:
            self.user_prompt = None
        elif isinstance(user_prompt, str) and user_prompt:
            self.user_prompt = user_prompt
        else:
            if self.output_mode == "JSON":
                raise ValueError("user_prompt must be provided when output_mode is 'JSON' to define the JSON structure.")
            if self.output_mode == "bbox":
                # None / empty → full-text OCR (empty user text)
                self.user_prompt = ""
            else:
                prompt_template_path = importlib.resources.files('vlm4ocr.assets.default_prompt_templates').joinpath(f'ocr_{self.output_mode}_user_prompt.txt')
                with prompt_template_path.open('r', encoding='utf-8') as f:
                    self.user_prompt = f.read()

        # Image processor
        self.image_processor = ImageProcessor(vlm_engine=self.vlm_engine)

        # PDF loading options; validated lazily, when a PDF is actually loaded.
        self.pdf_backend = pdf_backend
        self.pdf_dpi = pdf_dpi

        # Dedicated pool for page loading. Threads are spawned on demand, so an unused
        # engine costs nothing.
        if page_load_workers is None:
            page_load_workers = default_page_load_workers()
        if not isinstance(page_load_workers, int) or page_load_workers <= 0:
            raise ValueError("page_load_workers must be a positive integer")
        self.page_load_workers = page_load_workers
        self._page_load_executor = ThreadPoolExecutor(max_workers=page_load_workers,
                                                      thread_name_prefix="vlm4ocr-pageload")

    def close(self):
        """ Shuts down the page-loading thread pool. Optional; the pool is also joined at interpreter exit. """
        self._page_load_executor.shutdown(wait=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


    def stream_ocr(self, file_path: str, rotate_correction:Union[RotateCorrectionMethod, Literal[False]]=False,
                   max_dimension_pixels:int=None,
                   few_shot_examples:List[FewShotExample]=None) -> Generator[Dict[str, str], None, None]:
        """
        This method inputs a file path (image or PDF) and stream OCR results in real-time. This is useful for frontend applications.
        Yields dictionaries with 'type' ('ocr_chunk' or 'page_delimiter') and 'data'.

        Parameters:
        -----------
        file_path : str
            The path to the image or PDF file. Must be one of '.pdf', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        rotate_correction : {"tesseract", "vlm", False}, Optional
            Rotation correction method. "tesseract" uses pytesseract OSD; "vlm" prompts the VLM engine for orientation. False disables correction.
        max_dimension_pixels : int, Optional
            The maximum dimension of the image in pixels. Original dimensions will be resized to fit in. If None, no resizing is applied.
        few_shot_examples : List[FewShotExample], Optional
            list of few-shot examples.

        Returns:
        --------
        Generator[Dict[str, str], None, None]
            A generator that yields the output:
            {"type": "info", "data": msg}
            {"type": "ocr_chunk", "data": chunk}
            {"type": "page_delimiter", "data": page_delimiter}
            {"type": "error", "data": message, "error": error_dict}

        A document that cannot be loaded yields one "error" event and then raises, so
        stream consumers can render the failure and direct callers still get the exception.
        "data" is always a human-readable string; "error" carries VLM4OCRError.to_dict().
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
            # Emit the failure as a stream event before propagating, so a consumer rendering
            # the stream can display it; the exception still reaches direct API callers.
            try:
                data_loader = get_data_loader(file_path, executor=self._page_load_executor,
                                                  pdf_backend=self.pdf_backend, pdf_dpi=self.pdf_dpi)
                images = data_loader.get_all_pages()
            except VLM4OCRError as e:
                yield {"type": "error", "data": str(e), "error": e.to_dict()}
                raise
            # Check if images were extracted
            if not images:
                raise ValueError(f"No images extracted from file: {file_path}")

            # OCR each image
            for i, image in enumerate(images):
                # Apply rotate correction if specified
                if rotate_correction:
                    try:
                        image, _ = self.image_processor.rotate_correction(image, method=rotate_correction)
                    except Exception as e:
                        yield {"type": "info", "data": f"Error during rotate correction: {str(e)}"}

                # Resize the image if max_dimension_pixels is specified
                if max_dimension_pixels is not None:
                    try:
                        image, _ = self.image_processor.resize(image, max_dimension_pixels=max_dimension_pixels)
                    except Exception as e:
                        yield {"type": "info", "data": f"Error resizing image: {str(e)}"}

                # Get OCR messages
                messages = self.vlm_engine.get_ocr_messages(system_prompt=self.system_prompt,
                                                            user_prompt=self.user_prompt,
                                                            image=image,
                                                            few_shot_examples=few_shot_examples)

                # Stream response
                response_stream = self.vlm_engine.chat_stream(messages)
                buffered_chunks = []
                for chunk in response_stream:
                    if chunk["type"] == "response":
                        yield {"type": "ocr_chunk", "data": chunk["data"]}
                        buffered_chunks.append(chunk["data"])

                # bbox post-processing after stream completes
                if self.output_mode == "bbox":
                    from vlm4ocr.bbox import parse_bbox_response
                    img_w, img_h = image.size
                    raw_response = "".join(buffered_chunks)
                    bboxes = parse_bbox_response(raw_response, self.bbox_format, img_w, img_h)
                    yield {"type": "bbox_result", "data": {
                        "page_idx": i,
                        "bboxes": [asdict(b) for b in bboxes],
                        "image_width": img_w,
                        "image_height": img_h,
                    }}

                if i < len(images) - 1:
                    yield {"type": "page_delimiter", "data": get_default_page_delimiter(self.output_mode)}

        # Image
        else:
            try:
                data_loader = get_data_loader(file_path, executor=self._page_load_executor,
                                                  pdf_backend=self.pdf_backend, pdf_dpi=self.pdf_dpi)
                image = data_loader.get_page(0)
            except VLM4OCRError as e:
                yield {"type": "error", "data": str(e), "error": e.to_dict()}
                raise

            # Apply rotate correction if specified
            if rotate_correction:
                try:
                    image, _ = self.image_processor.rotate_correction(image, method=rotate_correction)
                except Exception as e:
                    yield {"type": "info", "data": f"Error during rotate correction: {str(e)}"}

            # Resize the image if max_dimension_pixels is specified
            if max_dimension_pixels is not None:
                try:
                    image, _ = self.image_processor.resize(image, max_dimension_pixels=max_dimension_pixels)
                except Exception as e:
                    yield {"type": "info", "data": f"Error resizing image: {str(e)}"}

            # Get OCR messages
            messages = self.vlm_engine.get_ocr_messages(system_prompt=self.system_prompt,
                                                        user_prompt=self.user_prompt,
                                                        image=image,
                                                        few_shot_examples=few_shot_examples)
            # Stream response
            response_stream = self.vlm_engine.chat_stream(messages)
            buffered_chunks = []
            for chunk in response_stream:
                if chunk["type"] == "response":
                    yield {"type": "ocr_chunk", "data": chunk["data"]}
                    buffered_chunks.append(chunk["data"])

            # bbox post-processing after stream completes
            if self.output_mode == "bbox":
                from vlm4ocr.bbox import parse_bbox_response
                img_w, img_h = image.size
                raw_response = "".join(buffered_chunks)
                bboxes = parse_bbox_response(raw_response, self.bbox_format, img_w, img_h)
                yield {"type": "bbox_result", "data": {
                    "page_idx": 0,
                    "bboxes": [asdict(b) for b in bboxes],
                    "image_width": img_w,
                    "image_height": img_h,
                }}
            

    def sequential_ocr(self, file_paths: Union[str, Iterable[str]],
                       rotate_correction:Union[RotateCorrectionMethod, Literal[False]]=False,
                       max_dimension_pixels:int=None, verbose:bool=False, few_shot_examples:List[FewShotExample]=None) -> List[OCRResult]:
        """
        This method inputs a file path or a list of file paths (image, PDF, TIFF) and performs OCR using the VLM inference engine.

        Parameters:
        -----------
        file_paths : Union[str, Iterable[str]]
            A file path or a list of file paths to process. Must be one of '.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        rotate_correction : {"tesseract", "vlm", False}, Optional
            Rotation correction method. "tesseract" uses pytesseract OSD; "vlm" prompts the VLM engine for orientation. False disables correction.
        max_dimension_pixels : int, Optional
            The maximum dimension of the image in pixels. Original dimensions will be resized to fit in. If None, no resizing is applied.
        verbose : bool, Optional
            If True, the function will print the output in terminal.
        few_shot_examples : List[FewShotExample], Optional
            list of few-shot examples. Each example is a dict with keys "image" (PIL.Image.Image) and "text" (str).
        
        Returns:
        --------
        List[OCRResult]
            A list of OCR result objects.
        """
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        # Iterate through file paths
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
                ocr_result.set_error(
                    DocumentLoadError(f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}",
                                      file_path=file_path),
                    text=f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}")
                ocr_results.append(ocr_result)
                continue

            filename = os.path.basename(file_path)
            
            try:
                # Load images from file
                data_loader = get_data_loader(file_path, executor=self._page_load_executor,
                                              pdf_backend=self.pdf_backend, pdf_dpi=self.pdf_dpi)
                images = data_loader.get_all_pages()
            except Exception as e:
                if verbose:
                    print(f"{Fore.RED}Error processing file {filename}:{Style.RESET_ALL} {str(e)}")
                error = e if isinstance(e, VLM4OCRError) else DocumentLoadError(
                    f"Failed to load file '{filename}'.", file_path=file_path, cause=e)
                ocr_result.set_error(error, text=f"Error processing file {filename}: {str(e)}")
                ocr_results.append(ocr_result)
                continue

            # Check if images were extracted
            if not images:
                if verbose:
                    print(f"{Fore.RED}No images extracted from file:{Style.RESET_ALL} {filename}. It might be empty or corrupted.")
                ocr_result.set_error(
                    DocumentLoadError(f"No images extracted from file '{filename}'. It might be empty or corrupted.",
                                      file_path=file_path),
                    text=f"No images extracted from file: {filename}. It might be empty or corrupted.")
                ocr_results.append(ocr_result)
                continue
            
            # OCR images
            load_info = data_loader.get_load_info()
            for i, image in enumerate(images):
                image_processing_status = {"page_load": {**load_info, "size": list(image.size)}}
                # Apply rotate correction if specified
                if rotate_correction:
                    try:
                        image, rotation_angle = self.image_processor.rotate_correction(image, method=rotate_correction)
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
                        original_size = list(image.size)
                        image, resized = self.image_processor.resize(image, max_dimension_pixels=max_dimension_pixels)
                        image_processing_status["resize"] = {
                            "status": "success",
                            "resized": resized,
                            "original_size": original_size,
                            "final_size": list(image.size)
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
                    messages = self.vlm_engine.get_ocr_messages(system_prompt=self.system_prompt,
                                                                user_prompt=self.user_prompt,
                                                                image=image,
                                                                few_shot_examples=few_shot_examples)
                    # Define a messages logger to capture messages
                    messages_logger = MessagesLogger()
                    # Generate response
                    response = self.vlm_engine.chat(
                        messages,
                        verbose=verbose,
                        messages_logger=messages_logger
                    )
                    ocr_text = response["response"]
                    bboxes = None
                    img_w = img_h = None

                    # Mode-specific post-processing
                    if self.output_mode == "markdown":
                        ocr_text = clean_markdown(ocr_text)
                    elif self.output_mode == "JSON":
                        json_list = extract_json(ocr_text)
                        ocr_text = json.dumps(json_list, indent=4)
                    elif self.output_mode == "bbox":
                        from vlm4ocr.bbox import parse_bbox_response
                        img_w, img_h = image.size
                        bboxes = parse_bbox_response(ocr_text, self.bbox_format, img_w, img_h)
                        ocr_text = "\n".join(item.text for item in bboxes)

                    # Add the page to the OCR result
                    ocr_result.add_page(text=ocr_text,
                                        image_processing_status=image_processing_status,
                                        bboxes=bboxes,
                                        image_width=img_w,
                                        image_height=img_h)

                    # Add messages log to the OCR result
                    ocr_result.add_messages_to_log(messages_logger.get_messages_log())

                except Exception as page_e:
                    page_error = page_e if isinstance(page_e, VLM4OCRError) else VLMError(
                        f"OCR failed for page {i} of '{filename}'.",
                        file_path=file_path, page_index=i, cause=page_e)
                    ocr_result.add_page_error(
                        page_error, text=f"Error during OCR for a page in {filename}: {str(page_e)}")
                    if verbose:
                        print(f"{Fore.RED}Error during OCR for a page in {filename}:{Style.RESET_ALL} {page_e}")

            # Add the OCR result to the list
            if ocr_result.status != "error":
                ocr_result.status = "success"
            ocr_results.append(ocr_result)

            if verbose:
                print(f"{Fore.BLUE}Processed {filename} with {len(ocr_result)} pages.{Style.RESET_ALL}")
                for page in ocr_result:
                    print(page)
                    print("-" * 80)

        return ocr_results


    async def ocr_image_async(self, image: Image.Image, few_shot_examples: List[FewShotExample] = None,
                              messages_logger: MessagesLogger = None) -> OCRPage:
        """
        Runs OCR on a single in-memory image using this engine's configured prompt and
        output_mode, and returns a standalone OCRPage. This is the atomic unit that the
        pipelines build on.

        No image preprocessing (rotate / resize) is applied here — the caller owns that,
        so classify-then-extract flows can preprocess a page once and share the result.

        Parameters:
        -----------
        image : PIL.Image.Image
            The image to OCR (already preprocessed, if desired).
        few_shot_examples : List[FewShotExample], Optional
            list of few-shot examples.
        messages_logger : MessagesLogger, Optional
            If provided, the request/response messages of this call are logged into it.

        Returns:
        --------
        OCRPage
            A standalone page not yet placed in an OCRResult (image_processing_status={},
            _page_idx=0, _source_path=""). Contains the OCR text, plus bboxes and
            image_width/image_height in bbox output mode.
        """
        messages = self.vlm_engine.get_ocr_messages(system_prompt=self.system_prompt,
                                                    user_prompt=self.user_prompt,
                                                    image=image,
                                                    few_shot_examples=few_shot_examples)
        response = await self.vlm_engine.chat_async(messages, messages_logger=messages_logger)
        ocr_text = response["response"]
        bboxes = None
        img_w = img_h = None

        # Mode-specific post-processing (mirrors the concurrent/sequential paths).
        if self.output_mode == "markdown":
            ocr_text = clean_markdown(ocr_text)
        elif self.output_mode == "JSON":
            json_list = extract_json(ocr_text)
            ocr_text = json.dumps(json_list, indent=4)
        elif self.output_mode == "bbox":
            from vlm4ocr.bbox import parse_bbox_response
            img_w, img_h = image.size
            bboxes = parse_bbox_response(ocr_text, self.bbox_format, img_w, img_h)
            ocr_text = "\n".join(item.text for item in bboxes)

        return OCRPage(text=ocr_text, image_processing_status={}, bboxes=bboxes,
                       image_width=img_w, image_height=img_h)


    def concurrent_ocr(self, file_paths: Union[str, Iterable[str]],
                       rotate_correction:Union[RotateCorrectionMethod, Literal[False]]=False,
                       max_dimension_pixels:int=None, few_shot_examples:List[FewShotExample]=None,
                       concurrent_batch_size: int=32, max_file_load: int=None) -> AsyncGenerator[OCRResult, None]:
        """
        First complete first out. Input and output order not guaranteed.
        This method inputs a file path or a list of file paths (image, PDF, TIFF) and performs OCR using the VLM inference engine.
        Results are processed concurrently using asyncio.

        Parameters:
        -----------
        file_paths : Union[str, Iterable[str]]
            A file path or a list of file paths to process. Must be one of '.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'
        rotate_correction : {"tesseract", "vlm", False}, Optional
            Rotation correction method. "tesseract" uses pytesseract OSD; "vlm" prompts the VLM engine for orientation. False disables correction.
        max_dimension_pixels : int, Optional
            The maximum dimension of the image in pixels. Origianl dimensions will be resized to fit in. If None, no resizing is applied.
        few_shot_examples : List[FewShotExample], Optional
            list of few-shot examples. Each example is a dict with keys "image" (PIL.Image.Image) and "text" (str).
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

        return self._ocr_async(file_paths=file_paths, 
                               rotate_correction=rotate_correction,
                               max_dimension_pixels=max_dimension_pixels,
                               few_shot_examples=few_shot_examples,
                               concurrent_batch_size=concurrent_batch_size, 
                               max_file_load=max_file_load)
    

    async def _ocr_async(self, file_paths: Iterable[str],
                         rotate_correction:Union[RotateCorrectionMethod, Literal[False]]=False,
                         max_dimension_pixels:int=None,
                         few_shot_examples:List[FewShotExample]=None,
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
            task = asyncio.ensure_future(
                self._ocr_file_with_semaphore(file_load_semaphore=file_load_semaphore,
                                              vlm_call_semaphore=vlm_call_semaphore,
                                              file_path=file_path,
                                              rotate_correction=rotate_correction,
                                              max_dimension_pixels=max_dimension_pixels,
                                              few_shot_examples=few_shot_examples)
            )
            tasks.append(task)

        try:
            for future in asyncio.as_completed(tasks):
                result: OCRResult = await future
                yield result
        finally:
            # Cancel any tasks still running when the consumer stops iterating
            # (e.g. break, exception, aclose(), or Ctrl+C)
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        
    async def _ocr_file_with_semaphore(self, file_load_semaphore:asyncio.Semaphore, vlm_call_semaphore:asyncio.Semaphore,
                                       file_path:str,
                                       rotate_correction:Union[RotateCorrectionMethod, Literal[False]]=False,
                                       max_dimension_pixels:int=None,
                                       few_shot_examples:List[FewShotExample]=None) -> OCRResult:
        """
        This internal method takes a semaphore and OCR a single file using the VLM inference engine.
        """
        async with file_load_semaphore:
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            result = OCRResult(input_dir=file_path, output_mode=self.output_mode)
            messages_logger = MessagesLogger()
            # check file extension
            if file_ext not in SUPPORTED_IMAGE_EXTS:
                result.set_error(
                    DocumentLoadError(f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}",
                                      file_path=file_path),
                    text=f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}")
                return result
            
            try:
                # Load images from file
                data_loader = get_data_loader(file_path, executor=self._page_load_executor,
                                              pdf_backend=self.pdf_backend, pdf_dpi=self.pdf_dpi)

            except Exception as e:
                # Document-level failure: no page is usable, so no page tasks are created
                # and no VLM calls are made for this file.
                error = e if isinstance(e, VLM4OCRError) else DocumentLoadError(
                    f"Failed to load file '{filename}'.", file_path=file_path, cause=e)
                result.set_error(error, text=f"Error processing file {filename}: {str(e)}")
                return result

            try:
                page_processing_tasks = []
                for page_index in range(data_loader.get_page_count()):
                    task = self._ocr_page_with_semaphore(
                        vlm_call_semaphore=vlm_call_semaphore,
                        data_loader=data_loader,
                        page_index=page_index,
                        rotate_correction=rotate_correction,
                        max_dimension_pixels=max_dimension_pixels,
                        few_shot_examples=few_shot_examples,
                        messages_logger=messages_logger
                    )
                    page_processing_tasks.append(task)
                
                if page_processing_tasks:
                    page_tasks = [asyncio.ensure_future(t) for t in page_processing_tasks]
                    try:
                        # return_exceptions keeps one bad page from discarding the pages
                        # that already completed (and were already paid for).
                        processed_page_results = await asyncio.gather(*page_tasks, return_exceptions=True)
                        # A cancelled child is captured rather than raised by gather, so
                        # re-raise to preserve cancellation semantics for the caller.
                        for page_result in processed_page_results:
                            if isinstance(page_result, asyncio.CancelledError):
                                raise page_result
                        for page_index, page_result in enumerate(processed_page_results):
                            if isinstance(page_result, BaseException):
                                page_error = page_result if isinstance(page_result, VLM4OCRError) else VLMError(
                                    f"OCR failed for page {page_index} of '{filename}'.",
                                    file_path=file_path, page_index=page_index, cause=page_result)
                                result.add_page_error(
                                    page_error,
                                    text=f"Error during OCR for a page in {filename}: {str(page_result)}")
                                continue
                            text, image_processing_status, bboxes, img_w, img_h = page_result
                            result.add_page(text=text, image_processing_status=image_processing_status,
                                            bboxes=bboxes, image_width=img_w, image_height=img_h)
                    except asyncio.CancelledError:
                        for pt in page_tasks:
                            if not pt.done():
                                pt.cancel()
                        await asyncio.gather(*page_tasks, return_exceptions=True)
                        raise

            except asyncio.CancelledError:
                raise
            except Exception as e:
                error = e if isinstance(e, VLM4OCRError) else VLMError(
                    f"OCR failed for '{filename}'.", file_path=file_path, cause=e)
                result.set_error(error, text=f"Error during OCR for {filename}: {str(e)}")
                result.add_messages_to_log(messages_logger.get_messages_log())
                return result

        # Set status to success if no errors occurred
        if result.status != "error":
            result.status = "success"
        result.add_messages_to_log(messages_logger.get_messages_log())
        return result

    async def _ocr_page_with_semaphore(self, vlm_call_semaphore: asyncio.Semaphore, data_loader: DataLoader,
                                       page_index:int,
                                       rotate_correction:Union[RotateCorrectionMethod, Literal[False]]=False,
                                       max_dimension_pixels:int=None,
                                       few_shot_examples:List[FewShotExample]=None, messages_logger:MessagesLogger=None) -> Tuple[str, Dict[str, str]]:
        """
        This internal method takes a semaphore and OCR a single image/page using the VLM inference engine.

        Returns:
        -------
        Tuple[str, Dict[str, str]]
            A tuple containing the OCR text and a dictionary with image processing status.
        """
        # Page loading and preprocessing are local CPU work, not VLM calls. They run
        # OUTSIDE vlm_call_semaphore so a page being rasterized or resized does not hold
        # one of the limited VLM concurrency slots.
        image = await data_loader.get_page_async(page_index)
        # Record how this page image was produced. plot_bboxes reads this back to reload
        # the source page at the same resolution the bboxes were computed against.
        image_processing_status = {"page_load": {**data_loader.get_load_info(),
                                                 "size": list(image.size)}}
        # Apply rotate correction if specified
        if rotate_correction:
            try:
                image, rotation_angle = await self.image_processor.rotate_correction_async(image, method=rotate_correction)
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
                original_size = list(image.size)
                image, resized = await self.image_processor.resize_async(image, max_dimension_pixels=max_dimension_pixels)
                image_processing_status["resize"] = {
                    "status": "success",
                    "resized": resized,
                    "original_size": original_size,
                    "final_size": list(image.size)
                }
            except Exception as e:
                image_processing_status["resize"] = {
                    "status": "error",
                    "error": str(e)
                }

        messages = self.vlm_engine.get_ocr_messages(system_prompt=self.system_prompt,
                                                    user_prompt=self.user_prompt,
                                                    image=image,
                                                    few_shot_examples=few_shot_examples)
        # Only the VLM call itself is capped by the concurrency semaphore.
        async with vlm_call_semaphore:
            try:
                response = await self.vlm_engine.chat_async(
                    messages,
                    messages_logger=messages_logger
                )
            except Exception as e:
                raise VLMError(f"VLM call failed for page {page_index} of "
                               f"'{os.path.basename(data_loader.file_path)}'.",
                               file_path=data_loader.file_path, page_index=page_index, cause=e) from e
        ocr_text = response["response"]
        bboxes = None
        img_w = img_h = None

        if self.output_mode == "markdown":
            ocr_text = clean_markdown(ocr_text)
        elif self.output_mode == "JSON":
            json_list = extract_json(ocr_text)
            ocr_text = json.dumps(json_list, indent=4)
        elif self.output_mode == "bbox":
            from vlm4ocr.bbox import parse_bbox_response
            img_w, img_h = image.size
            bboxes = parse_bbox_response(ocr_text, self.bbox_format, img_w, img_h)
            ocr_text = "\n".join(item.text for item in bboxes)

        return ocr_text, image_processing_status, bboxes, img_w, img_h