#!/usr/bin/env python3
"""
A database of circumlocutions: ways to say words that are *not* in the Thing
Explainer 1000 word list using only words that are.

The database lives in `thing-explainer/circumlocutions.json` and is a plain
mapping of `"word": "alternative expression"`. Every alternative is checked
against the word list, so a suggestion is always safe to drop into a text.
"""

import json
from pathlib import Path

from lemminflect import getAllLemmas
from pydantic import BaseModel, Field

from .check_words import CheckWordsResult, check_words_with_context, split_words
from .word_forms import WordFormsDictionary

_CIRCUMLOCUTIONS_PATH = Path(__file__).parent / "thing-explainer" / "circumlocutions.json"


class Suggestion(BaseModel):
    """A way of saying a word that is not in the word list."""

    word: str = Field(..., description="The word that was looked up.")
    entry: str = Field(
        ..., description="The database key that matched, which may be a base form of the word."
    )
    alternative: str = Field(
        ..., description="An expression, made only of allowed words, to use instead."
    )

    @property
    def is_exact(self) -> bool:
        """True when the looked up word is itself the database key."""
        return self.word == self.entry


class InvalidEntry(BaseModel):
    """A database entry that does not hold up."""

    word: str = Field(..., description="The database key at fault.")
    alternative: str = Field(..., description="The alternative expression stored for it.")
    reason: str = Field(..., description="What is wrong with the entry.")
    invalid_words: list[str] = Field(
        default_factory=list,
        description="Words in the alternative that are not in the word list.",
    )


class CheckWordsWithSuggestionsResult(CheckWordsResult):
    """A word check result carrying a way to say each invalid word that is known."""

    suggestions: list[Suggestion] = Field(
        default_factory=list,
        description="Known ways to say the invalid words using only allowed words.",
    )


class CircumlocutionError(ValueError):
    """Raised when an entry cannot be added to the database."""


def _strip_possessive(word: str) -> str:
    """Turn `girl's` into `girl` so possessives can still be looked up."""
    for ending in ("'s", "s'", "'"):
        if word.endswith(ending) and len(word) > len(ending):
            return word[: -len(ending)]
    return word


