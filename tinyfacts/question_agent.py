"""An agent that works out the user question a given text answers."""

from dataclasses import dataclass
from textwrap import dedent
from string import Template
from typing import Any, Callable

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRunResultEvent
from pydantic_ai.usage import RunUsage

from .agent import SupportedProviders, resolve_provider
from .custom_providers import CustomProviderError


class OutputQuestion(BaseModel):
    question: str = Field(
        ..., description="The user question that the given text answers."
    )


_QUESTION_PROMPT = Template("""
    Below is an answer written by a helper that explains things with very simple words.
    Work out the question a user would have asked to get this answer.

    Rules for the question:
    - Write it as a real user would write it, in normal English. It does not have to
      keep to the simple word list that the answer uses.
    - Ask about the subject of the answer, not about the way the answer is written.
    - Keep it to one short question, no more than about twenty words.
    - Do not repeat whole sentences from the answer, and do not give away its details.
    - Do not add anything else: no greeting, no notes, no answer.
    $title
    Here is the answer:

    $text
    """)

_TITLE_PROMPT = Template("""
    The answer was saved under this title, which may help you see what it is about: "$title".
""")


@dataclass
class QuestionResult:
    question: str
    usage: RunUsage


class QuestionAgent(Agent[None, OutputQuestion]):
    """Suggests the user question that a piece of text is a response to."""

    def __init__(
        self,
        model_name: str | None = None,
        provider_name: str = SupportedProviders.OPENAI,
    ):
        resolved = resolve_provider(provider_name)
        if model_name is None:
            model_name = resolved.default_model
        if model_name is None:
            raise CustomProviderError(
                f"Provider '{provider_name}' does not set 'default_model', "
                f"so a model must be given with --model."
            )
        self._model_name = model_name
        model = resolved.model_type(model_name=model_name, provider=resolved.provider)
        super().__init__(model=model, output_type=OutputQuestion)  # type: ignore

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_question(
        self,
        text: str,
        title: str | None = None,
        event_callback: Callable[[Any], None] = lambda x: None,
    ) -> QuestionResult:
        title_prompt = (
            _TITLE_PROMPT.substitute(title=title.strip()) if title else ""
        )
        prompt = dedent(
            _QUESTION_PROMPT.substitute(text=text.strip(), title=title_prompt)
        )
        output: OutputQuestion | None = None
        usage = RunUsage()
        async for event in self.run_stream_events(prompt):
            if isinstance(event, AgentRunResultEvent):
                output = event.result.output
                usage = event.result.usage()
            else:
                event_callback(event)
        if output is None:
            raise RuntimeError("No result returned from agent.")
        return QuestionResult(question=output.question.strip(), usage=usage)
