# Tinyfacts-gen

Helps generating text that follows the '1000 most common words of English' (plus inflected forms) established by xkcd's Up-Goer Five comic.

## How to use

Run `main.py` with one of the following arguments:

* `editor`: launch a terminal text editor that automatically highlights any incorrect words and helps you write compliant text;
* `agent`: launch an agent connecting to the OpenAI API (credentials are loaded from a `.env` file if present), or to a local ollama instance, to generate and refine a text via tool-calling;
* `check`: verify whether a given text file is compliant with the standard and report any violations;
* `stats`: produce statistics on the total number of generated files and words in the repository.

With any of these options, use `--help` for more information.