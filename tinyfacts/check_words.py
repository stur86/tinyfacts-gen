#!/usr/bin/env python3
"""
Check if a text file only uses words from the Thing Explainer 1000 word list.
"""

import re
import rich
from pathlib import Path
from .word_forms import WordFormsDictionary

_WORDS_RE = re.compile(r"[a-z']+", re.IGNORECASE)

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

def check_words(words: list[str]) -> dict[str, int]:
    """Check the list of words against the Thing Explainer word forms.
    
    Returns a dictionary of invalid words and their counts.
    """
    word_forms_dict = WordFormsDictionary()
    invalid_words = {}
    for word in words:
        if word not in word_forms_dict.allowed_words:
            invalid_words[word] = invalid_words.get(word, 0) + 1
    
    return invalid_words
    

def main(file: Path) -> int:
    
    raw_text = file.read_text()
    words = split_words(raw_text)
    invalid_words = check_words(words)    
    word_count = len(words)
    
    rich.print(f"Checked {word_count} words in {file}.")
    
    if not invalid_words:
        rich.print(f"[green]✓ All words in {file} are in the Thing Explainer word list![/green]")
        return 0
    else:
        rich.print(f"[red]✗ Found {len(invalid_words)} invalid word(s) in {file}:[/red]")
        rich.print()
        for word, count in sorted(invalid_words.items(), key=lambda x: -x[1]):
            rich.print(f"  {word} (used {count} time{'s' if count > 1 else ''})")
        return 1
