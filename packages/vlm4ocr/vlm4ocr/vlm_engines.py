import abc
import importlib.util
from typing import Any, List, Dict, Union, Generator
import warnings
from PIL import Image
from vlm4ocr.utils import image_to_base64


class VLMConfig(abc.ABC):
    def __init__(self, **kwargs):
        """
        This is an abstract class to provide interfaces for VLM configuration. 
        Children classes that inherts this class can be used in extrators and prompt editor.
        Common VLM parameters: max_new_tokens, temperature, top_p, top_k, min_p.
        """
        self.params = kwargs.copy()

    @abc.abstractmethod
    def preprocess_messages(self, messages:List[Dict[str,str]]) -> List[Dict[str,str]]:
        """
        This method preprocesses the input messages before passing them to the VLM.

        Parameters:
        ----------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        
        Returns:
        -------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        """
        return NotImplemented

    @abc.abstractmethod
    def postprocess_response(self, response:Union[str, Generator[str, None, None]]) -> Union[str, Generator[str, None, None]]:
        """
        This method postprocesses the VLM response after it is generated.

        Parameters:
        ----------
        response : Union[str, Generator[str, None, None]]
            the VLM response. Can be a string or a generator.
        
        Returns:
        -------
        response : str
            the postprocessed VLM response
        """
        return NotImplemented


class BasicVLMConfig(VLMConfig):
    def __init__(self, max_new_tokens:int=2048, temperature:float=0.0, **kwargs):
        """
        The basic VLM configuration for most non-reasoning models.
        """
        super().__init__(**kwargs)
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.params["max_new_tokens"] = self.max_new_tokens
        self.params["temperature"] = self.temperature

    def preprocess_messages(self, messages:List[Dict[str,str]]) -> List[Dict[str,str]]:
        """
        This method preprocesses the input messages before passing them to the VLM.

        Parameters:
        ----------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        
        Returns:
        -------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        """
        return messages

    def postprocess_response(self, response:Union[str, Generator[str, None, None]]) -> Union[str, Generator[str, None, None]]:
        """
        This method postprocesses the VLM response after it is generated.

        Parameters:
        ----------
        response : Union[str, Generator[str, None, None]]
            the VLM response. Can be a string or a generator.
        
        Returns: Union[str, Generator[Dict[str, str], None, None]]
            the postprocessed VLM response. 
            if input is a generator, the output will be a generator {"data": <content>}.
        """
        if isinstance(response, str):
            return response

        def _process_stream():
            for chunk in response:
                yield chunk

        return _process_stream()


class OpenAIReasoningVLMConfig(VLMConfig):
    def __init__(self, reasoning_effort:str="low", **kwargs):
        """
        The OpenAI "o" series configuration.
        1. The reasoning effort is set to "low" by default.
        2. The temperature parameter is not supported and will be ignored.
        3. The system prompt is not supported and will be concatenated to the next user prompt.

        Parameters:
        ----------
        reasoning_effort : str, Optional
            the reasoning effort. Must be one of {"low", "medium", "high"}. Default is "low".
        """
        super().__init__(**kwargs)
        if reasoning_effort not in ["low", "medium", "high"]:
            raise ValueError("reasoning_effort must be one of {'low', 'medium', 'high'}.")

        self.reasoning_effort = reasoning_effort
        self.params["reasoning_effort"] = self.reasoning_effort

        if "temperature" in self.params:
            warnings.warn("Reasoning models do not support temperature parameter. Will be ignored.", UserWarning)
            self.params.pop("temperature")

    def preprocess_messages(self, messages:List[Dict[str,str]]) -> List[Dict[str,str]]:
        """
        Concatenate system prompts to the next user prompt.

        Parameters:
        ----------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        
        Returns:
        -------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        """
        system_prompt_holder = ""
        new_messages = []
        for i, message in enumerate(messages):
            # if system prompt, store it in system_prompt_holder
            if message['role'] == 'system':
                system_prompt_holder = message['content']
            # if user prompt, concatenate it with system_prompt_holder
            elif message['role'] == 'user':
                if system_prompt_holder:
                    new_message = {'role': message['role'], 'content': f"{system_prompt_holder} {message['content']}"}
                    system_prompt_holder = ""
                else:
                    new_message = {'role': message['role'], 'content': message['content']}

                new_messages.append(new_message)
            # if assistant/other prompt, do nothing
            else:
                new_message = {'role': message['role'], 'content': message['content']}
                new_messages.append(new_message)

        return new_messages

    def postprocess_response(self, response:Union[str, Generator[str, None, None]]) -> Union[str, Generator[Dict[str, str], None, None]]:
        """
        This method postprocesses the VLM response after it is generated.

        Parameters:
        ----------
        response : Union[str, Generator[str, None, None]]
            the VLM response. Can be a string or a generator.
        
        Returns: Union[str, Generator[Dict[str, str], None, None]]
            the postprocessed VLM response. 
            if input is a generator, the output will be a generator {"type": "response", "data": <content>}.
        """
        if isinstance(response, str):
            return response

        def _process_stream():
            for chunk in response:
                yield {"type": "response", "data": chunk}

        return _process_stream()


