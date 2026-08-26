# Tinyfacts-gen

Helps generating text that follows the '1000 most common words of English' (plus inflected forms) established by xkcd's Up-Goer Five comic.

## How to use

The project is managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync                          # make the environment
uv run python main.py --help     # see every command
```

Run `main.py` with one of the following arguments:

* `editor`: launch a terminal text editor that automatically highlights any incorrect words and helps you write compliant text;
* `agent`: launch an agent connecting to the OpenAI API (credentials are loaded from a `.env` file if present), or to a local ollama instance, to generate and refine a text via tool-calling;
* `generate`: go through a whole word list with a model that already knows the word list, one text per word, with no agent and no checking (see [Going through a whole word list](#going-through-a-whole-word-list));
* `check`: verify whether a given text file is compliant with the standard and report any violations;
* `check-words`: check whether specific words are in the list;
* `suggest`: look up a compliant way to say a word that is *not* in the list;
* `suggest-add`: add a new entry to the circumlocutions database;
* `dataset`: build the dataset out of the generated texts, filter it, and keep it in step with the Hugging Face Hub (see [The dataset](#the-dataset));
* `stats`: produce statistics on the number of generated files and words in a folder (`--folder`, the current one by default).

With any of these options, use `--help` for more information.

### Where generated text goes

`agent` and `generate` save into a `<model_name>_created` folder, and `editor` into
`manually_created`; `-o` sends any of them somewhere else. Every folder whose name ends
in `_created` is read by `dataset add`, and what comes before the `_created` becomes the
`source` of its rows. Each text is a markdown file with a YAML block at the top of it:

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
to be worked out again later. It is left out of every word check and word count. The
editor writes `provider: human` and no model, which is how a hand-written text is told
apart from a generated one later.

The file name, with no suffix, names the row the text becomes: `<source>/<name>`. Use
lowercase names with `_` between the words, and keep them as they are, since renaming a
file makes a new row rather than changing the old one.

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

### Going through a whole word list

`generate` explains every word of a list, one text per word. It talks straight to an
OpenAI style API — a local server by default — and it uses no agent and makes no word
check: the model is expected to be fine-tuned so that it keeps to the allowed words on
its own.

```bash
python main.py generate                                  # the built-in list, localhost:8137
python main.py generate --words words.txt --model my-llm # a list of your own
python main.py generate -b http://other-box --port 9000 -o my_run_created
```

`--words` takes a file path or a URL, one word per line; it defaults to the
`google-10000-english-no-swears` list. The API is `<base-url>:<port>/v1`, so `--base-url`
takes no port on it. Each word makes one file named after the word, and a word that
already has a file is skipped, so a run that stops can simply be started again. A call
that fails is counted and named at the end while the run carries on.

## The dataset

The generated texts are kept as a dataset of `.jsonl` chunks and live on the
[Hugging Face Hub](https://huggingface.co/datasets), not in this repository. The working
copy sits in `.dataset/` (gitignored); `dataset.yaml` says which Hub repo it belongs to
and how big a chunk is.

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

`add` reads every `*_created` folder next to `dataset.yaml`, or under the folder given
by `--folder`; `--include` and `--exclude` keep to the folder names that match. It only
puts in what is not there yet, matched by id, and leaves out any text that uses words
outside the list, unless `--allow-invalid` is given. Everything a row knows comes out of
the YAML block of the file it was read from; `--overwrite` lets the files on disk win
over the dataset as well, and `--dry-run` says what would happen and writes nothing.

`enrich` fills in `instruction` for the rows that have none, by asking a model what
question each text answers, with `--provider` and `--question-model` saying who to ask.
The question is then kept in the dataset, instead of being made afresh on every export.
Rows are saved as they are made, so a run that stops can simply be started again. Use
`--limit` to try a few first, and `--overwrite` to make a new question even for rows
that have one.

`show` prints one row as it is kept, which is the way to see what a text ended up
knowing about itself:

```bash
python main.py dataset show tinyfacts-llama/rain
```

### Taking rows out

`remove` takes rows out of the working copy, either by id or by the same filters the
other commands use — one or the other, not both, so that what is about to go is never in
doubt. It asks before it does anything, unless `--yes` is given, and `--dry-run` says
what would go without taking anything out.

```bash
python main.py dataset remove tinyfacts-llama/aaa      # by id
python main.py dataset remove --source big_pickle -y   # a whole run
```

Send the result up with `dataset push`. **Not `dataset sync`**: a sync brings down what
is on the Hub before it sends anything, so the rows would come straight back. Note also
that taking out an early row shifts every chunk after it, so the push is a big one; ids
are matched exactly, so this is cheapest for rows near the end.

### Filtering

`export`, `enrich`, `stats` and `remove` all take the same filters, and every one that is
given has to pass. `--title`, `--id`, `--text` and `--instruction` are regular
expressions; `--source`, `--model` and `--tag` take a name, or several, or a comma
separated list; `--with-instruction`/`--without-instruction` keep to the rows that do, or
do not, have a question, and `--min-words`/`--max-words` to the rows of a given length.

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
works). The dataset card is written along with the rows, out of `README_HF.md`;
`--no-card` leaves the one on the Hub alone.

```bash
python main.py dataset sync --token hf_...          # or set HF_TOKEN
python main.py dataset pull                         # start from what is on the Hub
python main.py dataset push --dry-run               # see what would go up
```

### The dataset card

The card that sits on the Hub is `README_HF.md`, which describes the dataset and not
this software. It is a template: anywhere it says `{{rows}}`, `{{models_table}}` or the
like, the number or the table is put in from the dataset itself as it is pushed, so
nothing in the card can fall out of step with the rows. `dataset push` says which names
it knows if one is asked for that it does not. `--dry-run` sends nothing but leaves the
card it would have sent in `.preview/README.md` (gitignored), so it can be read over
first.

### What a text says about itself

Nothing in `dataset.yaml` describes any particular folder. A row is built out of
the YAML block at the top of the file it comes from, and the folder name only gives
the row its `source`:

```markdown
---
title: What is rain?
instruction: What is rain?
model: gemini-3-flash-preview:cloud
provider: ollama
created_at: '2026-01-28T08:26:36+00:00'
tags:
- word-explanation
---

Rain is water that falls out of the sky...
```

`agent`, `generate` and `editor` all write this block themselves, so a new run of
generations needs no new lines anywhere. A file with no block still makes a row: its
title comes from its file name, and everything else is empty until `dataset enrich`
fills the question in.

The texts that were made before the block existed were given one, once, by
`scripts/migrate_dataset.py`. That script is kept as the record of where their
titles, questions and model names came from; it is not meant to be run again.

## The other scripts

Two small scripts sit outside `main.py`, for making many texts in one go:

```bash
uv run python generate_questions.py words.txt > questions.txt
uv run python ask_questions.py -p ollama -m my-model -o my_run_created -i questions.txt
```

`generate_questions.py` turns a list of words into questions, one per line, using the
part of speech of each word ("What is a *rock*?", "What does it mean to *melt*
something?"). `--format detailed` groups them under their word instead.

`ask_questions.py` then calls `main.py agent` once per question, saving the answers as
`answer_<n>.md` in the given folder. A question whose file is already there is skipped,
so a run that stops can be started again. `questions_cmd.sh` holds the last run of it as
an example.
