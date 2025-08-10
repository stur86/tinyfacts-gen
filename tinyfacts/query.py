from typing import Any
from copy import deepcopy
from tinyfacts.prompt import make_prompt

class Query:
    
    _query_args: dict[str, Any]
    
    def __init__(self, model: str, cache_key: str = "tinyfacts_cache"):
        self._query_args = {
            "model": model,
            "prompt_cache_key": cache_key,
            "messages": [
                {
                    "role": "developer",
                    "content": make_prompt()
                }
            ]
        }
        
        if "gpt-5" in model:
            # We're focusing on no reasoning here, so we turn it off
            self._query_args["reasoning_effort"] = "minimal"
        
    def __call__(self, message: str) -> dict[str, Any]:
        """
        Get the full query arguments
        """
        _args = deepcopy(self._query_args)
        _args["messages"].append({
            "role": "user",
            "content": message
        })
        return _args
    
    def ask_explain(self, thing: str) -> dict[str, Any]:
        """
        Ask the model to explain a thing
        """
        return self(f"Please explain what the word '{thing}' means.")
    
    def ask_explain_and_fact(self, thing: str) -> dict[str, Any]:
        """
        Ask the model to explain a thing and provide a fact about it
        """
        return self(f"Please explain what the word '{thing}' means and in a new paragraph provide a fact about it.")