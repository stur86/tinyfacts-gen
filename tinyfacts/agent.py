from pathlib import Path
from enum import Enum
from textwrap import dedent
from pydantic import BaseModel, Field
from .word_forms import WordFormsDictionary
from .check_words import split_words
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
    
def get_provider(provider_name: SupportedProviders) -> Any:
    if provider_name == SupportedProviders.OPENAI:
        return OpenAIProvider()
    elif provider_name == SupportedProviders.OLLAMA:
        return OllamaProvider(base_url="http://localhost:11434/v1")
    elif provider_name == SupportedProviders.GOOGLE:
        return GoogleProvider()
    else:
        raise ValueError(f"Unsupported provider: {provider_name}")

class InvalidWord(BaseModel):
    word: str = Field(..., description="The invalid word found in the text.")
    index: int = Field(..., description="The index of the invalid word in the text.")
    context: str = Field(..., description="The context in which the invalid word was found.")

class CheckWordsResult(BaseModel):
    invalid_words: list[InvalidWord] = Field(..., description="List of invalid words found in the text.")    
    
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
    
    _DEFAULT_MODELS: dict[SupportedProviders, str] = {
        SupportedProviders.OPENAI: "gpt-5.1",
        SupportedProviders.OLLAMA: "qwen3:8b",
        SupportedProviders.GOOGLE: "gemini-2.5-pro",
    }

    
    def __init__(self, model_name: str | None = None, provider_name: SupportedProviders = SupportedProviders.OPENAI,
                 use_example: bool = True, example_topic: str = _DEFAULT_EXAMPLE_DESCRIPTION, example_path: Path = _DEFAULT_EXAMPLE_PATH):
        provider = get_provider(provider_name)
        if model_name is None:
            model_name = self._DEFAULT_MODELS[provider_name]
                
        self._dict = WordFormsDictionary()
        self._model_name = model_name
        self._use_example = use_example
        
        if provider_name in {SupportedProviders.OPENAI, SupportedProviders.OLLAMA}:
            model = OpenAIChatModel(model_name=model_name, provider=provider)
        elif provider_name == SupportedProviders.GOOGLE:
            model = GoogleModel(model_name=model_name, provider=provider)
        else:
            raise ValueError(f"Unsupported provider: {provider_name}")

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
            # Split text into words; remove all non-letter characters except apostrophes
            words = split_words(text)
            invalid_words: list[InvalidWord] = []
            for index, word in enumerate(words):
                if word not in self._dict.allowed_words:
                    # Get context
                    start = max(0, index - context_length)
                    end = min(len(words), index + context_length + 1)
                    context = ' '.join(words[start:end])
                    invalid_words.append(InvalidWord(word=word, index=index, context=context))
            return CheckWordsResult(invalid_words=invalid_words)
        
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
        usage: RunUsage
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