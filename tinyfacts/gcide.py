import subprocess
import re
from enum import Enum

class POS(str, Enum):
    NOUN = "noun"
    PRONOUN = "pronoun"
    VERB_TRANSITIVE = "verb (transitive)"
    VERB_INTRANSITIVE = "verb (intransitive)"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"

def get_pos_list(word: str) -> set[POS]:
    """
    Get POS for a word from GCIDE using structured parsing.
    Follows this logic:
      1. Parse the first line for number of definitions (not strictly needed but can be validated)
      2. Split entries by the fixed header
      3. Skip two lines to reach the actual dictionary entry
      4. Keep only entries where the literal word matches
      5. Extract POS:
         - n. -> noun
         - v. t. -> verb (transitive)
         - v. i. -> verb (intransitive)
         - a. -> adjective
         - adv. -> adverb
    """
    try:
        result = subprocess.run(
            ["dict", "-d", "gcide", word],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError:
        return set()  # word not found

    text = result.stdout

    pos_set: set[POS] = set()
    header = "From The Collaborative International Dictionary of English v.0.48 [gcide]:"

    # Split by the fixed header
    entries = text.split(header)
    for entry in entries:
        lines = entry.strip().splitlines()
        if not lines:
            continue
        main_line = lines[0].strip()
        # Check literal match
        # GCIDE shows "Word \Word\ ..."
        literal_match = re.match(r'^(?P<entry>\w+)\s+\\', main_line, re.IGNORECASE)
        if not literal_match:
            continue
        entry_word = literal_match.group("entry")
        if entry_word.strip().lower() != word.lower():
            continue
        # Focus on POS
        # Look for n., v. t., v. i., a., adv.
        pos_match = re.search(r',\s+(n\.|v\. t\.|v\. i\.|a\.|adv\.|pron\.)\s+', main_line)
        if pos_match:
            code = pos_match.group(1).lower()
            if code == 'n.':
                pos_set.add(POS.NOUN)
            elif code == 'v. t.':
                pos_set.add(POS.VERB_TRANSITIVE)
            elif code == 'v. i.':
                pos_set.add(POS.VERB_INTRANSITIVE)
            elif code == 'a.':
                pos_set.add(POS.ADJECTIVE)
            elif code == 'adv.':
                pos_set.add(POS.ADVERB)
            elif code == 'pron.':
                pos_set.add(POS.PRONOUN)
    return pos_set


if __name__ == "__main__":
    import sys
    words = sys.argv[1:]
    for word in words:
        pos_list = get_pos_list(word)
        pos_str = ', '.join([p.value for p in sorted(pos_list, key=lambda x: x.value)])
        print(f"{word}: {pos_str if pos_str else 'No POS found'}")