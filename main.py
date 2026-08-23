import asyncio
import json
import re
import openai
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from pathlib import Path
from urllib.request import urlopen
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Annotated, Any, Callable
from typer import Typer, Argument, Option, Exit
from dotenv import load_dotenv
from pydantic_ai import PartDeltaEvent
from tinyfacts.check_words import check_words_with_context, main as check_main
from tinyfacts.circumlocutions import (
    CircumlocutionError,
    CircumlocutionsDictionary,
    Suggestion,
)
from tinyfacts.word_forms import WordFormsDictionary
from tinyfacts.agent import ThingExplainerAgent, SupportedProviders, OutputText, RunUsage
from tinyfacts.question_agent import QuestionAgent
from tinyfacts.custom_providers import CustomProviderError
from tinyfacts.text_editor import SimpleTextEditor
from tinyfacts.stats import FolderGenStats

load_dotenv()  # Load environment variables from .env file if it exists
app = Typer()


def _print_suggestions(
    console: Console, suggestions: list[Suggestion], title: str = "Ways to say these:"
) -> None:
    """Print a block of 'say this instead' lines, if there are any."""
    if not suggestions:
        return
    console.print(f"\n[bold blue]{title}[/bold blue]\n")
    for suggestion in suggestions:
        via = "" if suggestion.is_exact else f" [grey](from '{suggestion.entry}')[/grey]"
        console.print(f"  [bold]{suggestion.word}[/bold] → {suggestion.alternative}{via}")


@app.command()
def check(
    file: Path,
    full: Annotated[
        bool,
        Option("--full", "-f", help="Show every invalid occurrence with surrounding context."),
    ] = False,
    suggest: Annotated[
        bool,
        Option(
            "--suggest",
            "-s",
            help="Also show a known way to say each invalid word, where one exists.",
        ),
    ] = False,
) -> int:
    """Check if a text file only uses words from the Thing Explainer 1000 word list."""
    exit_code = check_main(file, full=full)
    if suggest and exit_code != 0:
        invalid = check_words_with_context(file.read_text()).invalid_words
        circumlocutions = CircumlocutionsDictionary()
        _print_suggestions(
            Console(), circumlocutions.suggest_many([item.word for item in invalid])
        )
    return exit_code

@app.command()
def check_words(
    words: list[str],
    suggest: Annotated[
        bool,
        Option(
            "--suggest",
            "-s",
            help="For words that are not allowed, show a known way to say them instead.",
        ),
    ] = False,
) -> None:
    """Check whether given words are in the Thing Explainer 1000 word list."""
    d = WordFormsDictionary()
    circumlocutions = CircumlocutionsDictionary() if suggest else None
    for word in words:
        allowed = word in d.allowed_words
        mark = "✓" if allowed else "✗"
        line = f"{mark} {word}"
        if circumlocutions is not None and not allowed:
            suggestion = circumlocutions.suggest(word)
            if suggestion is not None:
                line += f" → {suggestion.alternative}"
        print(line)


