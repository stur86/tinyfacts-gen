"""Keeping the dataset in step with a Hugging Face dataset repository.

A sync is a pull and then a push: the rows that are already up there come down
first and keep their order, the local rows are merged into them, and only the
chunk files that really changed go back up.
"""

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .config import DatasetConfig
from .documents import join_frontmatter, split_frontmatter
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


#: What the card is called on the Hub.
CARD_NAME = "README.md"

#: The file in this repository the card is written in. It is kept apart from the
#: project's own README.md, which is about the software and not the dataset.
CARD_SOURCE = "README_HF.md"

#: Where a dry run leaves the card it would have sent, for reading over first.
PREVIEW_DIR = ".preview"

#: A place in the card where a count or a table goes: {{rows}}, {{models_table}}.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


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
    #: Where a dry run left the card, so it can be read before it is sent.
    card_preview: Path | None = None

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


def _counts_table(heading: str, counts: "Counter[str]") -> str:
    """A markdown table of how many rows each name has, most first."""
    rows = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    lines = [f"| {heading} | Rows |", "| --- | ---: |"]
    lines += [f"| `{name}` | {count:,} |" for name, count in rows]
    return "\n".join(lines)


def card_values(store: DatasetStore, config: DatasetConfig) -> dict[str, str]:
    """What the card template can ask for, worked out from the rows themselves.

    Keeping these out of the card means the numbers in it are never stale: they
    are made afresh from the dataset every time it is pushed.
    """
    total = len(store)
    with_instruction = sum(1 for record in store if record.instruction)
    return {
        "repo_id": config.hub.repo_id,
        "rows": f"{total:,}",
        "words": f"{sum(record.word_count for record in store):,}",
        "with_instruction": f"{with_instruction:,}",
        "instruction_percent": f"{(100 * with_instruction / total) if total else 0:.0f}%",
        "sources": f"{len({record.source for record in store}):,}",
        "models": f"{len({record.model for record in store if record.model}):,}",
        "sources_table": _counts_table("Source", Counter(r.source for r in store)),
        "models_table": _counts_table("Written by", Counter(r.model_label for r in store)),
    }


def fill_card(body: str, values: dict[str, str]) -> str:
    """Put the numbers into the card, and say so when one is asked for by a name
    that means nothing."""
    asked = {match.group(1) for match in _PLACEHOLDER_RE.finditer(body)}
    unknown = sorted(asked - set(values))
    if unknown:
        raise HubError(
            f"{CARD_SOURCE} asks for {', '.join(unknown)}, which the dataset cannot "
            f"give. It knows: {', '.join(sorted(values))}."
        )
    return _PLACEHOLDER_RE.sub(lambda match: values[match.group(1)], body)


def dataset_card(store: DatasetStore, config: DatasetConfig) -> str:
    """The README.md that goes with the dataset on the Hub.

    The words are `README_HF.md`, written by hand: what the dataset is, what is
    in a row, what it is good for. It is a template, and anywhere it says
    `{{rows}}` or `{{models_table}}` the number or the table is put in from the
    dataset itself, so nothing in the card can fall out of step with the rows.

    The YAML block on top is made here out of the `hub` settings, because it has
    to name the chunk files exactly for the dataset viewer to find them. A block
    in `README_HF.md` is kept as well, and wins where the two say the same thing.
    """
    hub = config.hub
    path = config.root / CARD_SOURCE
    if not path.exists():
        raise HubError(
            f"No dataset card at {path}. Write one, or push with --no-card to "
            f"leave the card on the Hub alone."
        )
    written, body = split_frontmatter(path.read_text())
    metadata = {
        "license": hub.license,
        "language": ["en"],
        "task_categories": ["text-generation"],
        "tags": ["thing-explainer", "simple-english"],
        "configs": [
            {
                "config_name": "default",
                "data_files": [
                    {"split": "train", "path": f"{hub.data_dir}/{hub.chunk_prefix}-*.jsonl"}
                ],
            }
        ],
    }
    metadata.update(written)
    return join_frontmatter(metadata, fill_card(body, card_values(store, config)))


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
    card = dataset_card(store, config) if write_card else None
    if card is not None:
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
    if dry_run and card is not None:
        # Nothing is sent, so leave the card where it can be read over first.
        preview = config.root / PREVIEW_DIR / CARD_NAME
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_text(card)
        result.card_preview = preview
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
