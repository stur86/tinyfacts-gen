---
name: update-tinyfacts-dataset
description: Use when adding generated texts to the tinyfacts dataset, filling in the questions rows are missing, exporting training files, taking rows out, or syncing the dataset with the Hugging Face Hub.
---

# Updating the Dataset

## Overview

The texts are not kept in git. They live as `.jsonl` chunks in a dataset repository on
the Hugging Face Hub, with a working copy in `.dataset/` (gitignored). `dataset.yaml`
says which Hub repo it is (`Stur86/tinyfacts`), where the working copy sits, and how many
rows go in one chunk.

Every command is `uv run python main.py dataset <command>`, and every one of them takes
`--help`.

One row per text, with `id` = `<source>/<name>` — the folder the text came from, minus
the `_created`, and the file name minus its suffix.

## The Usual Round

```bash
uv run python main.py dataset add            # read the *_created folders in
uv run python main.py dataset enrich         # ask a model for the missing questions
uv run python main.py dataset stats          # look at what is there now
uv run python main.py dataset sync           # pull the Hub copy, merge, push it back
```

Do them in that order. `add` and `enrich` only touch the working copy; nothing leaves
this machine until `sync` (or `push`).

### add

Reads every folder whose name ends in `_created`, and puts in what is not in the dataset
yet. Rows are matched by id, so running it again is safe and cheap.

```bash
uv run python main.py dataset add --dry-run          # say what would happen, write nothing
uv run python main.py dataset add --include claude   # only folders whose name matches
uv run python main.py dataset add --overwrite        # let the files on disk win
```

- What a row knows — title, question, model, provider, tags — comes out of the YAML
  block at the top of the file. Nothing about a folder is configured anywhere.
- A text that uses words outside the word list is **left out**, and counted at the end.
  `--allow-invalid` keeps it, but fix the text instead: see the `edit-thing-explainer`
  skill.
- A file with no YAML block still makes a row: its title comes from its file name, and
  everything else stays empty.
- Without `--overwrite`, a row that is already there is left as it is, even when the file
  on disk has changed.

### enrich

Fills in `instruction` — the question a text answers — for the rows that have none, by
asking a model. The answer is kept in the dataset, so it is worked out once and not
again on every export.

```bash
uv run python main.py dataset enrich --dry-run                  # how many rows need one
uv run python main.py dataset enrich --limit 20                 # try a few first
uv run python main.py dataset enrich -p ollama --question-model my-model
```

Rows are saved as they are made, so a run that stops loses nothing — start it again.
Rows that fail are counted and can be tried again the same way. `--overwrite` makes a
new question even for rows that have one.

Better than enriching: write the question into the file's YAML block as `instruction`
when the text is made, and it is never asked of a model at all.

## Filters

`enrich`, `export`, `stats` and `remove` all take the same filters, and every filter
given has to pass.

| Filter | What it takes |
| --- | --- |
| `--id`, `--title`, `--text`, `--instruction` | a regular expression |
| `--source`, `--model`, `--tag` | a name, repeated, or a comma separated list |
| `--with-instruction` / `--without-instruction` | rows that do, or do not, have a question |
| `--min-words`, `--max-words` | how long the text is |

```bash
uv run python main.py dataset stats --title "^how " --min-words 300 --without-instruction
```

Use `stats` with the filters first to see how many rows something would touch, before
running `enrich` or `remove` with the same ones.

## Looking at Rows

```bash
uv run python main.py dataset stats                       # counts by source and by model
uv run python main.py dataset show tinyfacts-llama/rain   # one row, as it is kept
```

## Exporting for Training

```bash
uv run python main.py dataset export train.jsonl --format instruct --model gpt-5.1
uv run python main.py dataset export - --format full --limit 3      # to the screen
```

`--format` picks what each row looks like:

- `text`: `id`, `text`
- `instruct`: `id`, `user`, `assistant`
- `chat`: `id`, `messages`
- `full`: the whole row

`instruct` and `chat` leave out rows with no question, and say how many they left. Run
`enrich` first if that number matters.

## Taking Rows Out

```bash
uv run python main.py dataset remove claude_code/how_rain_works    # by id
uv run python main.py dataset remove --source big_pickle --dry-run # by filter, safely
uv run python main.py dataset remove --source big_pickle -y        # do not ask
```

Give ids **or** a filter, never both. It asks before it takes anything out unless `-y`.
Always look at `--dry-run` first.

Then send the result up with **`push`, not `sync`**: a sync brings down what is on the
Hub before it sends anything, so the rows would come straight back.

Taking out an early row shifts every chunk after it, so the push is a big one. Rows near
the end are the cheap ones to take out.

## The Hub

```bash
uv run python main.py dataset pull                  # start from what is on the Hub
uv run python main.py dataset push --dry-run        # see what would go up
uv run python main.py dataset sync -M "add 40 texts"
```

- `sync` = pull, merge, push, in one commit. It is what to use for ordinary adding.
- Rows are matched by id; where local and remote disagree, **local wins**, unless
  `--prefer-remote`.
- Only the chunks that really changed are sent, so adding a few texts sends one small
  file.
- Pushing needs a token with write rights: `--token`, or `TINYFACTS_HF_TOKEN`, `HF_TOKEN`
  or `HUGGINGFACE_TOKEN` in the environment or a `.env` file. Never put a token in a
  file that git keeps.
- `--repo` or `TINYFACTS_HF_REPO` sends it somewhere other than the repo in
  `dataset.yaml` — useful for trying a push against a repo of your own.
- Ask the user before any push or sync. It is public and hard to undo.

## The Dataset Card

The card on the Hub is written from `README_HF.md` on every push. That file describes
the **dataset**, not this software (`README.md` is the software). It is a template: names
like `{{rows}}` and `{{models_table}}` are filled in from the dataset itself as it is
pushed, so no number in the card can fall out of step with the rows.

- Edit `README_HF.md` to change the card, and keep counts as template names rather than
  writing numbers by hand.
- `push --dry-run` sends nothing but leaves the card it would have sent in
  `.preview/README.md` (gitignored). Read that over after changing the template.
- `--no-card` leaves the card on the Hub alone and sends only the rows.
- `push` says which template names it knows, if one is used that it does not.

## Watch Out For

- **`sync` after `remove`** puts the removed rows back. Use `push`.
- **Renaming a text file** makes a new row instead of changing the old one; the old row
  stays until it is removed by id.
- **A text that fails the word check** never reaches the dataset. `add` says how many
  were left out; find them with `main.py check` and fix them.
- **`.dataset/` is not in git.** If it is missing, `dataset pull` builds it again from
  the Hub.
- **Nothing is written by `--dry-run`**, on any command that has it. Use it first.