@app.command()
def suggest(
    words: Annotated[
        list[str] | None,
        Argument(help="Words to find an allowed way of saying."),
    ] = None,
    search_text: Annotated[
        str | None,
        Option("--search", "-s", help="List entries whose word or alternative contains this."),
    ] = None,
    list_all: Annotated[
        bool,
        Option("--list", "-l", help="List the whole database."),
    ] = False,
    validate: Annotated[
        bool,
        Option(
            "--validate",
            help="Check that every alternative in the database uses only allowed words.",
        ),
    ] = False,
) -> int:
    """Look up ways to say words that are not in the Thing Explainer word list."""
    console = Console()
    circumlocutions = CircumlocutionsDictionary()

    if validate:
        problems = circumlocutions.validate()
        console.print(
            f"Checked {len(circumlocutions)} entries in {circumlocutions.path}."
        )
        if not problems:
            console.print("[green]✓ Every entry uses only allowed words.[/green]")
            return 0
        console.print(f"[red]✗ Found {len(problems)} bad entry(s):[/red]\n")
        for problem in problems:
            detail = f" ({', '.join(problem.invalid_words)})" if problem.invalid_words else ""
            console.print(f"  [bold red]{problem.word}[/bold red]: {problem.reason}{detail}")
        return 1

    if list_all:
        _print_suggestions(
            console,
            [
                Suggestion(word=word, entry=word, alternative=alternative)
                for word, alternative in circumlocutions.entries.items()
            ],
            title="All entries:",
        )
        console.print(f"\n{len(circumlocutions)} entries in {circumlocutions.path}\n")
        return 0

    if search_text is not None:
        matches = circumlocutions.search(search_text)
        if not matches:
            console.print(f"[yellow]Nothing found for '{search_text}'.[/yellow]")
            return 1
        _print_suggestions(console, matches, title=f"Entries matching '{search_text}':")
        console.print()
        return 0

    if not words:
        console.print(
            "[yellow]Give one or more words, or use --search, --list or --validate.[/yellow]"
        )
        return 1

    word_forms = WordFormsDictionary()
    found = circumlocutions.suggest_many(words)
    by_word = {suggestion.word: suggestion for suggestion in found}
    for word in words:
        key = word.strip().lower()
        if key in word_forms.allowed_words:
            console.print(f"[green]✓ {key}[/green] is already in the word list.")
        elif key in by_word:
            suggestion = by_word[key]
            via = "" if suggestion.is_exact else f" [grey](from '{suggestion.entry}')[/grey]"
            console.print(f"[bold]{key}[/bold] → {suggestion.alternative}{via}")
        else:
            console.print(
                f"[yellow]✗ {key}[/yellow] is not allowed, and there is no entry for it yet."
            )
    return 0


@app.command()
def suggest_add(
    word: Annotated[str, Argument(help="The word that is not in the word list.")],
    alternative: Annotated[str, Argument(help="A way to say it using only allowed words.")],
) -> int:
    """Add an entry to the circumlocutions database.

    The alternative is checked against the word list first, so a bad entry is refused.
    """
    console = Console()
    circumlocutions = CircumlocutionsDictionary()
    try:
        added = circumlocutions.add(word, alternative)
    except CircumlocutionError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        return 1
    console.print(
        f"[green]Added[/green] [bold]{added.word}[/bold] → {added.alternative} "
        f"[grey]({len(circumlocutions)} entries)[/grey]"
    )
    return 0


@dataclass
class _ExplanationResult:
    explanation: OutputText
    usage: RunUsage
    task_duration: timedelta

    def output_path(self, output_folder: Path) -> Path:
        return (
                output_folder
                / f"{self.explanation.short_title.lower().replace(' ', '_')}.txt"
            )


def _generate_agent_explanation(agent: ThingExplainerAgent, topic: str, event_logger: Callable[[Any], None]) -> _ExplanationResult:
    start_time = datetime.now()
    explanation, usage = asyncio.run(
        agent.generate_explanation(topic, event_callback=event_logger)
    )
    task_duration = datetime.now() - start_time
    return _ExplanationResult(
        explanation=explanation, usage=usage, task_duration=task_duration
    )

