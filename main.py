import asyncio
from rich.console import Console
from rich.panel import Panel
from pathlib import Path
from datetime import datetime
from typing import Annotated, Any
from typer import Typer, Option
from dotenv import load_dotenv
from pydantic_ai import PartDeltaEvent
from tinyfacts.check_words import main as check_main
from tinyfacts.agent import ThingExplainerAgent, SupportedProviders
from tinyfacts.text_editor import SimpleTextEditor
from tinyfacts.stats import FolderGenStats

load_dotenv()  # Load environment variables from .env file if it exists
app = Typer()


@app.command()
def check(file: Path) -> int:
    """Check if a text file only uses words from the Thing Explainer 1000 word list."""
    return check_main(file)


@app.command()
def agent(
    provider: Annotated[
        SupportedProviders,
        Option(
            "--provider",
            "-p",
            help="The LLM provider to use (openai, ollama, google).",
        ),
    ] = SupportedProviders.OPENAI,
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
):
    """Generate text using Thing Explainer word list."""
    agent = ThingExplainerAgent(provider_name=provider, model_name=model, use_example=not skip_example)
    console = Console()

    def event_logger(event: Any) -> None:
        if isinstance(event, PartDeltaEvent):
            return  # Too noisy, skip these
        console.print(f"\t[grey]{datetime.now()} - {type(event).__name__}[/grey]")
        

    # Ask the user for a topic, or whether to quit (loop until they do)
    try:
        while True:
            # Provider and model info
            console.print(f"\n[bold blue]Using provider:[/bold blue] '{provider.value}'")
            console.print(f"[bold blue]Using model:[/bold blue] '{agent.model_name}'\n")
            topic = console.input("\nEnter a topic to explain (or 'Ctrl+C' to exit): ")
            console.print(f"\n[bold]Generating explanation for:[/bold] {topic}\n")
            start_time = datetime.now()
            explanation, usage = asyncio.run(
                agent.generate_explanation(topic, event_callback=event_logger)
            )
            task_duration = datetime.now() - start_time
            console.print("\n[bold green]Generated Explanation:[/bold green]\n")
            console.print(Panel(explanation.text, title=explanation.short_title))
            console.print(
                f"\n[bold blue]Usage:[/bold blue]\tTokens: {usage.total_tokens}\n\tTool calls: {usage.tool_calls}\n"
            )
            console.print(f"[bold blue]Generation Time:[/bold blue] {task_duration}\n")
            # Query whether to save
            output_folder = (
                agent.model_name.replace(".", "_").replace("/", "_").replace(":", "_")
                + "_created"
            )
            output_path = (
                Path(__file__).parent
                / output_folder
                / f"{explanation.short_title.lower().replace(' ', '_')}.txt"
            )
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
    console.print(f"Total valid files: [green]{stats.file_count}[/green]")
    console.print(f"Total words across valid files: [green]{stats.word_count}[/green]")
    console.print(f"Unique words across valid files: [green]{stats.unique_word_count}[/green]\n")


if __name__ == "__main__":
    app()
