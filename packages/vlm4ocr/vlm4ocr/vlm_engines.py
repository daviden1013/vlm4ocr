import abc
import importlib.util
from typing import List, Dict, Union, Generator
import warnings
from PIL import Image
from vlm4ocr.utils import image_to_base64


class VLMEngine:
    @abc.abstractmethod
    def __init__(self):
        """
        This is an abstract class to provide interfaces for VLM inference engines. 
        Children classes that inherts this class can be used in extrators. Must implement chat() method.
        """
        return NotImplemented

    @abc.abstractmethod
    def chat(self, messages:List[Dict[str,str]], max_new_tokens:int=4096, temperature:float=0.0, 
             verbose:bool=False, stream:bool=False, **kwrs) -> Union[str, Generator[str, None, None]]:
        """
        This method inputs chat messages and outputs VLM generated text.

        Parameters:
        ----------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        max_new_tokens : str, Optional
            the max number of new tokens VLM can generate. 
        temperature : float, Optional
            the temperature for token sampling. 
        verbose : bool, Optional
            if True, VLM generated text will be printed in terminal in real-time.
        stream : bool, Optional
            if True, returns a generator that yields the output in real-time.
        """
        return NotImplemented
    
    @abc.abstractmethod
    def chat_async(self, messages:List[Dict[str,str]], max_new_tokens:int=4096, temperature:float=0.0, **kwrs) -> str:
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