@app.command()
def agent(
    provider: Annotated[
        str,
        Option(
            "--provider",
            "-p",
            help="The LLM provider to use (openai, ollama, google, or a name defined in custom_providers.yaml).",
        ),
    ] = SupportedProviders.OPENAI.value,
    model: Annotated[
        str | None,
        Option("--model", "-m", help="The model name to use for generation."),
    ] = None,
    skip_example: Annotated[
        bool,
        Option(
            "--skip-example",
            "-s",
            help="Skip including the example in the prompt.",
        ),
    ] = False,
    suggestions: Annotated[
        bool,
        Option(
            "--suggestions/--no-suggestions",
            help="Give the agent the circumlocutions database, as a tool and inside the word "
            "check results. Turn off to keep the prompt and the tool set smaller.",
        ),
    ] = True,
    save_suggestions: Annotated[
        bool,
        Option(
            "--save-suggestions/--no-save-suggestions",
            help="Let the agent add new word and alternative pairs to the circumlocutions "
            "database as it works. Off by default, since it writes to a file that is "
            "otherwise curated by hand.",
        ),
    ] = False,
    topic: Annotated[
        str | None,
        Option(
            "--topic",
            "-t",
            help="Generate and save a single topic answer with no user prompting."
        )
    ] = None,
    output_folder_in: Annotated[
        Path | None,
        Option(
            "--output-folder",
            "-o",
            help="Folder to save generated explanations (default: created_<model_name>).",
        ),
    ] = None,
    output_filename: Annotated[
        str | None,
        Option(
            "--output-filename",
            "-f",
            help="Filename to save the generated explanation (overrides default naming). Only" \
            " used when --topic is specified.",
        ),
    ] = None,
):
    """Generate text using Thing Explainer word list."""
    console = Console()
    try:
        agent = ThingExplainerAgent(
            provider_name=provider,
            model_name=model,
            use_example=not skip_example,
            use_circumlocutions=suggestions,
            save_circumlocutions=save_suggestions,
        )
    except CustomProviderError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise Exit(code=1)

    def event_logger(event: Any) -> None:
        if isinstance(event, PartDeltaEvent):
            return  # Too noisy, skip these
        console.print(f"\t[grey]{datetime.now()} - {type(event).__name__}[/grey]")

    if output_folder_in is None:
        output_folder = Path(__file__).parent / (
            agent.model_name.replace(".", "_").replace("/", "_").replace(":", "_")
            + "_created"
        )
    else:
        output_folder = output_folder_in.resolve()
    output_folder.mkdir(parents=True, exist_ok=True)

    console.print(
        f"\n[bold blue]Using provider:[/bold blue] '{provider}'"
    )
    console.print(f"[bold blue]Using model:[/bold blue] '{agent.model_name}'\n")

    if topic is not None:
        explanation_result = _generate_agent_explanation(agent, topic, event_logger)
        if output_filename is not None:
            output_path = output_folder / output_filename
        else:
            output_path = explanation_result.output_path(output_folder)
        output_path.write_text(explanation_result.explanation.text)
        console.print(f"[green]Saved explanation to {output_path}[/green]")
        return


    # Ask the user for a topic, or whether to quit (loop until they do)
    try:
        while True:
            # Provider and model info
            topic = console.input("\nEnter a topic to explain (or 'Ctrl+C' to exit): ")
            console.print(f"\n[bold]Generating explanation for:[/bold] {topic}\n")
            explanation_result = _generate_agent_explanation(agent, topic, event_logger)
            explanation = explanation_result.explanation
            usage = explanation_result.usage
            task_duration = explanation_result.task_duration
            console.print("\n[bold green]Generated Explanation:[/bold green]\n")
            console.print(Panel(explanation.text, title=explanation.short_title))
            console.print(
                f"\n[bold blue]Usage:[/bold blue]\tTokens: {usage.total_tokens}\n\tTool calls: {usage.tool_calls}\n"
            )
            console.print(f"[bold blue]Generation Time:[/bold blue] {task_duration}\n")
            # Query whether to save
            output_path = explanation_result.output_path(output_folder)
            save_response = console.input(
                f"\nSave explanation to [blue]{output_path}[/blue]? (y/n): "
            )
            if save_response.lower() == "y":
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(explanation.text)
                console.print(f"[green]Saved explanation to {output_path}[/green]")
    except KeyboardInterrupt:
        console.print("\n[bold red]Exiting.[/bold red]")


_DEFAULT_WORD_LIST = (
    "https://raw.githubusercontent.com/first20hours/google-10000-english/"
    "refs/heads/master/google-10000-english-no-swears.txt"
)


def _read_word_list(source: str) -> list[str]:
    """Read the word list from a file, or download it if the source is a URL."""
    if source.startswith(("http://", "https://")):
        with urlopen(source) as response:
            text = response.read().decode("utf-8")
    else:
        text = Path(source).read_text()
    return sorted({word.strip() for word in text.splitlines() if word.strip()})


def _format_duration(duration: timedelta) -> str:
    return str(timedelta(seconds=round(duration.total_seconds())))


