from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from textwrap import dedent
from pydantic import BaseModel, Field
from .word_forms import WordFormsDictionary
from .check_words import check_words_with_context, InvalidWord, CheckWordsResult
from .custom_providers import CustomProviders, CustomProviderError
from string import Template
from typing import Callable, Any
from pydantic_ai.usage import RunUsage
from pydantic_ai import Agent, AgentRunResultEvent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.google import GoogleProvider

class SupportedProviders(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    GOOGLE = "google"


_BUILTIN_DEFAULT_MODELS: dict[SupportedProviders, str] = {
    SupportedProviders.OPENAI: "gpt-5.1",
    SupportedProviders.OLLAMA: "qwen3:8b",
    SupportedProviders.GOOGLE: "gemini-2.5-pro",
}


@dataclass
class ResolvedProvider:
    """A provider instance plus what is needed to build a model from it."""

    provider: Any
    model_type: type[OpenAIChatModel] | type[GoogleModel]
    default_model: str | None


def get_provider(provider_name: str) -> Any:
    """Return the provider instance for a built-in or custom provider name."""
    return resolve_provider(provider_name).provider


def resolve_provider(provider_name: str) -> ResolvedProvider:
    """Resolve a provider name to a provider instance.

    Names outside `SupportedProviders` are looked up in the custom providers file
    and treated as OpenAI-compatible servers.
    """
    try:
        builtin = SupportedProviders(provider_name)
    except ValueError:
        return _resolve_custom_provider(provider_name)

    default_model = _BUILTIN_DEFAULT_MODELS[builtin]
    if builtin == SupportedProviders.OPENAI:
        return ResolvedProvider(OpenAIProvider(), OpenAIChatModel, default_model)
    elif builtin == SupportedProviders.OLLAMA:
        return ResolvedProvider(
            OllamaProvider(base_url="http://localhost:11434/v1"), OpenAIChatModel, default_model
        )
    elif builtin == SupportedProviders.GOOGLE:
        return ResolvedProvider(GoogleProvider(), GoogleModel, default_model)
    else:
        raise ValueError(f"Unsupported provider: {provider_name}")


def _resolve_custom_provider(provider_name: str) -> ResolvedProvider:
    config = CustomProviders.load().get(provider_name)
    provider = OpenAIProvider(
        base_url=config.base_url,
        api_key=config.resolve_api_key(provider_name),
    )
    return ResolvedProvider(provider, OpenAIChatModel, config.default_model)

class OutputText(BaseModel):
    short_title: str = Field(..., description="A short title for the generated text.")
    text: str = Field(..., description="The generated text using Thing Explainer words.")
    
_BASE_EXAMPLE_PROMPT = Template("""
    Here is an example of a text similar to what I would like you to produce:
    
    Example Topic: "$example_topic"
    Example Text: $example_text 

""")
   
_BASE_PROMPT = Template("""
    You are to write an explanation of the following topic using only words from the Thing Explainer 1000 word list, as well
    as allowed inflected forms of those words. Here is a complete list of the allowed words and their forms:
    
    $word_list
    
    Be simple, but not minimalist - add interesting facts and details where you can. If a word you need is not available in the 
    list, use a different way to say it using only the allowed words.
    
    $example
    The topic to write about is: "$topic".
    
    Please use the provided tool to check your text for any words that are not in the allowed list, and revise your text until it passes the check.
    Only answer with the final text that passes the check.
    """)
 

_DEFAULT_EXAMPLE_PATH = Path(__file__).parents[1] / "manually_created" / "anne_of_green_gables.txt"
_DEFAULT_EXAMPLE_DESCRIPTION = "The plot of the novel 'Anne of Green Gables' by L.M. Montgomery."
    
class ThingExplainerAgent(Agent[None, OutputText]):
    
    _DEFAULT_MODELS = _BUILTIN_DEFAULT_MODELS

    def __init__(self, model_name: str | None = None, provider_name: str = SupportedProviders.OPENAI,
                 use_example: bool = True, example_topic: str = _DEFAULT_EXAMPLE_DESCRIPTION, example_path: Path = _DEFAULT_EXAMPLE_PATH):
        resolved = resolve_provider(provider_name)
        if model_name is None:
            model_name = resolved.default_model
        if model_name is None:
            raise CustomProviderError(
                f"Provider '{provider_name}' does not set 'default_model', "
                f"so a model must be given with --model."
            )

        self._dict = WordFormsDictionary()
        self._model_name = model_name
        self._use_example = use_example

        model = resolved.model_type(model_name=model_name, provider=resolved.provider)

        super().__init__(model=model, output_type=OutputText) # type: ignore
        
        # Define the word checker tool
        def check_simple_words(text: str, context_length: int = 2) -> CheckWordsResult:
            """Check if the text only uses words from the Thing Explainer 1000 word list.

            Args:
                text (str): The text to check.
                context_length (int): Number of words to include in the context around invalid words.

            Returns:
                CheckWordsResult: The result containing invalid words information.
            """
            return check_words_with_context(text, context_length)
        
        self.tool_plain(check_simple_words)
        
        self._example_topic_description = example_topic
        self._example_text = example_path.read_text()
    
    @property
    def model_name(self) -> str:
        return self._model_name
        
    async def generate_explanation(self, topic: str, event_callback: Callable[[Any], None] = lambda x: None) -> tuple[OutputText, RunUsage]:
        word_list_str = ', '.join(sorted(self._dict.allowed_words))
        if self._use_example:
            example_prompt = _BASE_EXAMPLE_PROMPT.substitute(
                example_topic=self._example_topic_description,
                example_text=self._example_text
            )
        else:
            example_prompt = ""
        prompt = dedent(_BASE_PROMPT.substitute(
            word_list=word_list_str,
            example=example_prompt,
            topic=topic
        ))
        output = None
        usage = RunUsage()
        async for event in self.run_stream_events(prompt):
            if isinstance(event, AgentRunResultEvent):
                output = event.result.output
                usage = event.result.usage()
            else:
                event_callback(event)
        if output is None:
            raise RuntimeError("No result returned from agent.")
        return output, usage

async def main_async():        
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file if it exists
    
    agent = ThingExplainerAgent(provider_name=SupportedProviders.OLLAMA, use_example=True)
    agent_response, agent_usage = await agent.generate_explanation("How a car engine works", event_callback=lambda e: print(e))
    print("\nGenerated Explanation:\n")
    print(agent_response.text)
    print(f"\nUsage:\n\tTokens: {agent_usage.total_tokens}\n\tTool calls: {agent_usage.tool_calls}\n")
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(main_async())