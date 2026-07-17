# Tinyfacts-gen

Helps generating text that follows the '1000 most common words of English' (plus inflected forms) established by xkcd's Up-Goer Five comic.

## How to use

Run `main.py` with one of the following arguments:

* `editor`: launch a terminal text editor that automatically highlights any incorrect words and helps you write compliant text;
* `agent`: launch an agent connecting to the OpenAI API (credentials are loaded from a `.env` file if present), or to a local ollama instance, to generate and refine a text via tool-calling;
* `check`: verify whether a given text file is compliant with the standard and report any violations;
* `stats`: produce statistics on the total number of generated files and words in the repository.

With any of these options, use `--help` for more information.

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