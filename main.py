import asyncio
from rich.console import Console
from rich.panel import Panel
from pathlib import Path
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
