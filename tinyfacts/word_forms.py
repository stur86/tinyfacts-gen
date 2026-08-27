#!/usr/bin/env python3
"""
Generate word-forms.json using NLTK to find all valid inflections of the base 1000 words.
"""
import json
from functools import lru_cache
from pathlib import Path
from lemminflect import getAllInflections
from dataclasses import dataclass

_WORD_LIST_PATH = Path(__file__).parent / "thing-explainer" / "thing-explainer-1000.txt"
_ACTION_NOUNS_PATH = _WORD_LIST_PATH.parent / "action-nouns.json"

_SUPPORTED_INFLECTIONS = {
    'NNS',        # Noun, plural
    'VBZ',  # Verb, 3rd person singular present
    'VBD',    # Verb, past tense
    'VBG',  # Verb, gerund or present participle
    'VBN',  # Verb, past participle
    'JJR',    # Adjective, comparative
    'JJS',    # Adjective, superlative
    'RBR',    # Adverb, comparative
    'RBS'     # Adverb, superlative
}

_SUPPORTED_TAGS = _SUPPORTED_INFLECTIONS.union({'ANN'})

# Load action nouns
_ACTION_NOUNS = json.loads(_ACTION_NOUNS_PATH.read_text())

def find_word_forms(word: str) -> dict[str, str]:
    word_forms = {"base": word}
    inflections = getAllInflections(word)
    for tag, forms in inflections.items():
        if tag in _SUPPORTED_INFLECTIONS:
            if forms[0] != word:  # Avoid adding the base form again
                word_forms[tag] = forms[0]  # Take the first inflection
    # In addition, check if there's a supported action noun
    if word in _ACTION_NOUNS and _ACTION_NOUNS[word]:
        word_forms['ANN'] = _ACTION_NOUNS[word]            
    
    return word_forms

class WordFormsExtractor:
    def __init__(self):
        self.words = {}
        self._all_forms = []
    
    def __call__(self, word: str) -> None:
        if not word.strip():
            return
        word = word.strip().lower()
        if word in self._all_forms:
            return
        word_forms = find_word_forms(word)
        self._all_forms.extend(word_forms.values())
        self.words[word] = word_forms
        
@dataclass
class TaggedWord:
    base: str
    tag: str | None = None
    
    # Validate the word against allowed words
    def __post_init__(self):
        if self.tag and self.tag not in _SUPPORTED_TAGS:
            raise ValueError(f"Unsupported tag: {self.tag}")
        
@lru_cache(maxsize=1)
def _load_word_forms() -> tuple[dict[str, dict[str, str]], frozenset[str], dict[str, TaggedWord]]:
    """Read `word-forms.json` and work out what can be looked up in it.

    The file is written once by this module and does not change while a program
    runs, but reading it and building the maps takes long enough that doing it
    again for every text was most of the time that checking a whole folder took.
    It is done once, and every dictionary shares the result.
    """
    word_forms: dict[str, dict[str, str]] = json.loads(
        _WORD_LIST_PATH.with_name("word-forms.json").read_text()
    )
    allowed_words = frozenset(
        word for forms in word_forms.values() for word in forms.values()
    )
    # Now map each form to its base, plus the appropriate tag if needed
    word_map: dict[str, TaggedWord] = {}
    for base, forms in word_forms.items():
        for tag, form in forms.items():
            if tag == 'base':
                word_map[form] = TaggedWord(base=base)
            else:
                word_map[form] = TaggedWord(base=base, tag=tag)
    return word_forms, allowed_words, word_map


class WordFormsDictionary:
    """The allowed words, and what each of them is a form of.

    Making one of these is cheap: they all share the one loaded copy of the
    word forms, which is read only.
    """

    def __init__(self):
        self._word_forms, self._allowed_words, self._word_map = _load_word_forms()

    @property
    def allowed_words(self) -> frozenset[str]:
        return self._allowed_words
    
    def get_tagged_word(self, word: str) -> TaggedWord | None:
        return self._word_map.get(word, None)
    
    def get_tokens(self, word: str) -> list[str]:
        if word not in self._word_map:
            return ["<UNK>"]
        tword = self._word_map[word]
        tokens = [tword.base]
        if tword.tag:
            tokens = [f"<{tword.tag}>"] + tokens
        return tokens

if __name__ == "__main__":
    words_with_variants = {}
    raw_words = _WORD_LIST_PATH.read_text().splitlines()
    # Start with 'be' as a special case
    words_collection = WordFormsExtractor()
    words_collection('be')

    for word in raw_words:
        words_collection(word)

    with _WORD_LIST_PATH.with_name("word-forms.json").open('w') as f:
        json.dump(words_collection.words, f, indent=4)