"""Keeping the dataset in step with a Hugging Face dataset repository.

A sync is a pull and then a push: the rows that are already up there come down
first and keep their order, the local rows are merged into them, and only the
chunk files that really changed go back up.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .config import DatasetConfig
from .records import DatasetRecord
from .store import DatasetStore, read_jsonl_records

try:  # The Hub is only needed by the commands that talk to it.
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi
    from huggingface_hub.errors import (
        EntryNotFoundError,
        HfHubHTTPError,
        RepositoryNotFoundError,
    )

    _IMPORT_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover - only hit without the package
    _IMPORT_ERROR = str(exc)


class HubError(Exception):
    """Something went wrong talking to the Hugging Face Hub."""


CARD_NAME = "README.md"
_CARD_MARK = "<!-- Written by `python main.py dataset push`. Changes here are lost. -->"


def _require_hub() -> None:
    if _IMPORT_ERROR is not None:
        raise HubError(
            "The huggingface_hub package is needed to talk to the Hub "
            f"({_IMPORT_ERROR}). Install it with `uv sync`."
        )


def _api(token: str | None) -> "HfApi":
    _require_hub()
    return HfApi(token=token)


def _git_blob_sha1(data: bytes) -> str:
    """The name git gives a file, so a local file can be told from a remote one."""
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _hashes(data: bytes) -> set[str]:
    return {_git_blob_sha1(data), hashlib.sha256(data).hexdigest()}


@dataclass
class RemoteFile:
    path: str
    hashes: set[str]


@dataclass
class PullResult:
    repo_id: str
    files: list[str] = field(default_factory=list)
    remote_rows: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: bool = False


@dataclass
class PushResult:
    repo_id: str
    uploaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    rows: int = 0
    dry_run: bool = False
    commit_url: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.uploaded and not self.deleted


def remote_files(config: DatasetConfig, token: str | None = None) -> dict[str, RemoteFile]:
    """Every file in the dataset repo, with something to compare it by."""
    api = _api(token)
    try:
        entries = api.list_repo_tree(
            repo_id=config.hub.repo_id, repo_type="dataset", recursive=True
        )
        files: dict[str, RemoteFile] = {}
        for entry in entries:
            blob_id = getattr(entry, "blob_id", None)
            if blob_id is None:
                continue  # A folder, not a file
            hashes = {blob_id}
            lfs = getattr(entry, "lfs", None)
            sha256 = getattr(lfs, "sha256", None) if lfs is not None else None
            if sha256:
                hashes.add(sha256)
            files[entry.path] = RemoteFile(path=entry.path, hashes=hashes)
        return files
    except (RepositoryNotFoundError, EntryNotFoundError):
        return {}
    except HfHubHTTPError as exc:
        raise HubError(f"Could not read {config.hub.repo_id}: {exc}") from exc


def download_records(config: DatasetConfig, token: str | None = None) -> tuple[list[DatasetRecord], list[str]]:
    """Bring down every row that is on the Hub, in the order they are kept in."""
    api = _api(token)
    hub = config.hub
    prefix = f"{hub.data_dir}/{hub.chunk_prefix}-"
    try:
        names = api.list_repo_files(repo_id=hub.repo_id, repo_type="dataset")
    except RepositoryNotFoundError as exc:
        raise HubError(
            f"No dataset repo called '{hub.repo_id}'. Push to it first, or check "
            f"the repo_id in dataset.yaml."
        ) from exc
    except HfHubHTTPError as exc:
        raise HubError(f"Could not read {hub.repo_id}: {exc}") from exc

    chunks = sorted(name for name in names if name.startswith(prefix) and name.endswith(".jsonl"))
    records: list[DatasetRecord] = []
    for name in chunks:
        local = api.hf_hub_download(repo_id=hub.repo_id, filename=name, repo_type="dataset")
        records.extend(read_jsonl_records(Path(local)))
    return records, chunks


def pull(
    store: DatasetStore,
    config: DatasetConfig,
    token: str | None = None,
    prefer_local: bool = True,
    save: bool = True,
) -> PullResult:
    """Put the rows from the Hub under the local ones and merge the two."""
    records, files = download_records(config, token=token)
    result = store.rebase(records, prefer_local=prefer_local)
    if save:
        store.save()
    return PullResult(
        repo_id=config.hub.repo_id,
        files=files,
        remote_rows=len(records),
        added=result.added,
        updated=result.updated,
        unchanged=result.unchanged,
    )


def dataset_card(store: DatasetStore, config: DatasetConfig) -> str:
    """The README.md that goes with the dataset on the Hub."""
    hub = config.hub
    by_source = Counter(record.source for record in store)
    by_model = Counter(record.model or "unknown" for record in store)
    with_instruction = sum(1 for record in store if record.instruction)
    words = sum(record.word_count for record in store)
    header = [
        "---",
        *([f"license: {hub.license}"] if hub.license else []),
        "language:",
        "- en",
        "task_categories:",
        "- text-generation",
        "tags:",
        "- thing-explainer",
        "- simple-english",
        "configs:",
        "- config_name: default",
        "  data_files:",
        "  - split: train",
        f"    path: {hub.data_dir}/{hub.chunk_prefix}-*.jsonl",
        "---",
    ]
    lines = [
        *header,
        "",
        "# Tinyfacts",
        "",
        _CARD_MARK,
        "",
        "Short explanations of things, written with only the 1000 most common English "
        "words (the word list from xkcd's *Up Goer Five*). Made with "
        "[tinyfacts-gen](https://github.com/stur86/tinyfacts-gen).",
        "",
        "## What is in it",
        "",
        f"- Rows: **{len(store)}**",
        f"- Words: **{words}**",
        f"- Rows with an instruction: **{with_instruction}** "
        f"({(100 * with_instruction / len(store)) if len(store) else 0:.0f}%)",
        "",
        "## Fields",
        "",
        "| Field | What it is |",
        "| --- | --- |",
        "| `id` | Row id, `<source>/<name>`. |",
        "| `text` | The explanation. |",
        "| `title` | What the text is about. |",
        "| `source` | The run or folder the text came from. |",
        "| `model` | The model that wrote the text. |",
        "| `provider` | Where that model was asked. |",
        "| `instruction` | The question the text answers, when it is known. |",
        "| `instruction_model` | The model that worked out the question, if one did. |",
        "| `tags` | Free labels. |",
        "| `word_count` | Words in the text. |",
        "| `added_at` | When the row was made. |",
        "",
        "## Sources",
        "",
        "| Source | Rows |",
        "| --- | --- |",
        *[f"| `{name}` | {count} |" for name, count in sorted(by_source.items())],
        "",
        "## Models",
        "",
        "| Model | Rows |",
        "| --- | --- |",
        *[f"| `{name}` | {count} |" for name, count in sorted(by_model.items())],
        "",
    ]
    return "\n".join(lines)


def push(
    store: DatasetStore,
    config: DatasetConfig,
    token: str | None = None,
    message: str | None = None,
    write_card: bool = True,
    dry_run: bool = False,
) -> PushResult:
    """Send every chunk that changed up to the Hub, in one commit."""
    _require_hub()
    hub = config.hub
    if not len(store):
        raise HubError("The dataset is empty, so there is nothing to push.")
    chunks = store.save()
    api = _api(token)

    if not dry_run:
        try:
            api.create_repo(
                repo_id=hub.repo_id, repo_type="dataset", private=hub.private, exist_ok=True
            )
        except HfHubHTTPError as exc:
            raise HubError(
                f"Could not make or reach the dataset repo '{hub.repo_id}': {exc}. "
                f"Check the token has write rights on it."
            ) from exc

    known = remote_files(config, token=token)
    wanted: dict[str, bytes] = {}
    for chunk in chunks:
        wanted[f"{hub.data_dir}/{chunk.name}"] = chunk.read_bytes()
    if write_card:
        card = dataset_card(store, config)
        (store.path / CARD_NAME).write_text(card)
        wanted[CARD_NAME] = card.encode()

    operations = []
    uploaded: list[str] = []
    for path, data in sorted(wanted.items()):
        remote = known.get(path)
        if remote is not None and remote.hashes & _hashes(data):
            continue  # The same file is already up there
        operations.append(CommitOperationAdd(path_in_repo=path, path_or_fileobj=data))
        uploaded.append(path)

    stale = [
        path
        for path in known
        if path.startswith(f"{hub.data_dir}/{hub.chunk_prefix}-")
        and path.endswith(".jsonl")
        and path not in wanted
    ]
    operations.extend(CommitOperationDelete(path_in_repo=path) for path in sorted(stale))

    result = PushResult(
        repo_id=hub.repo_id,
        uploaded=uploaded,
        deleted=sorted(stale),
        rows=len(store),
        dry_run=dry_run,
    )
    if dry_run or not operations:
        return result
    try:
        info = api.create_commit(
            repo_id=hub.repo_id,
            repo_type="dataset",
            operations=operations,
            commit_message=message or f"Update dataset ({len(store)} rows)",
        )
    except HfHubHTTPError as exc:
        raise HubError(f"Could not push to {hub.repo_id}: {exc}") from exc
    result.commit_url = getattr(info, "commit_url", None)
    return result


def sync(
    store: DatasetStore,
    config: DatasetConfig,
    token: str | None = None,
    message: str | None = None,
    prefer_local: bool = True,
    write_card: bool = True,
    dry_run: bool = False,
) -> tuple[PullResult, PushResult]:
    """Bring down what is on the Hub, merge the local rows into it, send it back."""
    try:
        pull_result = pull(store, config, token=token, prefer_local=prefer_local, save=False)
    except HubError as exc:
        if "No dataset repo" not in str(exc):
            raise
        pull_result = PullResult(repo_id=config.hub.repo_id, missing=True)
    push_result = push(
        store, config, token=token, message=message, write_card=write_card, dry_run=dry_run
    )
    return pull_result, push_result
