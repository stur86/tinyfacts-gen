---
name: writing-thing-explainer
description: Use when writing new Thing Explainer explanations in this repository, checking whether text is valid, or creating content for the claude_code_created folder.
---

# Writing Thing Explainer Content

## Overview

Thing Explainer explanations may only use the ~1000 most common English words (plus allowed inflected forms — ~2900 total forms). The allowed set is in `tinyfacts/thing-explainer/word-forms.json`. Write, then verify with the check tool. Expect several iterations.

## Workflow

1. **Look up the word list** before writing — many obvious words are missing. Add
   `--suggest` and you also get a ready-made way to say the ones that fail:
   ```bash
   uv run python main.py check-words cloud river war knife --suggest
   # ✗ cloud → the grey stuff hanging in the sky
   # ✗ river → moving water
   ```

2. **Write** the explanation. When you need a word you suspect is missing, look it up
   rather than inventing a workaround — the database already has ~400 of them, many
   harvested from the texts already in this repository:
   ```bash
   uv run python main.py suggest gravity moon rivers
   uv run python main.py suggest --search "water"   # browse by meaning
   ```

3. **Check** with `--full` to see every invalid occurrence with context, and `--suggest`
   to get a replacement for each one:
   ```bash
   uv run python main.py check --full --suggest path/to/file.txt
   ```

4. **Fix and repeat** until the file passes:
   ```bash
   uv run python main.py check path/to/file.txt
   # ✓ All words in ... are in the Thing Explainer word list!
   ```

5. **Record what you worked out.** Do this before you finish, not as an afterthought.
   Every time you invented a phrase for a word `suggest` had no entry for, and the phrase
   is one another writer would want, add it:
   ```bash
   uv run python main.py suggest-add tail "the long part at the back of an animal"
   ```
   The alternative is validated on the way in, so a bad entry is refused rather than
   stored. Worth saving:

   - the word really is missing from the list (`check-words` says `✗`), and
   - the phrase stands on its own, away from the text you wrote it for, and
   - it names the thing rather than describing its role in one sentence.

   `"lava" → "hot wet rock"` is worth saving. `"the round thing he was carrying"` is not
   — it only means anything inside its own paragraph. Skip proper nouns entirely; a
   circumlocution for a character or a place belongs in the text, not the database.

   Keys must be single words, in their base form: `dart`, not `darts`; `melt`, not
   `melting`. Inflected forms resolve to the base at lookup time, so the base covers them
   all. If a word already has an entry you think is worse than yours, say so rather than
   overwriting it silently.

## Common Missing Words and Substitutions

These all live in `tinyfacts/thing-explainer/circumlocutions.json` — ask the tool rather
than working from memory, since the database is kept validated and this list is not:

```bash
uv run python main.py suggest <word> [<word> ...]
uv run python main.py suggest --list          # all of them
```

The traps you will hit most often:

| Missing word | Use instead |
|---|---|
| `itself` | "on its own", or restructure the sentence |
| `cloud` | "the grey stuff hanging in the sky" |
| `sea` / `ocean` | "the great wide water" |
| `river` / `lake` | "moving water" / "wide still water" |
| `moon` | "the great light in the night sky" |
| `plant` / `seed` | "growing thing" / "the small hard part a growing thing comes from" |
| `mountain` / `forest` | "very tall ground" / "a place with many trees" |
| `bird` / `fish` | "flying animal" / "animal that lives in the water" |
| `war` / `enemy` | "great fight" / "those they fight against" |
| `law` / `rule` | "the things everyone must follow" |
| `metal` | "hard bright stuff from the ground" |
| `tool` / `machine` | "thing used to do work" |
| `gravity` | "the pull toward the ground" |
| `heat` (noun) / `size` | "how hot it is" / "how big something is" |
| `thousand` / `million` | "many hundreds" / "many hundreds of hundreds" |

Whole families of ordinary words are also missing with no obvious warning: `thin`,
`flat`, `weak`, `bend`, `flow`, `melt`, `float`, `sink`, `spread`, `shape`, `count`,
`worth`, `hole`, `simple`, `anywhere`, `everywhere`, `nobody`, `whose`, `twice`,
`winter`, `season`. Check before you lean on one.

## Watch Out For

- **Possessives** like `girl's`, `boy's` fail — use "of the girl", "of the boy"
- **`grey` not `gray`** — the list has only the British spelling
- **Proper nouns** (names of people, places) are not in the list and will fail the check — this is expected and acceptable
- **`itself`** is not allowed — always restructure

## Output Location

Save generated files to `claude_code_created/` using lowercase snake_case filenames.