class VLMEngine:
    @abc.abstractmethod
    def __init__(self, config:VLMConfig, **kwrs):
        """
        This is an abstract class to provide interfaces for VLM inference engines. 
        Children classes that inherts this class can be used in extrators. Must implement chat() method.

        Parameters:
        ----------
        config : VLMConfig
            the VLM configuration. Must be a child class of VLMConfig.
        """
        return NotImplemented

    @abc.abstractmethod
    def chat(self, messages:List[Dict[str,str]], verbose:bool=False, stream:bool=False) -> Union[str, Generator[str, None, None]]:
        """
        This method inputs chat messages and outputs VLM generated text.

        Parameters:
        ----------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        verbose : bool, Optional
            if True, VLM generated text will be printed in terminal in real-time.
        stream : bool, Optional
            if True, returns a generator that yields the output in real-time.
        """
        return NotImplemented
    
    @abc.abstractmethod
    def chat_async(self, messages:List[Dict[str,str]]) -> str:
        """
        The async version of chat method. Streaming is not supported.
        """
        return NotImplemented

    @abc.abstractmethod
    def get_ocr_messages(self, system_prompt:str, user_prompt:str, image:Image.Image) -> List[Dict[str,str]]:
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
        """
        return NotImplemented
    
    def _format_config(self) -> Dict[str, Any]:
        """
        This method format the VLM configuration with the correct key for the inference engine. 

        Return : Dict[str, Any]
            the config parameters.
        """
        return NotImplemented


class OllamaVLMEngine(VLMEngine):
    def __init__(self, model_name:str, num_ctx:int=8192, keep_alive:int=300, config:VLMConfig=None, **kwrs):
        """
        The Ollama inference engine.

        Parameters:
        ----------
        model_name : str
            the model name exactly as shown in >> ollama ls
        num_ctx : int, Optional
            context length that LLM will evaluate.
        keep_alive : int, Optional
            seconds to hold the LLM after the last API call.
        config : LLMConfig
            the LLM configuration. 
        """
        if importlib.util.find_spec("ollama") is None:
            raise ImportError("ollama-python not found. Please install ollama-python (```pip install ollama```).")
        
        from ollama import Client, AsyncClient
        self.client = Client(**kwrs)
        self.async_client = AsyncClient(**kwrs)
        self.model_name = model_name
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.config = config if config else BasicVLMConfig()
        self.formatted_params = self._format_config()
    
    def _format_config(self) -> Dict[str, Any]:
        """
        This method format the LLM configuration with the correct key for the inference engine. 
        """
        formatted_params = self.config.params.copy()
        if "max_new_tokens" in formatted_params:
            formatted_params["num_predict"] = formatted_params["max_new_tokens"]
            formatted_params.pop("max_new_tokens")

        return formatted_params

    def chat(self, messages:List[Dict[str,str]], verbose:bool=False, stream:bool=False) -> Union[str, Generator[str, None, None]]:
        """
        This method inputs chat messages and outputs VLM generated text.

        Parameters:
        ----------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        verbose : bool, Optional
            if True, VLM generated text will be printed in terminal in real-time.
        stream : bool, Optional
            if True, returns a generator that yields the output in real-time.
        """
        processed_messages = self.config.preprocess_messages(messages)

        options={'num_ctx': self.num_ctx, **self.formatted_params}
        if stream:
            def _stream_generator():
                response_stream = self.client.chat(
                    model=self.model_name, 
                    messages=processed_messages, 
                    options=options,
                    stream=True, 
                    keep_alive=self.keep_alive
                )
                for chunk in response_stream:
                    content_chunk = chunk.get('message', {}).get('content')
                    if content_chunk:
                        yield content_chunk

            return self.config.postprocess_response(_stream_generator())

        elif verbose:
            response = self.client.chat(
                            model=self.model_name, 
                            messages=processed_messages, 
                            options=options,
                            stream=True,
                            keep_alive=self.keep_alive
                        )
            
            res = ''
            for chunk in response:
                content_chunk = chunk.get('message', {}).get('content')
                print(content_chunk, end='', flush=True)
                res += content_chunk
            print('\n')
            return self.config.postprocess_response(res)
        
        else:
            response = self.client.chat(
                                model=self.model_name, 
                                messages=processed_messages, 
                                options=options,
                                stream=False,
                                keep_alive=self.keep_alive
                            )
            res = response.get('message', {}).get('content')
            return self.config.postprocess_response(res)
        

    async def chat_async(self, messages:List[Dict[str,str]]) -> str:
        """
        Async version of chat method. Streaming is not supported.
        """
        processed_messages = self.config.preprocess_messages(messages)

        response = await self.async_client.chat(
                            model=self.model_name, 
                            messages=processed_messages, 
                            options={'num_ctx': self.num_ctx, **self.formatted_params},
                            stream=False,
                            keep_alive=self.keep_alive
                        )
        
        res = response['message']['content']
        return self.config.postprocess_response(res)
    
    def get_ocr_messages(self, system_prompt:str, user_prompt:str, image:Image.Image) -> List[Dict[str,str]]:
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
        """
        base64_str = image_to_base64(image)
        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_prompt,
                "images": [base64_str]
            }
        ]


