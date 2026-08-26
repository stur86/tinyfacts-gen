---
name: writing-thing-explainer
description: Use when writing new Thing Explainer explanations in this repository, checking whether text is valid, or saving a new entry as a markdown file in a *_created folder (such as claude_code_created).
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

## Writing a New Entry

A new text is one markdown file in a folder whose name ends in `_created`. That is all
`main.py dataset add` needs to find it; nothing has to be told about the folder anywhere
else.

### 1. Pick the folder and the file name

- Folder: `claude_code_created/` for texts written here. The part before `_created`
  becomes the `source` of the rows the folder gives (`claude_code`).
- File name: lowercase, `_` between the words, `.md` at the end — `how_rain_works.md`.
- The file name, with no suffix, names the row: `<source>/<name>`, e.g.
  `claude_code/how_rain_works`. Keep the name once it is in the dataset: renaming a file
  makes a **new** row, it does not change the old one.

### 2. Write the YAML block, then the text

```markdown
---
title: How rain works
instruction: How does rain work?
model: claude-opus-5
provider: claude-code
created_at: '2026-08-26T09:14:00+00:00'
tags:
- how-things-work
---

Water goes up into the air when the sun makes it hot...
```

- `title`: short, and about the thing, not about the file. Without it, the file name
  with its `_` turned into spaces is used instead.
- `instruction`: the question the text answers. Write it — it is what makes the row
  usable for training, and a row without one has to have one worked out later by a model
  (`dataset enrich`).
- `model` and `provider`: who really wrote the text. `provider: human` with no model is
  what a hand-written text says, so do not use it for a text a model wrote.
- `created_at`: the time now, with a time zone on it (`2026-08-26T09:14:00+00:00`).
- `tags`: free labels, and optional.

Everything in the block is optional, and the block is left out of every word check and
word count, so `check` reads the text alone.

### 3. Check it before you call it done

```bash
uv run python main.py check --full --suggest claude_code_created/how_rain_works.md
```

`dataset add` leaves out any text that uses words outside the list, so a file that does
not pass is simply not part of the dataset. Fix it until the check passes.

### 4. Put it in the dataset

Adding the file to the dataset, and sending it to the Hugging Face Hub, is its own job:
see the `update-tinyfacts-dataset` skill. The short of it:

```bash
uv run python main.py dataset add
uv run python main.py dataset sync
```
