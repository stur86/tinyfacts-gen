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
* `stats`: produce statistics on the total number of generated files and words in the repository.

With any of these options, use `--help` for more information.

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