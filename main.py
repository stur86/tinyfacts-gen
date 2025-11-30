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
from tinyfacts.agent import ThingExplainerAgent

load_dotenv()  # Load environment variables from .env file if it exists
app = Typer()

@app.command()
def check(file: Path) -> int:
    """Check if a text file only uses words from the Thing Explainer 1000 word list."""
    return check_main(file)

@app.command()
def agent(ollama: Annotated[bool, Option("--ollama", "-o", help="Use local Ollama model instead of OpenAI.")] = False, 
                model: Annotated[str | None, Option("--model", "-m", help="The model name to use for generation.")] = None):
    """Generate text using Thing Explainer word list."""
    agent = ThingExplainerAgent(use_ollama=ollama, model_name=model)
    console = Console()
    
    def event_logger(event: Any) -> None:
        if isinstance(event, PartDeltaEvent):
            return # Too noisy, skip these
        console.print(f"\t[grey]{datetime.now()} - {type(event).__name__}[/grey]")
    
    # Ask the user for a topic, or whether to quit (loop until they do)
    try:
        while True:
            topic = console.input("\nEnter a topic to explain (or 'Ctrl+C' to exit): ")
            console.print(f"\n[bold]Generating explanation for:[/bold] {topic}\n")
            explanation, usage = asyncio.run(agent.generate_explanation(topic, event_callback=event_logger))
            console.print("\n[bold green]Generated Explanation:[/bold green]\n")
            console.print(Panel(explanation.text, title=explanation.short_title))
            console.print(f"\n[bold blue]Usage:[/bold blue]\tTokens: {usage.total_tokens}\n\tTool calls: {usage.tool_calls}\n")
            # Query whether to save
            output_folder = agent.model_name.replace(".", "_").replace("/", "_").replace(":", "_") + "_created"
            output_path = Path(__file__).parent / output_folder / f"{explanation.short_title.lower().replace(' ', '_')}.txt"
            save_response = console.input(f"\nSave explanation to [blue]{output_path}[/blue]? (y/n): ")
            if save_response.lower() == 'y':
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(explanation.text)
                console.print(f"[green]Saved explanation to {output_path}[/green]")
    except KeyboardInterrupt:
        console.print("\n[bold red]Exiting.[/bold red]")

if __name__ == "__main__":
    app()
