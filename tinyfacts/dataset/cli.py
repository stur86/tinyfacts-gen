"""The `dataset` commands: gather rows, fill them in, send them to the Hub."""

import asyncio
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any, Iterable

from rich.console import Console
from rich.table import Table
from typer import Argument, Exit, Option, Typer

from ..agent import SupportedProviders
from ..custom_providers import CustomProviderError
from ..question_agent import QuestionAgent
from .config import ConfigError, DatasetConfig, resolve_token
from .filters import FilterError, RecordFilter
from .hub import HubError, pull as hub_pull, push as hub_push, sync as hub_sync
from .ingest import IngestReport, iter_records
from .records import DatasetRecord
from .store import DatasetStore, StoreError

app = Typer(help="Build, filter and sync the dataset of generated texts.")

# Options that several commands share ------------------------------------------

ConfigOpt = Annotated[
    Path | None,
    Option("--config", "-c", help="Config file to use (default: dataset.yaml)."),
]
RepoOpt = Annotated[
    str | None,
    Option("--repo", "-r", help="Hugging Face dataset repo, e.g. 'user/tinyfacts'."),
]
TokenOpt = Annotated[
    str | None,
    Option(
        "--token",
        "-t",
        help="Hugging Face token with write rights. Taken from TINYFACTS_HF_TOKEN, "
        "HF_TOKEN or HUGGINGFACE_TOKEN when it is not given.",
    ),
]
IdOpt = Annotated[str | None, Option("--id", help="Keep rows whose id matches this regular expression.")]
TitleOpt = Annotated[str | None, Option("--title", help="Keep rows whose title matches this regular expression.")]
TextOpt = Annotated[str | None, Option("--text", help="Keep rows whose text matches this regular expression.")]
InstructionOpt = Annotated[
    str | None,
    Option("--instruction", help="Keep rows whose instruction matches this regular expression."),
]
SourceOpt = Annotated[
    list[str] | None, Option("--source", "-s", help="Keep rows from these sources (may be repeated).")
]
ModelOpt = Annotated[
    list[str] | None, Option("--model", "-m", help="Keep rows from these models (may be repeated).")
]
TagOpt = Annotated[list[str] | None, Option("--tag", help="Keep rows with any of these tags.")]
HasInstructionOpt = Annotated[
    bool | None,
    Option(
        "--with-instruction/--without-instruction",
        help="Keep only rows that do, or do not, have an instruction.",
    ),
]
MinWordsOpt = Annotated[int | None, Option("--min-words", help="Keep rows with at least this many words.")]
MaxWordsOpt = Annotated[int | None, Option("--max-words", help="Keep rows with at most this many words.")]


def _load(config_path: Path | None, repo: str | None = None) -> tuple[DatasetConfig, DatasetStore]:
    """Read the config file and open the working copy."""
    console = Console()
    try:
        config = DatasetConfig.load(config_path)
    except ConfigError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise Exit(code=1)
    if repo:
        config.hub.repo_id = repo
    try:
        store = DatasetStore.open(
            config.store_path,
            chunk_size=config.store.chunk_size,
            data_dir=config.hub.data_dir,
            chunk_prefix=config.hub.chunk_prefix,
        )
    except StoreError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise Exit(code=1)
    return config, store


def _make_filter(**kwargs) -> RecordFilter:
    try:
        return RecordFilter.build(**kwargs)
    except FilterError as exc:
        Console().print(f"[bold red]{exc}[/bold red]")
        raise Exit(code=1)


# Commands ---------------------------------------------------------------------


