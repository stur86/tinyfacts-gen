#!/usr/bin/env python3
"""
Check if a text file only uses words from the Thing Explainer 1000 word list.
"""

import sys
import re
import json
from pathlib import Path


def load_word_list(word_forms_path) -> set[str]:
    """Load the allowed words from the word forms JSON dictionary."""
    with open(word_forms_path, 'r') as f:
        data = json.load(f)
    
    # Create a set of all allowed word forms
    allowed_words = set()
    for base_word, forms in data['words'].items():
        # forms is a dictionary with POS tags as keys and word forms as values
        # e.g., {"base": "be", "VBD": "was", "VBG": "being", ...}
        # Add all word forms from the dictionary values
        for form in forms.values():
            allowed_words.add(form.lower())
    
    return allowed_words


def check_text(text_path, allowed_words):
    """Check text file for words not in the allowed list."""
    with open(text_path, 'r') as f:
        text = f.read()
    
    # Extract all words (letters and apostrophes only)
    words = re.findall(r"[a-zA-Z']+", text)
    
    # Convert to lowercase and find invalid words
    invalid_words = {}
    for word in words:
        word_lower = word.lower()
        if word_lower not in allowed_words:
            invalid_words[word_lower] = invalid_words.get(word_lower, 0) + 1
    
    return invalid_words


def main():
    if len(sys.argv) != 2:
        print("Usage: python check_words.py <text_file>")
        print("Example: python check_words.py claude_created/bicycle.txt")
        sys.exit(1)
    
    text_file = sys.argv[1]
    
    # Find the word forms dictionary (assume it's in tinyfacts/thing-explainer/)
    script_dir = Path(__file__).parent
    word_forms_path = script_dir / "tinyfacts" / "thing-explainer" / "word-forms.json"
    
    if not word_forms_path.exists():
        print(f"Error: Word forms dictionary not found at {word_forms_path}")
        sys.exit(1)
    
    if not Path(text_file).exists():
        print(f"Error: Text file not found: {text_file}")
        sys.exit(1)
    
    # Load word list and check text
    allowed_words = load_word_list(word_forms_path)
    invalid_words = check_text(text_file, allowed_words)
    
    if not invalid_words:
        print(f"✓ All words in {text_file} are in the Thing Explainer word list!")
        return 0
    else:
        print(f"✗ Found {len(invalid_words)} invalid word(s) in {text_file}:")
        print()
        for word, count in sorted(invalid_words.items(), key=lambda x: -x[1]):
            print(f"  {word} (used {count} time{'s' if count > 1 else ''})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
