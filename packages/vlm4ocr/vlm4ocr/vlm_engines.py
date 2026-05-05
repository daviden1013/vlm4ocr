import abc
from typing import List, Dict
from PIL import Image
from vlm4ocr.utils import image_to_base64
from vlm4ocr.data_types import FewShotExample
from llm_inference_engine.llm_configs import (
    LLMConfig as VLMConfig, 
    BasicLLMConfig as BasicVLMConfig, 
    ReasoningLLMConfig as ReasoningVLMConfig, 
    OpenAIReasoningLLMConfig as OpenAIReasoningVLMConfig
)
from llm_inference_engine.utils import MessagesLogger
from llm_inference_engine.engines import (
    InferenceEngine,
    OllamaInferenceEngine,
    OpenAICompatibleInferenceEngine,
    VLLMInferenceEngine,
    SGLangInferenceEngine,
    OpenRouterInferenceEngine,
    OpenAIInferenceEngine,
    AzureOpenAIInferenceEngine,
)


class VLMEngine(InferenceEngine):
    @abc.abstractmethod
    def get_ocr_messages(self, system_prompt:str, user_prompt:str, image:Image.Image, few_shot_examples:List[FewShotExample]=None) -> List[Dict[str,str]]:
        """
        This method inputs an image and returns the correesponding chat messages for the inference engine.

        Parameters:
        ----------
        system_prompt : str
            the system prompt.
        user_prompt : str
            the user prompt.
        image : Image.Image
            the image for OCR.
        few_shot_examples : List[FewShotExample], Optional
            list of few-shot examples. 
        """
        return NotImplemented


class OllamaVLMEngine(OllamaInferenceEngine, VLMEngine):
    def get_ocr_messages(self, system_prompt:str, user_prompt:str, image:Image.Image, few_shot_examples:List[FewShotExample]=None) -> List[Dict[str,str]]:
        """
        This method inputs an image and returns the correesponding chat messages for the inference engine.

        Parameters:
        ----------
        system_prompt : str
            the system prompt.
        user_prompt : str
            the user prompt.
        image : Image.Image
            the image for OCR.
        few_shot_examples : List[FewShotExample], Optional
            list of few-shot examples. 
        """
        base64_str = image_to_base64(image)
        output_messages = []
        # system message (omitted when system_prompt is None)
        if system_prompt is not None:
            output_messages.append({"role": "system", "content": system_prompt})

        # few-shot examples
        if few_shot_examples is not None:
            for example in few_shot_examples:
                if not isinstance(example, FewShotExample):
                    raise ValueError("Few-shot example must be a FewShotExample object.")

                example_image_b64 = image_to_base64(example.image)
                example_user_message = {"role": "user", "content": user_prompt, "images": [example_image_b64]}
                example_agent_message = {"role": "assistant", "content": example.text}
                output_messages.append(example_user_message)
                output_messages.append(example_agent_message)

        # user message (text omitted when user_prompt is None)
        if user_prompt is not None:
            user_message = {"role": "user", "content": user_prompt, "images": [base64_str]}
        else:
            user_message = {"role": "user", "content": "", "images": [base64_str]}
        output_messages.append(user_message)

        return output_messages


class OpenAICompatibleVLMEngine(OpenAICompatibleInferenceEngine, VLMEngine):
    def get_ocr_messages(self, system_prompt:str, user_prompt:str, image:Image.Image, format:str='png', 
                         detail:str="high", few_shot_examples:List[FewShotExample]=None) -> List[Dict[str,str]]:
        """
        This method inputs an image and returns the correesponding chat messages for the inference engine.

        Parameters:
        ----------
        system_prompt : str
            the system prompt.
        user_prompt : str
            the user prompt.
        image : Image.Image
            the image for OCR.
        format : str, Optional
            the image format. 
        detail : str, Optional
            the detail level of the image. Default is "high". 
        few_shot_examples : List[FewShotExample], Optional
            list of few-shot examples.
        """
        base64_str = image_to_base64(image)
        output_messages = []
        # system message (omitted when system_prompt is None)
        if system_prompt is not None:
            output_messages.append({"role": "system", "content": system_prompt})

        # few-shot examples
        if few_shot_examples is not None:
            for example in few_shot_examples:
                if not isinstance(example, FewShotExample):
                    raise ValueError("Few-shot example must be a FewShotExample object.")

                example_image_b64 = image_to_base64(example.image)
                example_user_content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{format};base64,{example_image_b64}",
                            "detail": detail
                        },
                    },
                ]
                if user_prompt is not None:
                    example_user_content.append({"type": "text", "text": user_prompt})
                example_user_message = {"role": "user", "content": example_user_content}
                example_agent_message = {"role": "assistant", "content": example.text}
                output_messages.append(example_user_message)
                output_messages.append(example_agent_message)

        # user message (text omitted when user_prompt is None)
        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{format};base64,{base64_str}",
                    "detail": detail
                },
            },
        ]
        if user_prompt is not None:
            user_content.append({"type": "text", "text": user_prompt})
        output_messages.append({"role": "user", "content": user_content})
        return output_messages


