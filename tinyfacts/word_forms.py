#!/usr/bin/env python3
"""
Generate word-forms.json using NLTK to find all valid inflections of the base 1000 words.
"""
import json
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
        
class WordFormsDictionary:
    
    def __init__(self):
        # Read existing word forms
        self._word_forms: dict[str, dict[str, str]] = json.loads(_WORD_LIST_PATH.with_name("word-forms.json").read_text())
        self._allowed_words = set([word for forms in self._word_forms.values() for word in forms.values()])
        # Now map each form to its base, plus the appropriate tag if needed
        self._word_map: dict[str, TaggedWord] = {}
        for base, forms in self._word_forms.items():
            for tag, form in forms.items():
                if tag == 'base':
                    self._word_map[form] = TaggedWord(base=base)
                else:
                    self._word_map[form] = TaggedWord(base=base, tag=tag)
                    
    @property
    def allowed_words(self) -> set[str]:
        return self._allowed_words
    
    def get_tagged_word(self, word: str) -> TaggedWord | None:
        return self._word_map.get(word, None)
    
    def get_tokens(self, word: str) -> list[str]:
        if word not in self._word_forms:
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