@app.command()
def add(
    folder: Annotated[
        Path | None,
        Option("--folder", "-f", help="Folder the '*_created' folders sit in (default: the repo)."),
    ] = None,
    include: Annotated[
        str | None, Option("--include", help="Only use folders whose name matches this.")
    ] = None,
    exclude: Annotated[
        str | None, Option("--exclude", help="Leave out folders whose name matches this.")
    ] = None,
    overwrite: Annotated[
        bool,
        Option("--overwrite", help="Let the files on disk win over what the dataset already says."),
    ] = False,
    allow_invalid: Annotated[
        bool, Option("--allow-invalid", help="Keep texts that use words outside the word list.")
    ] = False,
    dry_run: Annotated[bool, Option("--dry-run", help="Say what would happen and write nothing.")] = False,
    config_path: ConfigOpt = None,
) -> int:
    """Read the folders of generated text and put what is new into the dataset.

    Files are matched by id, so running this again only adds what is not in the
    dataset yet. What a `.md` file says about itself in its YAML block wins over
    what dataset.yaml says about the folder it is in.
    """
    console = Console()
    config, store = _load(config_path)
    report = IngestReport()
    before = len(store)
    try:
        records = list(
            iter_records(
                config,
                root=folder.resolve() if folder else None,
                include=include,
                exclude=exclude,
                allow_invalid=allow_invalid,
                report=report,
            )
        )
    except Exception as exc:  # A bad regular expression, or a file that will not read
        console.print(f"[bold red]{exc}[/bold red]")
        raise Exit(code=1)

    result = store.add_many(records, overwrite=overwrite)
    console.print(
        f"\nRead [bold]{report.scanned}[/bold] file(s) from "
        f"{len(config.generation_folders(folder.resolve() if folder else None))} folder(s)."
    )
    console.print(
        f"[green]Added {result.added}[/green], [blue]changed {result.updated}[/blue], "
        f"left {result.unchanged} as they were."
    )
    if report.invalid:
        console.print(f"[yellow]{report.invalid_count} file(s) left out: words outside the list.[/yellow]")
    if report.empty:
        console.print(f"[yellow]{len(report.empty)} file(s) left out: no text in them.[/yellow]")
    if dry_run:
        console.print("[yellow]--dry-run: nothing was written.[/yellow]")
        return 0
    chunks = store.save()
    console.print(
        f"The dataset now holds [bold]{len(store)}[/bold] row(s) "
        f"(was {before}) in {len(chunks)} chunk(s) under {config.store_path}.\n"
    )
    return 0


@app.command()
def enrich(
    provider: Annotated[
        str, Option("--provider", "-p", help="The LLM provider used to suggest questions.")
    ] = SupportedProviders.OPENAI.value,
    model_name: Annotated[
        str | None, Option("--question-model", help="The model used to suggest questions.")
    ] = None,
    limit: Annotated[int | None, Option("--limit", "-n", help="Stop after this many rows.")] = None,
    overwrite: Annotated[
        bool, Option("--overwrite", help="Make a new question even for rows that have one.")
    ] = False,
    dry_run: Annotated[bool, Option("--dry-run", help="Say how many rows would be worked on.")] = False,
    id: IdOpt = None,
    title: TitleOpt = None,
    text: TextOpt = None,
    instruction: InstructionOpt = None,
    source: SourceOpt = None,
    model: ModelOpt = None,
    tag: TagOpt = None,
    min_words: MinWordsOpt = None,
    max_words: MaxWordsOpt = None,
    config_path: ConfigOpt = None,
) -> int:
    """Work out the question that rows without one answer, and keep it in the dataset.

    Rows are saved as they are made, so a run that stops part way loses nothing
    and can simply be started again.
    """
    console = Console()
    config, store = _load(config_path)
    record_filter = _make_filter(
        id=id,
        title=title,
        text=text,
        instruction=instruction,
        source=source,
        model=model,
        tag=tag,
        has_instruction=None if overwrite else False,
        min_words=min_words,
        max_words=max_words,
    )
    todo = record_filter.apply(store)
    if limit is not None:
        todo = todo[:limit]
    if not todo:
        console.print("[green]Every row that was asked for already has an instruction.[/green]")
        return 0
    console.print(f"\n[bold]{len(todo)}[/bold] row(s) need a question.")
    if dry_run:
        console.print("[yellow]--dry-run: nothing was written.[/yellow]")
        return 0

    try:
        agent = QuestionAgent(provider_name=provider, model_name=model_name)
    except CustomProviderError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise Exit(code=1)
    console.print(f"[bold blue]Asking:[/bold blue] '{provider}' / '{agent.model_name}'\n")

    done = 0
    failed: list[str] = []
    try:
        for index, record in enumerate(todo, start=1):
            console.print(f"\t[grey]{index} of {len(todo)}: {record.id}[/grey]")
            try:
                result = asyncio.run(agent.generate_question(record.text, record.title))
            except Exception as exc:  # One bad answer must not lose the whole run
                console.print(f"\t[red]{record.id}: {exc}[/red]")
                failed.append(record.id)
                continue
            record.instruction = result.question
            record.instruction_model = agent.model_name
            store.replace(record)
            done += 1
            if done % 20 == 0:
                store.save()
    except KeyboardInterrupt:
        console.print("\n[bold red]Stopped.[/bold red]")
    store.save()

    console.print(f"\n[green]Wrote {done} question(s)[/green] into {config.store_path}.")
    if failed:
        console.print(f"[yellow]{len(failed)} row(s) failed. Run again to try them.[/yellow]")
    return 0


