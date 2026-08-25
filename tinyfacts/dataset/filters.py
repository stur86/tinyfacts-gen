"""Picking out rows of the dataset."""

import re
from dataclasses import dataclass
from typing import Iterable

from .records import DatasetRecord


class FilterError(Exception):
    """One of the given patterns is not a working regular expression."""


def _compile(pattern: str | None, name: str) -> re.Pattern[str] | None:
    if pattern is None:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise FilterError(f"Bad regular expression for --{name}: {exc}") from exc


def _split(values: Iterable[str] | None) -> set[str] | None:
    """Turn a list of options into a set, letting one option hold many names.

    So `--model a --model b` and `--model a,b` mean the same thing.
    """
    if not values:
        return None
    out = {part.strip() for value in values for part in value.split(",") if part.strip()}
    return out or None


@dataclass
class RecordFilter:
    """Which rows to work on. Every test that is set has to pass."""

    id_pattern: re.Pattern[str] | None = None
    title_pattern: re.Pattern[str] | None = None
    text_pattern: re.Pattern[str] | None = None
    instruction_pattern: re.Pattern[str] | None = None
    sources: set[str] | None = None
    models: set[str] | None = None
    tags: set[str] | None = None
    has_instruction: bool | None = None
    min_words: int | None = None
    max_words: int | None = None

    @classmethod
    def build(
        cls,
        id: str | None = None,
        title: str | None = None,
        text: str | None = None,
        instruction: str | None = None,
        source: Iterable[str] | None = None,
        model: Iterable[str] | None = None,
        tag: Iterable[str] | None = None,
        has_instruction: bool | None = None,
        min_words: int | None = None,
        max_words: int | None = None,
    ) -> "RecordFilter":
        """Make a filter out of what was typed on the command line."""
        instruction_pattern = _compile(instruction, "instruction")
        if instruction_pattern is not None and has_instruction is None:
            has_instruction = True
        return cls(
            id_pattern=_compile(id, "id"),
            title_pattern=_compile(title, "title"),
            text_pattern=_compile(text, "text"),
            instruction_pattern=instruction_pattern,
            sources=_split(source),
            models=_split(model),
            tags=_split(tag),
            has_instruction=has_instruction,
            min_words=min_words,
            max_words=max_words,
        )

    @property
    def is_empty(self) -> bool:
        """True when the filter lets everything through."""
        return all(
            value in (None, set()) for value in self.__dict__.values()
        )

    def matches(self, record: DatasetRecord) -> bool:
        if self.id_pattern and not self.id_pattern.search(record.id):
            return False
        if self.title_pattern and not self.title_pattern.search(record.title):
            return False
        if self.text_pattern and not self.text_pattern.search(record.text):
            return False
        if self.sources is not None and record.source not in self.sources:
            return False
        if self.models is not None and (record.model or "") not in self.models:
            return False
        if self.tags is not None and not self.tags.intersection(record.tags):
            return False
        has = bool(record.instruction and record.instruction.strip())
        if self.has_instruction is not None and has != self.has_instruction:
            return False
        if self.instruction_pattern and not self.instruction_pattern.search(
            record.instruction or ""
        ):
            return False
        if self.min_words is not None and record.word_count < self.min_words:
            return False
        if self.max_words is not None and record.word_count > self.max_words:
            return False
        return True

    def apply(self, records: Iterable[DatasetRecord]) -> list[DatasetRecord]:
        return [record for record in records if self.matches(record)]
