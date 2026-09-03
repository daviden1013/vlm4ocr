from typing import Awaitable, Callable, Iterable, Optional, Union, AsyncGenerator, Tuple, List
import os
import asyncio

from PIL import Image

from vlm4ocr.data_types import OCRPage, OCRResult
from vlm4ocr.vlm_engines import MessagesLogger
from vlm4ocr.preprocessing import ImageProcessor, RotateCorrectionMethod
from concurrent.futures import ThreadPoolExecutor
from vlm4ocr.utils import SUPPORTED_IMAGE_EXTS, get_data_loader, default_page_load_workers

# A process_page callable receives ONE page image plus an optional MessagesLogger and
# returns an OCRPage. It never sees sibling pages, so page independence is guaranteed by
# this signature rather than by convention.
ProcessPage = Callable[..., Awaitable[OCRPage]]


class IndependentPagePipeline:
    """
    Concurrency + loading + assembly scaffold for OCR pipelines in which each page is
    processed INDEPENDENTLY of every other page.

    You supply ``process_page(image, *, messages_logger=None) -> OCRPage``. It receives a
    single, already-preprocessed page image (and an optional log sink) and returns a
    standalone OCRPage — typically produced by one or more ``OCREngine.ocr_image_async``
    calls. Because it cannot access neighbouring pages, cross-page logic is unwritable and
    independence holds by construction; flows needing sibling context (doc-level
    classification, continuation pages, cross-page table merges) are out of scope.

    The pipeline owns everything reusable: file loading, optional preprocessing
    (resize + tesseract rotate), page-level concurrency, page ordering, error handling,
    and OCRResult assembly. ``concurrent_ocr`` mirrors ``OCREngine.concurrent_ocr`` (same
    arguments, same first-complete-first-out ``AsyncGenerator[OCRResult]``), so it is a
    drop-in.

    Parameters:
    -----------
    process_page : Callable[..., Awaitable[OCRPage]]
        ``async (image, *, messages_logger=None) -> OCRPage``. The returned page's text,
        bboxes, image_width/height and metadata are kept; the pipeline supplies the
        page's image_processing_status, index, and source path when assembling the result.
    output_mode : str, Optional
        Labels the produced OCRResult. Must be 'markdown', 'HTML', 'text', 'JSON', or
        'bbox', and should match the output mode of the engines used inside process_page.
    rotate_correction : {"tesseract", False}, Optional
        Engine-free rotation correction applied before process_page. "vlm" rotation is not
        supported at this layer (it needs an engine and would escape the concurrency cap);
        do vlm-based rotation inside process_page if required.
    max_dimension_pixels : int, Optional
        If set, resize each page to fit within this dimension before process_page.
    page_load_workers : int | None, Optional
        Size of the thread pool used to load/rasterize pages. Defaults to one worker per
        CPU, capped at 32. Separate from asyncio's default executor so page loading cannot
        starve preprocessing, and independent of concurrent_batch_size.
    """
    def __init__(self, process_page: ProcessPage, *, output_mode: str = "JSON",
                 rotate_correction: Union[RotateCorrectionMethod, bool] = False,
                 max_dimension_pixels: Optional[int] = None,
                 page_load_workers: Optional[int] = None):
        if not callable(process_page):
            raise TypeError("process_page must be a callable returning an awaitable OCRPage")
        if output_mode not in ["markdown", "HTML", "text", "JSON", "bbox"]:
            raise ValueError("output_mode must be 'markdown', 'HTML', 'text', 'JSON', or 'bbox'.")
        self.process_page = process_page
        self.output_mode = output_mode
        self.rotate_correction = rotate_correction
        self.max_dimension_pixels = max_dimension_pixels
        # Engine-free processor: supports resize + tesseract rotate. vlm rotation needs an
        # engine and belongs inside process_page, so it is intentionally not offered here.
        self.image_processor = ImageProcessor()

        # Dedicated pool for page loading; threads are spawned on demand.
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

    def concurrent_ocr(self, file_paths: Union[str, Iterable[str]],
                       concurrent_batch_size: int = 32,
                       max_file_load: Optional[int] = None) -> AsyncGenerator[OCRResult, None]:
        """
        Process files concurrently. First complete first out; output order not guaranteed.

        Parameters:
        -----------
        file_paths : Union[str, Iterable[str]]
            A file path or list of file paths. Must be one of SUPPORTED_IMAGE_EXTS.
        concurrent_batch_size : int, Optional
            Global cap on pages processed concurrently (each page runs one process_page,
            so ~= concurrent VLM calls when process_page issues calls sequentially).
        max_file_load : int, Optional
            Maximum number of files open at once. Defaults to 2 * concurrent_batch_size.

        Returns:
        --------
        AsyncGenerator[OCRResult, None]
            Yields one OCRResult per file as it completes.
        """
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        if max_file_load is None:
            max_file_load = concurrent_batch_size * 2
        if not isinstance(max_file_load, int) or max_file_load <= 0:
            raise ValueError("max_file_load must be a positive integer")

        return self._ocr_async(list(file_paths), concurrent_batch_size, max_file_load)

    async def _ocr_async(self, file_paths: List[str], concurrent_batch_size: int,
                         max_file_load: int) -> AsyncGenerator[OCRResult, None]:
        page_semaphore = asyncio.Semaphore(concurrent_batch_size)      # bounds pages (~VLM calls) globally
        file_load_semaphore = asyncio.Semaphore(max_file_load)         # bounds files open at once

        tasks = [asyncio.ensure_future(
                    self._ocr_file_with_semaphore(file_load_semaphore, page_semaphore, fp))
                 for fp in file_paths]
        try:
            for future in asyncio.as_completed(tasks):
                yield await future
        finally:
            # Cancel tasks still running if the consumer stops iterating early.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _ocr_file_with_semaphore(self, file_load_semaphore: asyncio.Semaphore,
                                       page_semaphore: asyncio.Semaphore, file_path: str) -> OCRResult:
        async with file_load_semaphore:
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            result = OCRResult(input_dir=file_path, output_mode=self.output_mode)

            if file_ext not in SUPPORTED_IMAGE_EXTS:
                result.status = "error"
                result.add_page(text=f"Unsupported file type: {file_ext}. Supported types are: {SUPPORTED_IMAGE_EXTS}",
                                image_processing_status={})
                return result

            try:
                data_loader = get_data_loader(file_path, executor=self._page_load_executor)
                page_count = data_loader.get_page_count()
            except Exception as e:
                result.status = "error"
                result.add_page(text=f"Error processing file {filename}: {str(e)}", image_processing_status={})
                return result

            page_tasks = [asyncio.ensure_future(
                            self._process_page_with_semaphore(page_semaphore, data_loader, i))
                          for i in range(page_count)]
            try:
                processed_pages = await asyncio.gather(*page_tasks)
            except asyncio.CancelledError:
                for pt in page_tasks:
                    if not pt.done():
                        pt.cancel()
                await asyncio.gather(*page_tasks, return_exceptions=True)
                raise
            except Exception as e:
                result.status = "error"
                result.add_page(text=f"Error during OCR for {filename}: {str(e)}", image_processing_status={})
                return result

            # gather preserves submission order, so pages land in page order.
            for page, image_processing_status, messages_log in processed_pages:
                result.add_page(text=page.text, image_processing_status=image_processing_status,
                                bboxes=page.bboxes, image_width=page.image_width,
                                image_height=page.image_height, metadata=page.metadata)
                result.add_messages_to_log(messages_log)

        if result.status != "error":
            result.status = "success"
        return result

    async def _process_page_with_semaphore(self, page_semaphore: asyncio.Semaphore,
                                           data_loader, page_index: int) -> Tuple[OCRPage, dict, list]:
        image = await data_loader.get_page_async(page_index)
        image_processing_status = {}

        # Preprocessing (engine-free, local CPU work) runs OUTSIDE the VLM semaphore.
        if self.rotate_correction:
            try:
                image, rotation_angle = await self.image_processor.rotate_correction_async(
                    image, method=self.rotate_correction)
                image_processing_status["rotate_correction"] = {"status": "success", "rotation_angle": rotation_angle}
            except Exception as e:
                image_processing_status["rotate_correction"] = {"status": "error", "error": str(e)}

        if self.max_dimension_pixels is not None:
            try:
                image, resized = await self.image_processor.resize_async(
                    image, max_dimension_pixels=self.max_dimension_pixels)
                image_processing_status["resize"] = {"status": "success", "resized": resized}
            except Exception as e:
                image_processing_status["resize"] = {"status": "error", "error": str(e)}

        # User logic (>= 1 VLM calls) runs under the global page cap.
        messages_logger = MessagesLogger()
        async with page_semaphore:
            page = await self.process_page(image, messages_logger=messages_logger)

        if not isinstance(page, OCRPage):
            raise TypeError(f"process_page must return an OCRPage, got {type(page).__name__}")

        return page, image_processing_status, messages_logger.get_messages_log()