_FORMATS = ("text", "instruct", "chat", "full")


@app.command()
def export(
    output_file: Annotated[
        Path,
        Argument(help="The .jsonl file to write, or '-' to write to the screen."),
    ],
    format: Annotated[
        str, Option("--format", help=f"How to write each row: {', '.join(_FORMATS)}.")
    ] = "text",
    limit: Annotated[int | None, Option("--limit", "-n", help="Write at most this many rows.")] = None,
    id: IdOpt = None,
    title: TitleOpt = None,
    text: TextOpt = None,
    instruction: InstructionOpt = None,
    source: SourceOpt = None,
    model: ModelOpt = None,
    tag: TagOpt = None,
    has_instruction: HasInstructionOpt = None,
    min_words: MinWordsOpt = None,
    max_words: MaxWordsOpt = None,
    config_path: ConfigOpt = None,
) -> int:
    """Write the rows that match the filters into a .jsonl file.

    Instructions are the ones kept in the dataset: nothing is asked of a model
    here. Use `dataset enrich` first to fill in the rows that have none.
    """
    console = Console()
    if format not in _FORMATS:
        console.print(f"[bold red]Unknown format '{format}'. Use one of: {', '.join(_FORMATS)}.[/bold red]")
        raise Exit(code=1)
    _, store = _load(config_path)
    if format in ("instruct", "chat") and has_instruction is None:
        has_instruction = True  # Those rows are of no use without a question
    record_filter = _make_filter(
        id=id,
        title=title,
        text=text,
        instruction=instruction,
        source=source,
        model=model,
        tag=tag,
        has_instruction=has_instruction,
        min_words=min_words,
        max_words=max_words,
    )
    rows = record_filter.apply(store)
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        console.print("[yellow]No row matches, nothing written.[/yellow]")
        _note_missing_instructions(console, store, record_filter, format)
        return 1
    _note_missing_instructions(console, store, record_filter, format)

    lines = [json.dumps(_as_row(record, format)) for record in rows]
    body = "\n".join(lines) + "\n"
    if str(output_file) == "-":
        print(body, end="")
        return 0
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(body)
    console.print(
        f"[green]Wrote {len(rows)} row(s)[/green] of {len(store)} into {output_file} "
        f"as '{format}'."
    )
    return 0


def _note_missing_instructions(
    console: Console, store: DatasetStore, record_filter: RecordFilter, format: str
) -> None:
    """Say how many rows a format that needs a question had to leave out."""
    if format not in ("instruct", "chat") or record_filter.has_instruction is not True:
        return
    without = replace(record_filter, has_instruction=False, instruction_pattern=None)
    left_out = len(without.apply(store))
    if left_out:
        console.print(
            f"[yellow]{left_out} row(s) that match were left out: they have no "
            f"instruction yet. Use `dataset enrich` to make one.[/yellow]"
        )


