#!/usr/bin/env python3
"""
Check if a text file only uses words from the Thing Explainer 1000 word list.
"""

import re
import rich
from pathlib import Path
from pydantic import BaseModel, Field
from .word_forms import WordFormsDictionary

_WORDS_RE = re.compile(r"[a-z](?:[a-z']*[a-z])?", re.IGNORECASE)


class InvalidWord(BaseModel):
    word: str = Field(..., description="The invalid word found in the text.")
    index: int = Field(..., description="The index of the invalid word in the text.")
    context: str = Field(..., description="The context in which the invalid word was found.")


class CheckWordsResult(BaseModel):
    invalid_words: list[InvalidWord] = Field(..., description="List of invalid words found in the text.")


def split_words(text: str) -> list[str]:
    """Split text into words, considering only letters and apostrophes."""
    return _WORDS_RE.findall(text.lower())

def find_word_matches(text: str) -> list[tuple[str, int, int]]:
    """Find words in the text and return their positions.

    Returns a list of tuples: (word, start_index, end_index)
    """
    matches = []
    for match in _WORDS_RE.finditer(text.lower()):
        word = match.group()
        start = match.start()
        end = match.end()
        matches.append((word, start, end))

    return matches


def check_words_with_context(text: str, context_length: int = 2) -> CheckWordsResult:
    """Check text against the Thing Explainer word list, returning each occurrence with context.

    Args:
        text: The text to check.
        context_length: Number of surrounding words to include as context.

    Returns:
        CheckWordsResult with each invalid word occurrence, its index, and context snippet.
    """
    word_forms_dict = WordFormsDictionary()
    words = split_words(text)
    invalid_words: list[InvalidWord] = []
    for index, word in enumerate(words):
        if word not in word_forms_dict.allowed_words:
            start = max(0, index - context_length)
            end = min(len(words), index + context_length + 1)
            context = ' '.join(words[start:end])
            invalid_words.append(InvalidWord(word=word, index=index, context=context))
    return CheckWordsResult(invalid_words=invalid_words)


def main(file: Path, full: bool = False) -> int:

    raw_text = file.read_text()
    result = check_words_with_context(raw_text)
    word_count = len(split_words(raw_text))

    rich.print(f"Checked {word_count} words in {file}.")

    if not result.invalid_words:
        rich.print(f"[green]✓ All words in {file} are in the Thing Explainer word list![/green]")
        return 0

    if full:
        rich.print(f"[red]✗ Found {len(result.invalid_words)} invalid occurrence(s) in {file}:[/red]")
        rich.print()
        for item in result.invalid_words:
            rich.print(f"  [bold red]{item.word}[/bold red] (word #{item.index}): ...{item.context}...")
    else:
        counts: dict[str, int] = {}
        for item in result.invalid_words:
            counts[item.word] = counts.get(item.word, 0) + 1
        rich.print(f"[red]✗ Found {len(counts)} invalid word(s) in {file}:[/red]")
        rich.print()
        for word, count in sorted(counts.items(), key=lambda x: -x[1]):
            rich.print(f"  {word} (used {count} time{'s' if count > 1 else ''})")

    return 1
