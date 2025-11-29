import json
from pathlib import Path
from nltk.corpus import wordnet as wn


if __name__ == "__main__":
    words_path = Path("tinyfacts/thing-explainer/thing-explainer-1000.txt")
    words = words_path.read_text().splitlines()
    output_path = words_path.parent / "action-nouns.json"
    print(f"Loaded {len(words)} Thing Explainer words.")
    # Load existing action nouns if any
    if output_path.exists():
        with open(output_path, 'r') as f:
            supported_an = json.load(f)
    else:
        supported_an = {}
    
    # Iterate over the words
    for w in words:
        vsets = wn.synsets(w, pos=wn.VERB)
        # Filter only those who coincide exactly with the word
        vsets = [vs for vs in vsets if vs.lemmas()[0].name() == w]
        if vsets and (w not in supported_an):
            supported_an[w] = ""
    # Save the results
    with open(output_path, 'w') as f:
        json.dump(supported_an, f, indent=2)
    print(f"Saved action nouns to {output_path}")