def _as_row(record: DatasetRecord, format: str) -> dict[str, Any]:
    if format == "full":
        return json.loads(record.to_json_line())
    if format == "instruct":
        return {"id": record.id, "user": record.instruction, "assistant": record.text}
    if format == "chat":
        return {
            "id": record.id,
            "messages": [
                {"role": "user", "content": record.instruction},
                {"role": "assistant", "content": record.text},
            ],
        }
    return {"id": record.id, "text": record.text}


@app.command()
def stats(
    id: IdOpt = None,
    title: TitleOpt = None,
    text: TextOpt = None,
    instruction: InstructionOpt = None,
    source: SourceOpt = None,
    model: ModelOpt = None,
    tag: TagOpt = None,
    has_instruction: HasInstructionOpt = None,
    min_words: MinWordsOpt = None,
    max_words: MaxWordsOpt = None,
    config_path: ConfigOpt = None,
) -> int:
    """Count what is in the dataset, by source and by model."""
    console = Console()
    config, store = _load(config_path)
    record_filter = _make_filter(
        id=id,
        title=title,
        text=text,
        instruction=instruction,
        source=source,
        model=model,
        tag=tag,
        has_instruction=has_instruction,
        min_words=min_words,
        max_words=max_words,
    )
    rows = record_filter.apply(store)
    console.print(f"\n[bold]Dataset:[/bold] {config.store_path}  →  {config.hub.repo_id}")
    if not rows:
        console.print("[yellow]No row matches.[/yellow]\n")
        return 1
    words = sum(record.word_count for record in rows)
    with_instruction = sum(1 for record in rows if record.instruction)
    console.print(
        f"Rows: [green]{len(rows)}[/green] of {len(store)}   "
        f"Words: [green]{words}[/green]   "
        f"With an instruction: [green]{with_instruction}[/green] "
        f"({100 * with_instruction / len(rows):.0f}%)\n"
    )
    console.print(_counts_table(rows, "Source", lambda r: r.source))
    console.print(_counts_table(rows, "Model", lambda r: r.model or "unknown"))
    console.print()
    return 0


def _counts_table(rows: Iterable[DatasetRecord], name: str, key) -> Table:
    counts: Counter[str] = Counter(key(record) for record in rows)
    with_instruction: Counter[str] = Counter(key(r) for r in rows if r.instruction)
    table = Table(title=None)
    table.add_column(name)
    table.add_column("Rows", justify="right")
    table.add_column("With instruction", justify="right")
    for value, count in sorted(counts.items()):
        table.add_row(value, str(count), str(with_instruction.get(value, 0)))
    return table


@app.command()
def show(
    record_id: Annotated[str, Argument(help="The id of the row to show.")],
    config_path: ConfigOpt = None,
) -> int:
    """Print one row of the dataset."""
    console = Console()
    _, store = _load(config_path)
    record = store.get(record_id)
    if record is None:
        console.print(f"[bold red]No row with id '{record_id}'.[/bold red]")
        return 1
    console.print_json(record.to_json_line())
    return 0


@app.command()
def pull(
    prefer_remote: Annotated[
        bool,
        Option("--prefer-remote", help="Let the rows on the Hub win where the two disagree."),
    ] = False,
    repo: RepoOpt = None,
    token: TokenOpt = None,
    config_path: ConfigOpt = None,
) -> int:
    """Bring the dataset down from the Hugging Face Hub into the working copy."""
    console = Console()
    config, store = _load(config_path, repo)
    console.print(f"\n[bold blue]Pulling from:[/bold blue] {config.hub.repo_id}")
    try:
        result = hub_pull(store, config, token=resolve_token(token), prefer_local=not prefer_remote)
    except HubError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise Exit(code=1)
    console.print(
        f"Took down [bold]{result.remote_rows}[/bold] row(s) in {len(result.files)} chunk(s)."
    )
    console.print(
        f"[green]{result.added} row(s) were only here[/green], "
        f"[blue]{result.updated} changed[/blue], {result.unchanged} were the same."
    )
    console.print(f"The working copy holds [bold]{len(store)}[/bold] row(s).\n")
    return 0


