from .exceptions import (VLM4OCRError, PDFBackendNotAvailableError, DocumentLoadError,
                         VLMError, OutputParseError)
from .data_types import FewShotExample, BBoxItem, BBoxFormat, OCRResult, OCRPage
from .ocr_engines import OCREngine
from .ocr_pipelines import IndependentPagePipeline
from .vlm_engines import BasicVLMConfig, ReasoningVLMConfig, OpenAIReasoningVLMConfig, OllamaVLMEngine, OpenAICompatibleVLMEngine, VLLMVLMEngine, OpenRouterVLMEngine, OpenAIVLMEngine, AzureOpenAIVLMEngine
from .bbox import resolve_bbox_format, register_bbox_format, plot_bbox

__all__ = [
    "VLM4OCRError",
    "PDFBackendNotAvailableError",
    "DocumentLoadError",
    "VLMError",
    "OutputParseError",
    "FewShotExample",
    "BBoxItem",
    "BBoxFormat",
    "OCRResult",
    "OCRPage",
    "BasicVLMConfig",
    "ReasoningVLMConfig",
    "OpenAIReasoningVLMConfig",
    "OCREngine",
    "IndependentPagePipeline",
    "OllamaVLMEngine",
    "OpenAICompatibleVLMEngine",
    "VLLMVLMEngine",
    "OpenRouterVLMEngine",
    "OpenAIVLMEngine",
    "AzureOpenAIVLMEngine",
    "resolve_bbox_format",
    "register_bbox_format",
    "plot_bbox",
]