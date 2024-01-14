from __future__ import annotations
import asyncio
import json
import time
from abc import ABC, abstractmethod, ABCMeta
from edsl.trackers.TrackerAPI import TrackerAPI
from queue import Queue
from threading import Lock
from typing import Any, Callable, Type
from edsl.data import CRUDOperations, CRUD
from edsl.exceptions import LanguageModelResponseNotJSONError
from edsl.language_models.schemas import model_prices
from edsl.utilities.decorators import sync_wrapper

from edsl.language_models.repair import repair


class RegisterLanguageModelsMeta(ABCMeta):
    "Metaclass to register output elements in a registry i.e., those that have a parent"
    _registry = {}  # Initialize the registry as a dictionary

    def __init__(cls, name, bases, dct):
        super(RegisterLanguageModelsMeta, cls).__init__(name, bases, dct)
        if name != "LanguageModel":
            RegisterLanguageModelsMeta._registry[name] = cls

    @classmethod
    def get_registered_classes(cls):
        return cls._registry

    @classmethod
    def model_names_to_classes(cls):
        d = {}
        for classname, cls in cls._registry.items():
            if hasattr(cls, "_model_"):
                d[cls._model_] = cls
            else:
                raise Exception(
                    f"Class {classname} does not have a __model__ class attribute"
                )
        return d


class LanguageModel(ABC, metaclass=RegisterLanguageModelsMeta):
    """ABC for LLM subclasses."""

    def __init__(self, crud: CRUDOperations = CRUD, **kwargs):
        """
        Attributes:
        - all attributes inherited from subclasses
        - lock: lock for this model to ensure TODO
        - api_queue: queue that records messages about API calls the model makes. Used by `InterviewManager` to update details about state of model.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.lock = Lock()
        self.api_queue = Queue()
        self.crud = crud

    @abstractmethod
    async def async_execute_model_call():
        pass

    def execute_model_call(self, *args, **kwargs):
        async def main():
            results = await asyncio.gather(
                self.async_execute_model_call(*args, **kwargs)
            )
            return results[0]  # Since there's only one task, return its result

        return asyncio.run(main())

    @abstractmethod
    def parse_response(raw_response: dict[str, Any]) -> str:
        """Parses the API response and returns the response text.
        What is returned by the API is model-specific and often includes meta-data that we do not need.
        For example, here is the results from a call to GPT-4:

        {
            "id": "chatcmpl-8eORaeuVb4po9WQRjKEFY6w7v6cTm",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "content": "Hello! How can I assist you today? If you have any questions or need information on a particular topic, feel free to ask.",
                        "role": "assistant",
                        "function_call": None,
                        "tool_calls": None,
                    },
                }
            ],
            "created": 1704637774,
            "model": "gpt-4-1106-preview",
            "object": "chat.completion",
            "system_fingerprint": "fp_168383a679",
            "usage": {"completion_tokens": 27, "prompt_tokens": 13, "total_tokens": 40},
        }

        To actually tract the response, we need to grab
            data["choices[0]"]["message"]["content"].
        """
        raise NotImplementedError

    def _update_response_with_tracking(
        self, response, start_time, cached_response=False
    ):
        end_time = time.time()
        response["elapsed_time"] = end_time - start_time
        response["timestamp"] = end_time
        self._post_tracker_event(response)
        with self.lock:
            response["cached_response"] = cached_response
        return response

    async def async_get_raw_response(
        self, prompt: str, system_prompt: str = ""
    ) -> dict[str, Any]:
        """This is some middle-ware that handles the caching of responses.
        If the cache isn't being used, it just returns a 'fresh' call to the LLM,
        but appends some tracking information to the response (using the _update_response_with_tracking method).
        But if cache is being used, it first checks the database to see if the response is already there.
        If it is, it returns the cached response, but again appends some tracking information.
        If it isn't, it calls the LLM, saves the response to the database, and returns the response with tracking information.

        If self.use_cache is True, then attempts to retrieve the response from the database;
        if not in the DB, calls the LLM and writes the response to the DB."""
        start_time = time.time()

        if not self.use_cache:
            response = await self.async_execute_model_call(prompt, system_prompt)
            return self._update_response_with_tracking(response, start_time, False)

        cached_response = self.crud.get_LLMOutputData(
            model=str(self.model),
            parameters=str(self.parameters),
            system_prompt=system_prompt,
            prompt=prompt,
        )

        if cached_response:
            response = json.loads(cached_response)
            cache_used = True
        else:
            response = await self.async_execute_model_call(prompt, system_prompt)
            self._save_response_to_db(prompt, system_prompt, response)
            cache_used = False

        return self._update_response_with_tracking(response, start_time, cache_used)

    get_raw_response = sync_wrapper(async_get_raw_response)

    def _save_response_to_db(self, prompt, system_prompt, response):
        try:
            output = json.dumps(response)
        except json.JSONDecodeError:
            raise LanguageModelResponseNotJSONError
        self.crud.write_LLMOutputData(
            model=str(self.model),
            parameters=str(self.parameters),
            system_prompt=system_prompt,
            prompt=prompt,
            output=output,
        )

    async def async_get_response(self, prompt: str, system_prompt: str = ""):
        """Get response, parse, and return as string."""
        raw_response = await self.async_get_raw_response(prompt, system_prompt)
        response = self.parse_response(raw_response)
        try:
            dict_response = json.loads(response)
        except json.JSONDecodeError as e:
            print("Could not load JSON. Trying to repair.")
            print(response)
            dict_response, success = repair(response, str(e))
            if not success:
                raise Exception("Even the repair failed.")
        return dict_response

    get_response = sync_wrapper(async_get_response)

    #######################
    # USEFUL METHODS
    #######################
    def _post_tracker_event(self, raw_response: dict[str, Any]) -> None:
        """Parses the API response and sends usage details to the API Queue."""
        usage = raw_response.get("usage", {})
        usage.update(
            {
                "cached_response": raw_response.get("cached_response", None),
                "elapsed_time": raw_response.get("elapsed_time", None),
                "timestamp": raw_response.get("timestamp", None),
            }
        )
        event = TrackerAPI.APICallDetails(details=usage)
        self.api_queue.put(event)

    def cost(self, raw_response: dict[str, Any]) -> float:
        """Returns the dollar cost of a raw response."""
        keys = raw_response["usage"].keys()
        prices = model_prices.get(self.model)
        return sum([prices.get(key, 0.0) * raw_response["usage"][key] for key in keys])

    #######################
    # SERIALIZATION METHODS
    #######################
    def to_dict(self) -> dict[str, Any]:
        """Converts instance to a dictionary."""
        return {"model": self.model, "parameters": self.parameters}

    @classmethod
    def from_dict(cls, data: dict) -> Type[LanguageModel]:
        """Converts dictionary to a LanguageModel child instance."""
        from edsl.language_models.registry import get_model_class

        model_class = get_model_class(data["model"])
        data["use_cache"] = True
        return model_class(**data)

    #######################
    # DUNDER METHODS
    #######################
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model = '{self.model}', parameters={self.parameters})"

    def __add__(self, other_model: Type[LanguageModel]) -> Type[LanguageModel]:
        """Combine two models into a single model (other_model takes precedence over self)"""
        print(
            f"""Warning: one model is replacing another. If you want to run both models, use a single `by` e.g., 
              by(m1, m2, m3) not by(m1).by(m2).by(m3)."""
        )
        return other_model or self
