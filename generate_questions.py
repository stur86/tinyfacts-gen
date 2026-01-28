#!/usr/bin/env python3
"""
Generate explanatory questions for words based on their parts of speech.
Takes a file with one word per line and generates appropriate questions.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple
from tinyfacts.gcide import get_pos_list, POS


def generate_question(word: str, pos: POS) -> str:
    """Generate an appropriate question for a word based on its POS."""
    word = word.lower().strip()

    if pos == POS.NOUN:
        return f"What is a {word}?"
    elif pos == POS.VERB_INTRANSITIVE:
        return f"What does it mean to {word}?"
    elif pos == POS.VERB_TRANSITIVE:
        return f"What does it mean to {word} something/someone?"
    elif pos == POS.ADJECTIVE:
        return f"What does it mean for something to be {word}?"
    elif pos == POS.PRONOUN:
        return f"What does {word} refer to?"
    else:
        return f"What does '{word}' mean or how is it used?"


def process_words(file_path: str) -> List[Tuple[str, List[str]]]:
    """Process words from file and generate questions."""
    results = []

    try:
        text = Path(file_path).read_text(encoding="utf-8")
        lines = text.splitlines()
        for line in lines:
            word = line.strip()

            if not word:
                continue

            pos_tags = get_pos_list(word)

            # Generate question for each POS type
            questions = []
            for pos in sorted(pos_tags):
                questions.append(generate_question(word, pos))

            results.append((word, questions))

    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate explanatory questions for words based on parts of speech"
    )
    parser.add_argument(
        "file_path", help="Path to file containing words (one per line)"
    )
    parser.add_argument(
        "--format",
        choices=["simple", "detailed"],
        default="simple",
        help="Output format (default: simple)",
    )

    args = parser.parse_args()

    results = process_words(args.file_path)

    if args.format == "simple":
        for word, questions in results:
            for question in questions:
                print(question)
    else:  # detailed format
        for word, questions in results:
            print(f"{word}:")
            for question in questions:
                print(f"  - {question}")
            print()


if __name__ == "__main__":
    main()
