import sys
from pathlib import Path
from datetime import datetime
from typer import Typer
from rich.console import Console
from rich.prompt import Confirm
from tinyfacts.prompt import get_words
from tinyfacts.query import Query
from tinyfacts.batch import make_batch_jsonl, submit_batch_job
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file if it exists
app = Typer()

@app.command()
def submit_batch(model: str = "gpt-5-nano", task: str = "explain",):
    console = Console()
    console.print(f"[bold green]Starting TinyFacts with model: {model}[/bold green]")
    
    words = get_words()    
    query = Query(model=model)
    
    method = f"ask_{task}"
    if not hasattr(query, method):
        console.print(f"[bold red]Error:[/bold red] Method '{method}' does not exist in Query class.")
        sys.exit(1)
    queries = [getattr(query, method)(word) for word in words]
    batch_dest = Path(f"batch_{task}_{model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
    make_batch_jsonl(queries, batch_dest)
    
    # Ask for confirmation from the user before submitting
    ans = Confirm.ask(f"Batch job with {len(queries)} queries created at {batch_dest} for model {model}. Do you want to submit this batch job?", default=False)
    if ans:
        batch_info = submit_batch_job(batch_dest)
        batch_dest.with_suffix(".out.jsonl").write_text(batch_info.model_dump_json(indent=2))

if __name__ == "__main__":
    app()
