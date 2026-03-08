---
name: writing-thing-explainer
description: Use when writing new Thing Explainer explanations in this repository, checking whether text is valid, or creating content for the claude_code_created folder.
---

# Writing Thing Explainer Content

## Overview

Thing Explainer explanations may only use the ~1000 most common English words (plus allowed inflected forms — ~2900 total forms). The allowed set is in `tinyfacts/thing-explainer/word-forms.json`. Write, then verify with the check tool. Expect several iterations.

## Workflow

1. **Look up the word list** before writing — many obvious words are missing:
   ```bash
   uv run python -c "
   from tinyfacts.word_forms import WordFormsDictionary
   d = WordFormsDictionary()
   # Check specific words:
   words = ['cloud', 'river', 'war', 'knife']
   for w in words: print(w, '✓' if w in d.allowed_words else '✗')
   "
   ```

2. **Write** the explanation, using substitutions from the table below.

3. **Check** with `--full` to see every invalid occurrence with context:
   ```bash
   uv run python main.py check --full path/to/file.txt
   ```

4. **Fix and repeat** until the file passes:
   ```bash
   uv run python main.py check path/to/file.txt
   # ✓ All words in ... are in the Thing Explainer word list!
   ```

## Common Missing Words and Substitutions

| Missing word | Use instead |
|---|---|
| `itself` | restructure the sentence |
| `cloud` | "the grey hanging things in the sky" |
| `sea` / `ocean` | "the great wide water" |
| `river` / `lake` | "moving water" / "wide still water" |
| `plant` / `seed` / `flower` | "growing thing" / "small hard part" / "bright part" |
| `mountain` / `forest` | "very tall ground" / "a place with many trees" |
| `bird` / `fish` | "flying animal" / "animal that lives in water" |
| `ship` / `boat` | "big thing that moves on water" |
| `war` / `battle` | "great fight" / "fight" |
| `king` / `queen` | "the one who rules" |
| `soldier` | "fighting person" |
| `enemy` | "those they fight against" |
| `priest` | "man who works for god" |
| `wolf` / `wild` | "large free animal" / "living without people" |
| `hunt` | "chase animals for food" |
| `metal` | "hard stuff from the ground" |
| `tool` / `machine` | "thing used to do work" |
| `secret` | "without anyone knowing" |
| `heat` (noun) | "how hot it is" / restructure |
| `mix` / `mixing` | "join" / "joining" |
| `rise` | "go up" |
| `thousands` | "many hundreds" |
| `gravity` | "the pull toward the ground" |
| `electricity` | "the power that moves through wires" |
| `size` / `sizes` | "how big" |
| `center` | "middle" |
| `directly` | remove or rephrase |
| `affect` | "change" |
| `nearby` | "close to it" |
| `mainly` | "most of" |
| `awake` | "not sleeping" |
| `decisions` | use "decides" (verb form instead) |
| `practice` (noun) | "working through" |
| `eight` | "around seven to ten" or use a different number |
| `vary` | "change" |
| `forever` | "for as long as they live" |
| `wise` | "kind" or "careful" |
| `pool` | "wide still water" |
| `garden` | "the yard" / "outside the home" |
| `special` | "one" / "a certain" |
| `exist` | "be here" |
| `apart` | restructure: "break up and join" |

## Watch Out For

- **Possessives** like `girl's`, `boy's` fail — use "of the girl", "of the boy"
- **`grey` not `gray`** — the list has only the British spelling
- **Proper nouns** (names of people, places) are not in the list and will fail the check — this is expected and acceptable
- **`itself`** is not allowed — always restructure

## Output Location

Save generated files to `claude_code_created/` using lowercase snake_case filenames.