@app.command()
def push(
    message: Annotated[str | None, Option("--message", "-M", help="Commit message.")] = None,
    card: Annotated[
        bool, Option("--card/--no-card", help="Write the dataset card (README.md) as well.")
    ] = True,
    dry_run: Annotated[
        bool, Option("--dry-run", help="Say which files would be sent, and send nothing.")
    ] = False,
    repo: RepoOpt = None,
    token: TokenOpt = None,
    config_path: ConfigOpt = None,
) -> int:
    """Send the working copy up to the Hugging Face Hub.

    Only the chunks that really changed are sent. This does not look at what is
    on the Hub first, so use `dataset sync` when others may have added rows.
    """
    console = Console()
    config, store = _load(config_path, repo)
    hf_token = resolve_token(token)
    if hf_token is None and not dry_run:
        console.print(
            "[bold red]No Hugging Face token. Use --token, or set TINYFACTS_HF_TOKEN, "
            "HF_TOKEN or HUGGINGFACE_TOKEN.[/bold red]"
        )
        raise Exit(code=1)
    console.print(f"\n[bold blue]Pushing to:[/bold blue] {config.hub.repo_id}")
    try:
        result = hub_push(
            store, config, token=hf_token, message=message, write_card=card, dry_run=dry_run
        )
    except HubError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise Exit(code=1)
    _report_push(console, result)
    return 0


@app.command()
def sync(
    message: Annotated[str | None, Option("--message", "-M", help="Commit message.")] = None,
    prefer_remote: Annotated[
        bool, Option("--prefer-remote", help="Let the rows on the Hub win where the two disagree.")
    ] = False,
    card: Annotated[
        bool, Option("--card/--no-card", help="Write the dataset card (README.md) as well.")
    ] = True,
    dry_run: Annotated[
        bool, Option("--dry-run", help="Pull, then say what would be sent back, and send nothing.")
    ] = False,
    repo: RepoOpt = None,
    token: TokenOpt = None,
    config_path: ConfigOpt = None,
) -> int:
    """Pull the dataset, merge the local rows into it, and push it back."""
    console = Console()
    config, store = _load(config_path, repo)
    hf_token = resolve_token(token)
    if hf_token is None and not dry_run:
        console.print(
            "[bold red]No Hugging Face token. Use --token, or set TINYFACTS_HF_TOKEN, "
            "HF_TOKEN or HUGGINGFACE_TOKEN.[/bold red]"
        )
        raise Exit(code=1)
    console.print(f"\n[bold blue]Syncing with:[/bold blue] {config.hub.repo_id}")
    try:
        pull_result, push_result = hub_sync(
            store,
            config,
            token=hf_token,
            message=message,
            prefer_local=not prefer_remote,
            write_card=card,
            dry_run=dry_run,
        )
    except HubError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise Exit(code=1)
    if pull_result.missing:
        console.print("[yellow]Nothing up there yet: this will be the first push.[/yellow]")
    else:
        console.print(
            f"Took down [bold]{pull_result.remote_rows}[/bold] row(s); "
            f"[green]{pull_result.added} were only here[/green], "
            f"[blue]{pull_result.updated} changed[/blue]."
        )
    _report_push(console, push_result)
    return 0


def _report_push(console: Console, result) -> None:
    if result.is_empty:
        console.print("[green]The Hub is already up to date.[/green]\n")
        return
    what = "Would send" if result.dry_run else "Sent"
    console.print(f"[green]{what} {len(result.uploaded)} file(s):[/green]")
    for name in result.uploaded:
        console.print(f"\t{name}")
    if result.deleted:
        console.print(f"[yellow]{what.lower()} away {len(result.deleted)} old chunk(s).[/yellow]")
    if result.dry_run:
        console.print("[yellow]--dry-run: nothing was sent.[/yellow]\n")
        return
    console.print(f"The dataset on the Hub now holds [bold]{result.rows}[/bold] row(s).")
    if result.commit_url:
        console.print(f"{result.commit_url}\n")
    else:
        console.print()
