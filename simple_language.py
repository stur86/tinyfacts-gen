import json
from pathlib import Path

_WORDS_PATH = Path(__file__).parent / "tinyfacts" / "thing-explainer" / "word-forms.json"

def read_allowed_words() -> set[str]:
    """Read the allowed words from the JSON file and return them as a set."""

    word_forms: dict[str, dict[str, str]] = json.loads(_WORDS_PATH.read_text())["words"]
    allowed_words = set()
    for forms in word_forms.values():
        for form in forms.values():
            allowed_words.add(form.lower())
    return allowed_words

_ALLOWED_WORDS = read_allowed_words()