@dataclass
class _GenerationProgress:
    """How many words are done, and how long they took.

    Words that were already on disk are left out of the count, so that the mean
    time and the time left keep to the words that really call the model.
    """

    total: int
    done: int = 0
    failed: int = 0
    elapsed: timedelta = timedelta()

    def add(self, duration: timedelta, failed: bool = False) -> None:
        self.done += 1
        self.elapsed += duration
        if failed:
            self.failed += 1

    @property
    def mean_time(self) -> timedelta | None:
        if self.done == 0:
            return None
        return self.elapsed / self.done

    @property
    def time_left(self) -> timedelta | None:
        mean = self.mean_time
        return None if mean is None else mean * (self.total - self.done)

    def panel(self, word: str) -> Panel:
        mean = self.mean_time
        time_left = self.time_left
        lines = [
            f"[bold blue]Word:[/bold blue] {word}",
            f"[bold blue]Done:[/bold blue] {self.done}/{self.total}",
            "[bold blue]Mean time:[/bold blue] "
            + ("-" if mean is None else f"{mean.total_seconds():.1f} s/word"),
            "[bold blue]Time left:[/bold blue] "
            + ("-" if time_left is None else _format_duration(time_left)),
        ]
        if self.failed:
            lines.append(f"[bold red]Failed:[/bold red] {self.failed}")
        return Panel("\n".join(lines), title="Generating")


@app.command()
def generate(
    words: Annotated[
        str,
        Option(
            "--words",
            "-w",
            help="Word list source: a file path, or a URL to download it from. "
            "One word per line.",
        ),
    ] = _DEFAULT_WORD_LIST,
    base_url: Annotated[
        str,
        Option(
            "--base-url",
            "-b",
            help="Base URL of the OpenAI style API, without the port.",
        ),
    ] = "http://localhost",
    port: Annotated[
        int,
        Option("--port", help="Port of the OpenAI style API."),
    ] = 8137,
    model: Annotated[
        str,
        Option("--model", "-m", help="Name of the model to ask."),
    ] = "tinyfacts-llama",
    output_folder_in: Annotated[
        Path | None,
        Option(
            "--output-folder",
            "-o",
            help="Folder to save the texts in (default: <model_name>_created).",
        ),
    ] = None,
) -> int:
    """Explain every word of a list with a model that already knows the word list.

    This talks straight to an OpenAI style API (a local server by default). It
    makes no use of an agent, and it does not check the answers: the model is
    expected to be fine-tuned so that it keeps to the allowed words by itself.
    Each word gets one call and one text file, named after the word. Words that
    already have a file are skipped, so a run that stops can be started again.
    """
    console = Console()
    try:
        word_list = _read_word_list(words)
    except OSError as exc:
        console.print(f"[bold red]Could not read the word list: {exc}[/bold red]")
        raise Exit(code=1)

    if output_folder_in is None:
        output_folder = Path(__file__).parent / (
            model.replace(".", "_").replace("/", "_").replace(":", "_") + "_created"
        )
    else:
        output_folder = output_folder_in.resolve()
    output_folder.mkdir(parents=True, exist_ok=True)

    pending = [
        word for word in word_list if not (output_folder / f"{word}.txt").exists()
    ]
    skipped = len(word_list) - len(pending)
    # The server is a local one that wants no key, but the client asks for one
    client = openai.OpenAI(
        base_url=f"{base_url.rstrip('/')}:{port}/v1", api_key="dummy"
    )

    console.print(f"\n[bold blue]Using model:[/bold blue] '{model}'")
    console.print(f"[bold blue]Saving into:[/bold blue] {output_folder}")
    console.print(
        f"[bold blue]Words:[/bold blue] {len(pending)} to do, {skipped} already there\n"
    )
    if not pending:
        console.print("[green]Nothing left to do.[/green]")
        return 0

    progress = _GenerationProgress(total=len(pending))
    errors: list[str] = []
    try:
        with Live(progress.panel(pending[0]), console=console) as live:
            for word in pending:
                live.update(progress.panel(word))
                start_time = datetime.now()
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "user",
                                "content": f"Explain the following word: {word}",
                            }
                        ],
                    )
                    answer = response.choices[0].message.content or ""
                except Exception as exc:  # One bad answer must not stop the run
                    errors.append(f"{word}: {exc}")
                    progress.add(datetime.now() - start_time, failed=True)
                    live.update(progress.panel(word))
                    continue
                (output_folder / f"{word}.txt").write_text(answer)
                progress.add(datetime.now() - start_time)
                live.update(progress.panel(word))
    except KeyboardInterrupt:
        console.print("\n[bold red]Stopped.[/bold red]")

    console.print(
        f"[green]Wrote {progress.done - progress.failed} file(s)[/green] in "
        f"{_format_duration(progress.elapsed)} ({skipped} skipped)."
    )
    if errors:
        console.print(f"[bold red]{len(errors)} word(s) failed:[/bold red]")
        for error in errors:
            console.print(f"\t[red]{error}[/red]")
        return 1
    return 0


