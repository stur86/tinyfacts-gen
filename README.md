# Tinyfacts-gen

Helps generating text that follows the '1000 most common words of English' (plus inflected forms) established by xkcd's Up-Goer Five comic.

## How to use

Run `main.py` with one of the following arguments:

* `editor`: launch a terminal text editor that automatically highlights any incorrect words and helps you write compliant text;
* `agent`: launch an agent connecting to the OpenAI API (credentials are loaded from a `.env` file if present), or to a local ollama instance, to generate and refine a text via tool-calling;
* `check`: verify whether a given text file is compliant with the standard and report any violations;
* `check-words`: check whether specific words are in the list;
* `suggest`: look up a compliant way to say a word that is *not* in the list;
* `suggest-add`: add a new entry to the circumlocutions database;
* `dataset`: build the dataset out of the generated texts, filter it, and keep it in step with the Hugging Face Hub (see [The dataset](#the-dataset));
* `stats`: produce statistics on the total number of generated files and words in the repository.

With any of these options, use `--help` for more information.

### Where generated text goes

`agent`, `generate` and `editor` all save into a `<model_name>_created` folder as a
markdown file with a YAML block at the top of it:

```markdown
---
title: The Sun
instruction: What is the sun?
model: gpt-5.1
provider: openai
created_at: '2026-01-30T10:12:00+00:00'
---

The sun is a big hot light...
```

Everything in the block is optional, and older `.txt` files with no block still work
everywhere. The block is what carries the question a text answers, so it does not have
to be worked out again later. It is left out of every word check and word count.

### Circumlocutions

`tinyfacts/thing-explainer/circumlocutions.json` is a plain mapping of
`"word": "alternative expression"` — ways to say words that are *not* in the 1000 word
list using only words that are (`"river": "moving water"`). Every alternative is itself
checked against the word list, so a suggestion is always safe to paste into a text.

```bash
python main.py suggest gravity rivers        # look words up (inflected forms work too)
python main.py suggest --search "wide water" # find entries by word or by alternative
python main.py suggest --list                # dump the whole database
python main.py suggest --validate            # re-check every entry against the word list
```

`check` and `check-words` take `--suggest` to annotate their output:

```bash
python main.py check --suggest path/to/file.txt
python main.py check-words cloud river war --suggest
```

To grow the database, use `suggest-add`. The entry is refused if the alternative uses
words outside the list, or if the word did not need replacing in the first place:

```bash
python main.py suggest-add tail "the long part at the back of an animal"
```

The `agent` command passes the database to the model by default: alternatives come back
inside the word check results, and a `suggest_other_words` tool is available for looking
words up before writing. This costs prompt space and model attention, so it can be turned
off with `--no-suggestions`.

`--save-suggestions` additionally gives the agent a `save_new_word` tool, so a good phrase
it works out for a missing word is kept for next time. It is **off by default**, since it
writes to a file that is otherwise curated by hand. Entries still go through the same
validation, and unlike `suggest-add` the agent cannot overwrite an entry that already
exists — it is told one is there instead.

### Custom providers

Besides the built-in `openai`, `ollama` and `google` providers, `agent --provider <name>` accepts
the name of any OpenAI-compatible server defined in `custom_providers.yaml`. That file is
gitignored; copy `custom_providers.example.yaml` to get started:

```yaml
providers:
  myserver:
    base_url: https://llm.internal/v1
    api_key_env: MYSERVER_API_KEY  # or `api_key: sk-...`, or omit both for servers with no auth
    default_model: llama-3.3-70b   # optional; if unset, --model is required
```

Then run e.g. `python main.py agent --provider myserver`.

## The dataset

The generated texts are kept as a dataset of `.jsonl` chunks and live on the
[Hugging Face Hub](https://huggingface.co/datasets), not in this repository. The working
copy sits in `.dataset/` (gitignored); `dataset.yaml` says which Hub repo it belongs to,
how big a chunk is, and what is known about each folder of generated text.

One row per text:

| Field | What it is |
| --- | --- |
| `id` | Row id, `<source>/<name>`. |
| `text` | The explanation. |
| `title` | What the text is about. |
| `source` | The folder or run the text came from. |
| `model`, `provider` | Who wrote it, and where it was asked. |
| `instruction` | The question the text answers, when it is known. |
| `instruction_model` | The model that worked out the question, if one did. |
| `tags`, `word_count`, `added_at` | Labels, size, and when the row was made. |

### The usual round

```bash
python main.py dataset add          # read the *_created folders into the dataset
python main.py dataset enrich       # ask a model for the questions that are missing
python main.py dataset sync         # pull the Hub copy, merge, push it back
```

`add` only puts in what is not there yet, matched by id, and leaves out any text that
uses words outside the list. What a file says about itself in its YAML block wins over
what `dataset.yaml` says about the folder it is in; `--overwrite` lets the files on disk
win over the dataset as well.

`enrich` fills in `instruction` for the rows that have none, using the same kind of agent
`compile --instruct` used to use — the difference being that the question is now kept in
the dataset instead of being made afresh on every export. Rows are saved as they are
made, so a run that stops can simply be started again.

### Filtering

`export`, `enrich` and `stats` all take the same filters, and every one that is given has
to pass. `--title`, `--id`, `--text` and `--instruction` are regular expressions;
`--source`, `--model` and `--tag` take a name, or several, or a comma separated list.

```bash
# every text a given model wrote, as question and answer rows
python main.py dataset export train.jsonl --format instruct --model gpt-5.1

# the long ones about how things work, with no question yet
python main.py dataset stats --title "^how " --min-words 300 --without-instruction

# make questions for just those, then write them out as chat messages
python main.py dataset enrich --title "^how " --provider openai
python main.py dataset export chat.jsonl --format chat --title "^how "
```

`--format` picks what each row looks like: `text` (`id`, `text`), `instruct` (`id`,
`user`, `assistant`), `chat` (`id`, `messages`), or `full` for the whole row.
`instruct` and `chat` leave out rows that have no question, and say how many they left.

### Syncing with the Hugging Face Hub

`sync` brings down what is on the Hub, merges the local rows into it, and sends the
result back in one commit. Rows are matched by id; where the two disagree the local row
wins, unless `--prefer-remote` is given. Only the chunk files that really changed are
sent, so adding a few texts sends one small file. `pull` and `push` do the two halves on
their own, and `--dry-run` says what would be sent without sending it.

The Hub repo comes from `dataset.yaml`, and either `--repo` or the `TINYFACTS_HF_REPO`
environment variable wins over it. A token with write rights is needed to push: pass
`--token`, or set `TINYFACTS_HF_TOKEN`, `HF_TOKEN` or `HUGGINGFACE_TOKEN` (a `.env` file
works). A dataset card is written along with the rows; `--no-card` leaves it alone.

```bash
python main.py dataset sync --token hf_...          # or set HF_TOKEN
python main.py dataset pull                         # start from what is on the Hub
python main.py dataset push --dry-run               # see what would go up
```

### Folders the dataset is built from

`dataset.yaml` says what is known about each `*_created` folder: the model that wrote its
texts, the provider, and where its questions come from. A folder that is not named there
still works — its source name and model are taken from the folder name — but naming it
means its rows carry the right model, and their questions can be worked out instead of
asked for:

```yaml
sources:
  tinyfacts-llama:
    model: tinyfacts-llama
    # every text answers the same question about its own title
    instruction_template: "Explain the following word: {title}"

  questions_gemini-3-flash-preview_cloud:
    model: gemini-3-flash-preview:cloud
    # answer_<n>.txt answers line <n> (counting from 0) of this file
    instructions_file: thing_explainer_questions.txt.q
    instructions_name_pattern: "answer_(\\d+)"
    title_template: "{instruction}"
```