class OllamaVLMEngine(VLMEngine):
    def __init__(self, model_name:str, num_ctx:int=4096, keep_alive:int=300, **kwrs):
        """
        The Ollama inference engine.

        Parameters:
        ----------
        model_name : str
            the model name exactly as shown in >> ollama ls
        num_ctx : int, Optional
            context length that VLM will evaluate.
        keep_alive : int, Optional
            seconds to hold the VLM after the last API call.
        """
        if importlib.util.find_spec("ollama") is None:
            raise ImportError("ollama-python not found. Please install ollama-python (```pip install ollama```).")
        
        from ollama import Client, AsyncClient
        self.client = Client(**kwrs)
        self.async_client = AsyncClient(**kwrs)
        self.model_name = model_name
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive

    def chat(self, messages:List[Dict[str,str]], max_new_tokens:int=4096, temperature:float=0.0, 
             verbose:bool=False, stream:bool=False, **kwrs) -> Union[str, Generator[str, None, None]]:
        """
        This method inputs chat messages and outputs VLM generated text.

        Parameters:
        ----------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        max_new_tokens : str, Optional
            the max number of new tokens VLM can generate. 
        temperature : float, Optional
            the temperature for token sampling. 
        verbose : bool, Optional
            if True, VLM generated text will be printed in terminal in real-time.
        stream : bool, Optional
            if True, returns a generator that yields the output in real-time.
        """
        options={'temperature':temperature, 'num_ctx': self.num_ctx, 'num_predict': max_new_tokens, **kwrs}
        if stream:
            def _stream_generator():
                response_stream = self.client.chat(
                    model=self.model_name, 
                    messages=messages, 
                    options=options,
                    stream=True, 
                    keep_alive=self.keep_alive
                )
                for chunk in response_stream:
                    content_chunk = chunk.get('message', {}).get('content')
                    if content_chunk:
                        yield content_chunk

            return _stream_generator()

        elif verbose:
            response = self.client.chat(
                            model=self.model_name, 
                            messages=messages, 
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
            return res
        
        return response.get('message', {}).get('content', '')
    

    async def chat_async(self, messages:List[Dict[str,str]], max_new_tokens:int=4096, temperature:float=0.0, **kwrs) -> str:
        """
        Async version of chat method. Streaming is not supported.
        """
        response = await self.async_client.chat(
                            model=self.model_name, 
                            messages=messages, 
                            options={'temperature':temperature, 'num_ctx': self.num_ctx, 'num_predict': max_new_tokens, **kwrs},
                            stream=False,
                            keep_alive=self.keep_alive
                        )
        
        return response.get('message', {}).get('content', '')
    
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
    def __init__(self, model:str, reasoning_model:bool=False, **kwrs):
        """
        The OpenAI API inference engine. Supports OpenAI models and OpenAI compatible servers:
        - vLLM OpenAI compatible server (https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html)

        For parameters and documentation, refer to https://platform.openai.com/docs/api-reference/introduction

        Parameters:
        ----------
        model_name : str
            model name as described in https://platform.openai.com/docs/models
        reasoning_model : bool, Optional
            indicator for OpenAI reasoning models ("o" series).
        """
        if importlib.util.find_spec("openai") is None:
            raise ImportError("OpenAI Python API library not found. Please install OpanAI (```pip install openai```).")
        
        from openai import OpenAI, AsyncOpenAI
        self.client = OpenAI(**kwrs)
        self.async_client = AsyncOpenAI(**kwrs)
        self.model = model
        self.reasoning_model = reasoning_model

    def chat(self, messages:List[Dict[str,str]], max_new_tokens:int=4096, temperature:float=0.0, 
             verbose:bool=False, stream:bool=False, **kwrs) -> Union[str, Generator[str, None, None]]:
        """
        This method inputs chat messages and outputs VLM generated text.

        Parameters:
        ----------
        messages : List[Dict[str,str]]
            a list of dict with role and content. role must be one of {"system", "user", "assistant"}
        max_new_tokens : str, Optional
            the max number of new tokens VLM can generate. 
        temperature : float, Optional
            the temperature for token sampling. 
        verbose : bool, Optional
            if True, VLM generated text will be printed in terminal in real-time. 
        stream : bool, Optional
            if True, returns a generator that yields the output in real-time.
        """
        # For reasoning models
        if self.reasoning_model:
            # Reasoning models do not support temperature parameter
            if temperature != 0.0:
                warnings.warn("Reasoning models do not support temperature parameter. Will be ignored.", UserWarning)

            # Reasoning models do not support system prompts
            if any(msg['role'] == 'system' for msg in messages):
                warnings.warn("Reasoning models do not support system prompts. Will be ignored.", UserWarning)
                messages = [msg for msg in messages if msg['role'] != 'system']
            

            if stream:
                def _stream_generator():
                    response_stream = self.client.chat.completions.create(
                                            model=self.model,
                                            messages=messages,
                                            max_completion_tokens=max_new_tokens,
                                            stream=True,
                                            **kwrs
                                        )
                    for chunk in response_stream:
                        if len(chunk.choices) > 0:
                            if chunk.choices[0].delta.content is not None:
                                yield chunk.choices[0].delta.content
                            if chunk.choices[0].finish_reason == "length":
                                warnings.warn("Model stopped generating due to context length limit.", RuntimeWarning)
                                if self.reasoning_model:
                                    warnings.warn("max_new_tokens includes reasoning tokens and output tokens.", UserWarning)
                return _stream_generator()

            elif verbose:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=max_new_tokens,
                    stream=True,
                    **kwrs
                )
                res = ''
                for chunk in response:
                    if len(chunk.choices) > 0:
                        if chunk.choices[0].delta.content is not None:
                            res += chunk.choices[0].delta.content
                            print(chunk.choices[0].delta.content, end="", flush=True)
                        if chunk.choices[0].finish_reason == "length":
                            warnings.warn("Model stopped generating due to context length limit.", RuntimeWarning)
                            if self.reasoning_model:
                                warnings.warn("max_new_tokens includes reasoning tokens and output tokens.", UserWarning)

                print('\n')
                return res
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=max_new_tokens,
                    stream=False,
                    **kwrs
                )
                return response.choices[0].message.content

        # For non-reasoning models
        else:
            if stream:
                def _stream_generator():
                    response_stream = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=max_new_tokens,
                        temperature=temperature,
                        stream=True,
                        **kwrs
                    )
                    for chunk in response_stream:
                        if len(chunk.choices) > 0:
                            if chunk.choices[0].delta.content is not None:
                                yield chunk.choices[0].delta.content
                            if chunk.choices[0].finish_reason == "length":
                                warnings.warn("Model stopped generating due to context length limit.", RuntimeWarning)
                                if self.reasoning_model:
                                    warnings.warn("max_new_tokens includes reasoning tokens and output tokens.", UserWarning)
                return _stream_generator()
            
            elif verbose:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_new_tokens,
                    temperature=temperature,
                    stream=True,
                    **kwrs
                )
                res = ''
                for chunk in response:
                    if len(chunk.choices) > 0:
                        if chunk.choices[0].delta.content is not None:
                            res += chunk.choices[0].delta.content
                            print(chunk.choices[0].delta.content, end="", flush=True)
                        if chunk.choices[0].finish_reason == "length":
                            warnings.warn("Model stopped generating due to context length limit.", RuntimeWarning)
                            if self.reasoning_model:
                                warnings.warn("max_new_tokens includes reasoning tokens and output tokens.", UserWarning)

                print('\n')
                return res

            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_new_tokens,
                    temperature=temperature,
                    stream=False,
                    **kwrs
                )

            return response.choices[0].message.content
    

    async def chat_async(self, messages:List[Dict[str,str]], max_new_tokens:int=4096, temperature:float=0.0, **kwrs) -> str:
        """
        Async version of chat method. Streaming is not supported.
        """
        if self.reasoning_model:
            # Reasoning models do not support temperature parameter
            if temperature != 0.0:
                warnings.warn("Reasoning models do not support temperature parameter. Will be ignored.", UserWarning)

            # Reasoning models do not support system prompts
            if any(msg['role'] == 'system' for msg in messages):
                warnings.warn("Reasoning models do not support system prompts. Will be ignored.", UserWarning)
                messages = [msg for msg in messages if msg['role'] != 'system']

            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=max_new_tokens,
                stream=False,
                **kwrs
            )

        else:
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_new_tokens,
                temperature=temperature,
                stream=False,
                **kwrs
            )
        
        if response.choices[0].finish_reason == "length":
            warnings.warn("Model stopped generating due to context length limit.", RuntimeWarning)
            if self.reasoning_model:
                warnings.warn("max_new_tokens includes reasoning tokens and output tokens.", UserWarning)

        return response.choices[0].message.content
    
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
    def __init__(self, model:str, api_version:str, reasoning_model:bool=False, **kwrs):
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
        reasoning_model : bool, Optional
            indicator for OpenAI reasoning models ("o" series).
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
        self.reasoning_model = reasoning_model
