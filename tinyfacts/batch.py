import jsonlines
from pathlib import Path
from openai import OpenAI
from openai.types import Batch

def make_batch_jsonl(queries: list[dict], dest: Path):
    """
    Write a list of queries to a JSON Lines file.
    
    Args:
        queries (list[dict]): List of query dictionaries.
        dest (Path): Destination path for the JSON Lines file.
    """
    with jsonlines.open(dest, mode='w') as writer:
        for i, query in enumerate(queries):
            writer.write({
                "custom_id": f"query-{i}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": query
            })
            
def submit_batch_job(path: Path) -> Batch:
    """
    Submit a batch job using the provided path.
    
    Args:
        path (Path): Path to the batch JSON Lines file.
    """
    client = OpenAI()
    # 1. submit the file
    batch_file = client.files.create(
        file=path.open("rb"),
        purpose="batch"
    )
    # 2. submit the job
    batch_info = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={
            "description": f"Batch job from {path}"
        }
    )
    
    return batch_info


if __name__ == "__main__":
    import sys
    from tinyfacts.query import Query
    from tinyfacts.prompt import get_words
    
    q = Query(model="gpt-4.1-nano")
    requests = [q.ask_explain(w) for w in get_words()]
    make_batch_jsonl(requests, Path(sys.argv[1]) if len(sys.argv) > 1 else Path("batch.jsonl"))