class VLLMVLMEngine(VLLMInferenceEngine, OpenAICompatibleVLMEngine):
    """
    vLLM OpenAI compatible server inference engine.
    https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html

    For parameters and documentation, refer to https://platform.openai.com/docs/api-reference/introduction

    Parameters:
    ----------
    model_name : str
        model name as shown in the vLLM server
    api_key : str, Optional
        the API key for the vLLM server.
    base_url : str, Optional
        the base url for the vLLM server. 
    config : LLMConfig
        the LLM configuration.
    """
    pass

class SGLangVLMEngine(SGLangInferenceEngine, OpenAICompatibleVLMEngine):
    """
    SGLang OpenAI compatible API inference engine.
    https://docs.sglang.ai/basic_usage/openai_api.html

    Parameters:
    ----------
    model_name : str
        model name as shown in the vLLM server
    api_key : str, Optional
        the API key for the vLLM server.
    base_url : str, Optional
        the base url for the vLLM server. 
    config : LLMConfig, Optional
        the LLM configuration.
    max_concurrent_requests : int, Optional
        the maximum number of concurrent requests.
    max_requests_per_minute : int, Optional
        the maximum number of requests per minute.
    """
    pass

class OpenRouterVLMEngine(OpenRouterInferenceEngine, OpenAICompatibleVLMEngine):
    """
    OpenRouter OpenAI-compatible server inference engine.

    Parameters:
    ----------
    model_name : str
        model name as shown in the vLLM server
    api_key : str, Optional
        the API key for the vLLM server. If None, will use the key in os.environ['OPENROUTER_API_KEY'].
    base_url : str, Optional
        the base url for the vLLM server. 
    config : LLMConfig
        the LLM configuration.
    """
    pass

class OpenAIVLMEngine(OpenAIInferenceEngine, VLMEngine):
    def get_ocr_messages(self, system_prompt:str, user_prompt:str, image:Image.Image, format:str='png', 
                         detail:str="high", few_shot_examples:List[FewShotExample]=None) -> List[Dict[str,str]]:
        """
        This method inputs an image and returns the correesponding chat messages for the inference engine.

        Parameters:
        ----------
        system_prompt : str
            the system prompt.
        user_prompt : str
            the user prompt.
        image : Image.Image
            the image for OCR.
        format : str, Optional
            the image format. 
        detail : str, Optional
            the detail level of the image. Default is "high". 
        few_shot_examples : List[FewShotExample], Optional
            list of few-shot examples. Each example is a dict with keys "image" (PIL.Image.Image) and "text" (str).
        """
        base64_str = image_to_base64(image)
        output_messages = []
        # system message (omitted when system_prompt is None)
        if system_prompt is not None:
            output_messages.append({"role": "system", "content": system_prompt})

        # few-shot examples
        if few_shot_examples is not None:
            for example in few_shot_examples:
                if not isinstance(example, FewShotExample):
                    raise ValueError("Few-shot example must be a FewShotExample object.")

                example_image_b64 = image_to_base64(example.image)
                example_user_content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{format};base64,{example_image_b64}",
                            "detail": detail
                        },
                    },
                ]
                if user_prompt is not None:
                    example_user_content.append({"type": "text", "text": user_prompt})
                example_user_message = {"role": "user", "content": example_user_content}
                example_agent_message = {"role": "assistant", "content": example.text}
                output_messages.append(example_user_message)
                output_messages.append(example_agent_message)

        # user message (text omitted when user_prompt is None)
        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{format};base64,{base64_str}",
                    "detail": detail
                },
            },
        ]
        if user_prompt is not None:
            user_content.append({"type": "text", "text": user_prompt})
        output_messages.append({"role": "user", "content": user_content})
        return output_messages


class AzureOpenAIVLMEngine(AzureOpenAIInferenceEngine, OpenAIVLMEngine):
    """
    The Azure OpenAI API inference engine.
    For parameters and documentation, refer to 
    - https://azure.microsoft.com/en-us/products/ai-services/openai-service
    - https://learn.microsoft.com/en-us/azure/ai-services/openai/quickstart
    
    Parameters:
    ----------
    model : str
        model name as described in https://platform.openai.com/docs/models
    api_version : str
        the Azure OpenAI API version
    config : LLMConfig
        the LLM configuration.
    """
    pass
