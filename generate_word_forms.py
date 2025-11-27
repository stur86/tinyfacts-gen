#!/usr/bin/env python3
"""
Generate word-forms.json using NLTK to find all valid inflections of the base 1000 words.
"""
import json
from pathlib import Path
from lemminflect import getAllInflections

_WORD_LIST_PATH = Path(__file__).parent / "tinyfacts" / "thing-explainer" / "thing-explainer-1000.txt"

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

def find_word_forms(word: str) -> dict[str, str]:
    word_forms = {"base": word}
    inflections = getAllInflections(word)
    for tag, forms in inflections.items():
        if tag in _SUPPORTED_INFLECTIONS:
            if forms[0] != word:  # Avoid adding the base form again
                word_forms[tag] = forms[0]  # Take the first inflection
    return word_forms

class WordFormsCollection:
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

if __name__ == "__main__":
    words_with_variants = {}
    raw_words = _WORD_LIST_PATH.read_text().splitlines()
    # Start with 'be' as a special case
    words_collection = WordFormsCollection()
    words_collection('be')
    
    for word in raw_words:
        words_collection(word)
        
    with _WORD_LIST_PATH.with_name("word-forms.json").open('w') as f:
        json.dump({
            "comment": "Generated word forms for the Thing Explainer 1000 words using lemminflect.",
            "words": words_collection.words
        }, f, indent=4)