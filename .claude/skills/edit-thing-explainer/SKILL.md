---
name: edit-thing-explainer
description: Use when fixing an existing text file to comply with the Thing Explainer 1000-word constraint, replacing forbidden words with creative allowable alternatives.
---

# Editing Text to Meet the Thing Explainer Word List

## Goal

Make an existing file fully compliant with the Thing Explainer constraint: every word must appear in the ~1000-word base list (or an allowed inflected form). The file to fix is: **`$args`**

Preserve the author's meaning and voice as much as possible. Change only what the word-checker forces you to change.

## Workflow

```
check --suggest (summary) → check --full --suggest → fix word by word → recheck → repeat
```

### 1. Get the summary of violations, with replacements

```bash
uv run python main.py check --suggest $args
```

This lists every unique forbidden word with a usage count, then a **Ways to say these** block giving a known, already-validated replacement for each word the circumlocutions database knows. Read the whole list before touching anything — a single word may appear dozens of times and one good substitution fixes all of them at once.

Anything not in that block has no stored answer and needs you to invent one (strategies B–E below).

### 2. Get context for each violation

```bash
uv run python main.py check --full --suggest $args
```

This shows every occurrence with its surrounding words. Use it to understand what each forbidden word actually means *in that sentence* — a stored suggestion is a default, not an order, and the right substitution sometimes depends on context.

### 3. Fix, then recheck

Edit the file, then run step 1 again. Repeat until you see:

```
✓ All words in ... are in the Thing Explainer word list!
```

---

## Substitution Strategies (in order of preference)

### A. Take the stored suggestion

`check --suggest` has already done this step for every word the database knows. Use what it gives you unless the sentence makes it read badly.

To look a word up on its own, or to browse by meaning:

```bash
uv run python main.py suggest gravity moon rivers
uv run python main.py suggest --search "water"
```

Inflected forms and possessives resolve to their base word, so `rivers` and `river's` both find the `river` entry — inflect the replacement yourself to fit the sentence.

### B. Try a different word form

Check whether a different grammatical form of the forbidden word *is* allowed. The list includes inflected verb forms, comparatives, and plurals generated from the 1000 bases.

```bash
uv run python main.py check-words decide decision decisions decided deciding
```

If `decision` is forbidden but `decide` is allowed, rewrite the sentence to use the verb: "when they decide" instead of "the decision".

### C. Restructure the sentence

When no single swap works, rewrite the sentence to express the same idea without the forbidden word:

- **`itself`**: "the thing on its own", "on their own", or rewrite the sentence entirely
- **Possessives** (`girl's`, `city's`): "of the girl", "of the city"
- **Abstract nouns** (`existence`, `awareness`): convert to a verb phrase — "it is here", "they know about it"
- **Long compound concepts**: break into two simpler sentences

### D. Describe the concept in plain terms

For technical or abstract words with no near-synonym in the list, describe *what it does* or *what it looks like*:

- `photosynthesis` → "how a growing thing uses light to make food"
- `atmosphere` → "the air that covers the whole world"
- `nucleus` → "the part at the very middle"
- `protein` → "tiny building parts that the body makes and uses"

Ask: *If I had to explain this to a child who has never heard the word, what would I say?* Write that.

When you land on a phrase that works, put it in the database so the next edit gets it for free — do this as you go, not once at the end when you have forgotten which ones were new. The alternative is checked against the word list on the way in, so a bad entry is refused rather than stored:

```bash
uv run python main.py suggest-add tail "the long part at the back of an animal"
```

Save a phrase when the word really is missing and the phrase still makes sense away from this file. Do not save wording that only works in its own paragraph, and do not save circumlocutions for proper nouns (strategy E) — those are per-text choices. Keys are single words in base form (`dart`, not `darts`), since inflected forms resolve to the base at lookup time.

### E. Circumlocute proper nouns

Names of people and places are not in the word list. Replace them with a short descriptive phrase that makes their role clear in context:

- A character named *Romeo* → "the boy", "the young man", "he"
- A character named *Elizabeth* → "the girl", "the young woman", "she"
- *London* → "the great city", "the big city across the water"
- *France* → "the land across the water", "the land to the south"
- *Mount Everest* → "the tallest place on earth"
- A named institution → "the big place where people learn", "the house of the one who rules"

Introduce the circumlocution clearly on first use so the reader knows who or what is being talked about, then use shorter forms ("the boy", "she", "the city") afterwards.

---

## Watch-Outs

- **`grey` not `gray`** — only the British spelling is in the list.
- **Possessives** (`dog's`) always fail — rewrite as "of the dog".
- **`itself`** is not in the list — always restructure.
- **Contractions** like `isn't`, `don't`, `he's` are in the list; less common ones may not be — check before using.
- A word used in two different senses in the same file may need two different substitutions.