class CircumlocutionsDictionary:
    """Look up, search, validate and grow the circumlocutions database."""

    def __init__(self, path: Path | None = None, word_forms: WordFormsDictionary | None = None):
        self._path = path if path is not None else _CIRCUMLOCUTIONS_PATH
        self._word_forms = word_forms if word_forms is not None else WordFormsDictionary()
        if self._path.exists():
            self._entries: dict[str, str] = json.loads(self._path.read_text())
        else:
            self._entries = {}

    @property
    def path(self) -> Path:
        return self._path

    @property
    def entries(self) -> dict[str, str]:
        """The whole database, sorted by word."""
        return dict(sorted(self._entries.items()))

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, word: str) -> bool:
        return word.strip().lower() in self._entries

    @staticmethod
    def _candidate_keys(word: str) -> list[str]:
        """The keys to try for a word: the word, then its base forms."""
        candidates = [word]
        stripped = _strip_possessive(word)
        if stripped != word:
            candidates.append(stripped)
        for base in candidates[:]:
            for lemmas in getAllLemmas(base).values():
                for lemma in lemmas:
                    if lemma not in candidates:
                        candidates.append(lemma)
        return candidates

    def suggest(self, word: str) -> Suggestion | None:
        """Find a way to say `word`, or None if the database has nothing for it.

        Inflected forms and possessives fall back to the base word, so looking up
        `rivers` or `river's` finds the entry stored under `river`.
        """
        key = word.strip().lower()
        if not key:
            return None
        for candidate in self._candidate_keys(key):
            if candidate in self._entries:
                return Suggestion(
                    word=key, entry=candidate, alternative=self._entries[candidate]
                )
        return None

    def suggest_many(self, words: list[str]) -> list[Suggestion]:
        """Look up several words at once, keeping only the ones that were found.

        Each word appears at most once, in the order it was first asked for.
        """
        found: list[Suggestion] = []
        seen: set[str] = set()
        for word in words:
            key = word.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            suggestion = self.suggest(key)
            if suggestion is not None:
                found.append(suggestion)
        return found

    def search(self, text: str) -> list[Suggestion]:
        """Find entries whose word or alternative contains `text`."""
        needle = text.strip().lower()
        return [
            Suggestion(word=word, entry=word, alternative=alternative)
            for word, alternative in self.entries.items()
            if needle in word or needle in alternative.lower()
        ]

    def check_entry(self, word: str, alternative: str) -> InvalidEntry | None:
        """Check a single entry, returning what is wrong with it or None if it holds up."""
        word = word.strip().lower()
        alternative = alternative.strip()
        if not word or " " in word:
            return InvalidEntry(
                word=word, alternative=alternative, reason="the word must be a single word"
            )
        if not alternative:
            return InvalidEntry(
                word=word, alternative=alternative, reason="the alternative is empty"
            )
        if word in self._word_forms.allowed_words:
            return InvalidEntry(
                word=word,
                alternative=alternative,
                reason="the word is already in the word list, so it needs no alternative",
            )
        invalid = [
            found
            for found in split_words(alternative)
            if found not in self._word_forms.allowed_words
        ]
        if invalid:
            return InvalidEntry(
                word=word,
                alternative=alternative,
                reason="the alternative uses words that are not in the word list",
                invalid_words=invalid,
            )
        return None

    def validate(self) -> list[InvalidEntry]:
        """Check every entry in the database."""
        problems = []
        for word, alternative in self.entries.items():
            problem = self.check_entry(word, alternative)
            if problem is not None:
                problems.append(problem)
        return problems

    def add(self, word: str, alternative: str, save: bool = True) -> Suggestion:
        """Add an entry, refusing anything that would not hold up.

        Raises:
            CircumlocutionError: if the entry is not valid.
        """
        word = word.strip().lower()
        alternative = " ".join(alternative.split())
        problem = self.check_entry(word, alternative)
        if problem is not None:
            detail = f" ({', '.join(problem.invalid_words)})" if problem.invalid_words else ""
            raise CircumlocutionError(f"Cannot add '{word}': {problem.reason}{detail}.")
        self._entries[word] = alternative
        if save:
            self.save()
        return Suggestion(word=word, entry=word, alternative=alternative)

    def save(self) -> None:
        """Write the database back out, sorted by word."""
        self._path.write_text(json.dumps(self.entries, indent=4) + "\n")


def check_words_with_suggestions(
    text: str,
    context_length: int = 2,
    circumlocutions: CircumlocutionsDictionary | None = None,
) -> CheckWordsWithSuggestionsResult:
    """Check a text and look up a way to say each word that is not allowed.

    Args:
        text: The text to check.
        context_length: Number of surrounding words to include as context.
        circumlocutions: The database to use, loaded fresh if not given.

    Returns:
        The invalid words with their context, plus any known alternatives.
    """
    result = check_words_with_context(text, context_length)
    if circumlocutions is None:
        circumlocutions = CircumlocutionsDictionary()
    return CheckWordsWithSuggestionsResult(
        invalid_words=result.invalid_words,
        suggestions=circumlocutions.suggest_many(
            [invalid.word for invalid in result.invalid_words]
        ),
    )


if __name__ == "__main__":
    circumlocutions = CircumlocutionsDictionary()
    problems = circumlocutions.validate()
    print(f"Checked {len(circumlocutions)} entries in {circumlocutions.path}.")
    for problem in problems:
        detail = f" ({', '.join(problem.invalid_words)})" if problem.invalid_words else ""
        print(f"  {problem.word}: {problem.reason}{detail}")
    raise SystemExit(1 if problems else 0)