class OpenAIVLMEngine(VLMEngine):
    def __init__(self, model:str, config:VLMConfig=None, **kwrs):
        """
        The OpenAI API inference engine. Supports OpenAI models and OpenAI compatible servers:
        - vLLM OpenAI compatible server (https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html)

        For parameters and documentation, refer to https://platform.openai.com/docs/api-reference/introduction

        Parameters:
        ----------
        model_name : str
            model name as described in https://platform.openai.com/docs/models
        config : VLMConfig, Optional
            the VLM configuration. Must be a child class of VLMConfig.
        """
        if importlib.util.find_spec("openai") is None:
            raise ImportError("OpenAI Python API library not found. Please install OpanAI (```pip install openai```).")
        
        from openai import OpenAI, AsyncOpenAI
        self.client = OpenAI(**kwrs)
        self.async_client = AsyncOpenAI(**kwrs)
        self.model = model
        self.config = config if config else BasicVLMConfig()
        self.formatted_params = self._format_config()

    def _format_config(self) -> Dict[str, Any]:
        """
        This method format the LLM configuration with the correct key for the inference engine. 
        """
        formatted_params = self.config.params.copy()
        if "max_new_tokens" in formatted_params:
            formatted_params["max_completion_tokens"] = formatted_params["max_new_tokens"]
            formatted_params.pop("max_new_tokens")

        return formatted_params

    def chat(self, messages:List[Dict[str,str]], verbose:bool=False, stream:bool=False) -> Union[str, Generator[str, None, None]]:
        """
        This method inputs chat messages and outputs LLM generated text.

        Parameters:
        ----------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        verbose : bool, Optional
            if True, VLM generated text will be printed in terminal in real-time.
        stream : bool, Optional
            if True, returns a generator that yields the output in real-time.
        """
        processed_messages = self.config.preprocess_messages(messages)

        if stream:
            def _stream_generator():
                response_stream = self.client.chat.completions.create(
                                        model=self.model,
                                        messages=processed_messages,
                                        stream=True,
                                        **self.formatted_params
                                    )
                for chunk in response_stream:
                    if len(chunk.choices) > 0:
                        if chunk.choices[0].delta.content is not None:
                            yield chunk.choices[0].delta.content
                        if chunk.choices[0].finish_reason == "length":
                            warnings.warn("Model stopped generating due to context length limit.", RuntimeWarning)

            return self.config.postprocess_response(_stream_generator())

        elif verbose:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=processed_messages,
                stream=True,
                **self.formatted_params
            )
            res = ''
            for chunk in response:
                if len(chunk.choices) > 0:
                    if chunk.choices[0].delta.content is not None:
                        res += chunk.choices[0].delta.content
                        print(chunk.choices[0].delta.content, end="", flush=True)
                    if chunk.choices[0].finish_reason == "length":
                        warnings.warn("Model stopped generating due to context length limit.", RuntimeWarning)

            print('\n')
            return self.config.postprocess_response(res)
        else:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=processed_messages,
                stream=False,
                **self.formatted_params
            )
            res = response.choices[0].message.content
            return self.config.postprocess_response(res)
    

    async def chat_async(self, messages:List[Dict[str,str]]) -> str:
        """
        Async version of chat method. Streaming is not supported.
        """
        processed_messages = self.config.preprocess_messages(messages)

        response = await self.async_client.chat.completions.create(
            model=self.model,
            messages=processed_messages,
            stream=False,
            **self.formatted_params
        )
        
        if response.choices[0].finish_reason == "length":
            warnings.warn("Model stopped generating due to context length limit.", RuntimeWarning)

        res = response.choices[0].message.content
        return self.config.postprocess_response(res)
    
    def get_ocr_messages(self, system_prompt:str, user_prompt:str, image:Image.Image, format:str='png', detail:str="high") -> List[Dict[str,str]]:
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
        """
        base64_str = image_to_base64(image)
        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{format};base64,{base64_str}",
                            "detail": detail
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]


class AzureOpenAIVLMEngine(OpenAIVLMEngine):
    def __init__(self, model:str, api_version:str, config:VLMConfig=None, **kwrs):
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
        if importlib.util.find_spec("openai") is None:
            raise ImportError("OpenAI Python API library not found. Please install OpanAI (```pip install openai```).")
        
        from openai import AzureOpenAI, AsyncAzureOpenAI
        self.model = model
        self.api_version = api_version
        self.client = AzureOpenAI(api_version=self.api_version, 
                                  **kwrs)
        self.async_client = AsyncAzureOpenAI(api_version=self.api_version, 
                                             **kwrs)
        self.config = config if config else BasicVLMConfig()
        self.formatted_params = self._format_config()