_DEFAULT_EDITOR_OUTPUT_DIR = Path(__file__).parent / "manually_created"


@app.command()
def editor(
    output_dir: Annotated[
        Path,
        Option(
            "--output-dir",
            "-o",
            help="Directory to save edited files (default: manually_created)",
        ),
    ] = _DEFAULT_EDITOR_OUTPUT_DIR,
):
    """Launch the text editor to create and edit documents using the Thing Explainer word list."""
    output_dir = output_dir.resolve()
    editor = SimpleTextEditor(output_dir)
    editor.run()


@app.command()
def compile(
    output_file: Annotated[
        Path,
        Argument(help="Path of the .jsonl file to write all valid documents into."),
    ],
    folder: Annotated[
        Path,
        Option(
            "--folder",
            "-f",
            help="Folder containing text files to analyze.",
        ),
    ] = Path.cwd(),
    instruct: Annotated[
        bool,
        Option(
            "--instruct",
            "-i",
            help="Write question and answer rows instead of plain text rows. An agent "
            "suggests the user question that each text answers.",
        ),
    ] = False,
    append: Annotated[
        bool,
        Option(
            "--append",
            "-a",
            help="Keep the rows already in the output file and add only the files that "
            "are not in it yet, matched by their id.",
        ),
    ] = False,
    include: Annotated[
        str | None,
        Option(
            "--include",
            help="Regular expression. Use only the folders whose name matches it.",
        ),
    ] = None,
    exclude: Annotated[
        str | None,
        Option(
            "--exclude",
            help="Regular expression. Leave out the folders whose name matches it. "
            "It is used on the folders kept by --include, if that one is given too.",
        ),
    ] = None,
    provider: Annotated[
        str,
        Option(
            "--provider",
            "-p",
            help="The LLM provider used to suggest questions (only with --instruct).",
        ),
    ] = SupportedProviders.OPENAI.value,
    model: Annotated[
        str | None,
        Option(
            "--model",
            "-m",
            help="The model name used to suggest questions (only with --instruct).",
        ),
    ] = None,
) -> int:
    """Write all valid text files into one .jsonl file, one row per file.

    Each row holds the file id, and either {"text": ...} or, with --instruct,
    {"user": ..., "assistant": ...}. Rows are written as they are made, so a run
    that stops early can be carried on later with --append.
    """
    console = Console()
    try:
        include_re = re.compile(include) if include is not None else None
        exclude_re = re.compile(exclude) if exclude is not None else None
    except re.error as exc:
        console.print(f"[bold red]Bad regular expression: {exc}[/bold red]")
        raise Exit(code=1)

    documents: list[_CompileDocument] = []
    invalid_files: list[Path] = []
    resolved_output = output_file.resolve()
    for gen_folder in sorted(folder.glob("*_created")):
        if include_re is not None and not include_re.search(gen_folder.name):
            continue
        if exclude_re is not None and exclude_re.search(gen_folder.name):
            continue
        for text_file in sorted(gen_folder.glob("*.txt")):
            if text_file.resolve() == resolved_output:
                continue  # Never include the output file itself
            text = text_file.read_text()
            if check_words_with_context(text).invalid_words:
                invalid_files.append(text_file)
                continue
            documents.append(_CompileDocument.from_file(text_file, folder, text))
    if not documents:
        console.print("[yellow]No valid files found, nothing written.[/yellow]")
        return 1

    already_done = _read_row_ids(output_file) if append else set()
    if already_done:
        documents = [doc for doc in documents if doc.file_id not in already_done]
        console.print(
            f"[blue]{len(already_done)} row(s) already in {output_file}, "
            f"{len(documents)} file(s) left to do.[/blue]"
        )
        if not documents:
            console.print("[green]Nothing left to do.[/green]")
            return 0

    question_agent = None
    if instruct:
        try:
            question_agent = QuestionAgent(provider_name=provider, model_name=model)
        except CustomProviderError as exc:
            console.print(f"[bold red]{exc}[/bold red]")
            raise Exit(code=1)
        console.print(
            f"[bold blue]Making questions with:[/bold blue] '{provider}' / "
            f"'{question_agent.model_name}'\n"
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    written_count = 0
    failed_count = 0
    with output_file.open("a" if append else "w") as f:
        for index, document in enumerate(documents, start=1):
            if question_agent is None:
                row = {"id": document.file_id, "text": document.text}
            else:
                console.print(f"\t[grey]Question {index} of {len(documents)}...[/grey]")
                try:
                    result = asyncio.run(
                        question_agent.generate_question(document.text, document.title)
                    )
                except Exception as exc:  # One bad answer must not lose the whole run
                    console.print(f"\t[red]{document.file_id}: {exc}[/red]")
                    failed_count += 1
                    continue
                row = {
                    "id": document.file_id,
                    "user": result.question,
                    "assistant": document.text,
                }
            f.write(json.dumps(row) + "\n")
            f.flush()  # Keep the file usable if the run stops part way
            written_count += 1

    console.print(
        f"[green]Compiled {written_count} valid file(s)[/green] "
        f"({len(invalid_files)} skipped) into {output_file}."
    )
    if failed_count:
        console.print(
            f"[yellow]{failed_count} file(s) left out: no question could be made. "
            f"Run again with --append to try them.[/yellow]"
        )
    if invalid_files:
        console.print("[bold red]Skipped invalid files:[/bold red]")
        for invalid_file in invalid_files:
            console.print(f"\t[red]{invalid_file}[/red]")
    return 0


@dataclass
class _CompileDocument:
    """One valid text file, ready to be written as a row."""

    file_id: str
    title: str
    text: str

    @classmethod
    def from_file(cls, path: Path, folder: Path, text: str) -> "_CompileDocument":
        try:
            file_id = path.relative_to(folder).as_posix()
        except ValueError:
            file_id = path.name
        return cls(
            file_id=file_id,
            title=path.stem.replace("_", " "),
            text=text.strip(),
        )


def _read_row_ids(output_file: Path) -> set[str]:
    """Return the file ids already written into an output file, if it exists."""
    if not output_file.exists():
        return set()
    ids: set[str] = set()
    for line in output_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # A half written row from a run that stopped part way
        file_id = row.get("id") if isinstance(row, dict) else None
        if isinstance(file_id, str):
            ids.add(file_id)
    return ids


@app.command()
def stats(
    folder: Annotated[
        Path,
        Option(
            "--folder",
            "-f",
            help="Folder containing text files to analyze.",
        ),
    ] = Path.cwd(),
):
    """Generate statistics about text files in a folder."""
    stats = FolderGenStats(folder)
    console = Console()
    console.print(f"\n[bold]Generation Statistics for folder:[/bold] {folder}\n")
    console.print(f"Total invalid files (skipped): [red]{stats.invalid_file_count}[/red]")
    console.print(f"Total valid files: [green]{stats.file_count}[/green]")
    console.print(f"Total words across valid files: [green]{stats.word_count}[/green]")
    console.print(
        f"Unique words across valid files: [green]{stats.unique_word_count}[/green]\n"
    )

    if stats.invalid_file_count > 0:
        console.print("[bold red]Invalid files:[/bold red]")
        for invalid_file in stats.invalid_files:
            console.print(f"\t[red]{invalid_file}[/red]")


if __name__ == "__main__":
    app()
