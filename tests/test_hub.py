"""Tests for the Hub sync, run against a stand-in for the Hugging Face API.

The stand-in keeps files in a dict, the way the real repo keeps them, so the
part that matters here can be checked without a token or a network: which files
are sent, which are left alone because they did not change, and how rows from
up there and rows from here are put together.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from tinyfacts.dataset import hub
from tinyfacts.dataset.config import DatasetConfig
from tinyfacts.dataset.records import DatasetRecord
from tinyfacts.dataset.store import DatasetStore


@dataclass
class _Entry:
    path: str
    blob_id: str
    lfs: None = None


class FakeApi:
    """Just enough of `HfApi` for the sync to work against."""

    def __init__(self, files: dict[str, bytes] | None = None, missing: bool = False):
        self.files = dict(files or {})
        self.missing = missing
        self.commits: list[list] = []
        self.created: list[str] = []

    def _check(self):
        if self.missing:
            raise hub.RepositoryNotFoundError("no such repo")

    def list_repo_tree(self, repo_id, repo_type, recursive=False):
        self._check()
        return [
            _Entry(path=path, blob_id=hub._git_blob_sha1(data))
            for path, data in self.files.items()
        ]

    def list_repo_files(self, repo_id, repo_type):
        self._check()
        return list(self.files)

    def hf_hub_download(self, repo_id, filename, repo_type):
        path = Path(self._cache) / filename.replace("/", "_")
        path.write_bytes(self.files[filename])
        return str(path)

    def create_repo(self, repo_id, repo_type, private, exist_ok):
        self.created.append(repo_id)
        self.missing = False

    def create_commit(self, repo_id, repo_type, operations, commit_message):
        self.commits.append(operations)
        for operation in operations:
            if isinstance(operation, hub.CommitOperationAdd):
                self.files[operation.path_in_repo] = operation.path_or_fileobj
            else:
                self.files.pop(operation.path_in_repo, None)
        return type("Commit", (), {"commit_url": "https://hf.co/commit/1"})()


@pytest.fixture
def fake(monkeypatch, tmp_path):
    api = FakeApi()
    api._cache = tmp_path / "cache"
    api._cache.mkdir()
    monkeypatch.setattr(hub, "_api", lambda token=None: api)
    return api


@pytest.fixture
def config(tmp_path) -> DatasetConfig:
    return DatasetConfig(root=tmp_path)


def store_with(tmp_path: Path, names: list[str], chunk_size: int = 2, **fields) -> DatasetStore:
    store = DatasetStore(tmp_path / "store", chunk_size=chunk_size)
    for name in names:
        store.add(
            DatasetRecord.build(
                id=f"test/{name}", text=f"Words about {name}.", title=name, source="test", **fields
            )
        )
    return store


def uploaded_names(api: FakeApi) -> list[str]:
    return [op.path_in_repo for op in api.commits[-1] if isinstance(op, hub.CommitOperationAdd)]


def test_a_first_push_sends_everything_and_makes_the_repo(fake, config, tmp_path):
    store = store_with(tmp_path, ["a", "b", "c"])
    result = hub.push(store, config, token="tok")
    assert fake.created == [config.hub.repo_id]
    assert result.uploaded == ["README.md", "data/tinyfacts-0000.jsonl", "data/tinyfacts-0001.jsonl"]
    assert result.rows == 3


def test_a_second_push_with_nothing_new_sends_nothing(fake, config, tmp_path):
    store = store_with(tmp_path, ["a", "b", "c"])
    hub.push(store, config, token="tok")
    result = hub.push(store, config, token="tok")
    assert result.is_empty
    assert len(fake.commits) == 1  # No second commit was made


def test_adding_a_row_only_sends_the_last_chunk(fake, config, tmp_path):
    store = store_with(tmp_path, ["a", "b", "c"])
    hub.push(store, config, token="tok")
    store.add(DatasetRecord.build(id="test/d", text="Words about d.", source="test"))
    result = hub.push(store, config, token="tok")
    assert "data/tinyfacts-0000.jsonl" not in result.uploaded  # It did not change
    assert "data/tinyfacts-0001.jsonl" in result.uploaded


def test_a_dry_run_sends_nothing(fake, config, tmp_path):
    store = store_with(tmp_path, ["a", "b"])
    result = hub.push(store, config, token="tok", dry_run=True)
    assert result.uploaded and result.dry_run
    assert fake.commits == [] and fake.created == []


def test_chunks_that_are_no_longer_needed_are_taken_off_the_hub(fake, config, tmp_path):
    store = store_with(tmp_path, ["a", "b", "c"])
    hub.push(store, config, token="tok")
    store.remove("test/c")
    result = hub.push(store, config, token="tok")
    assert result.deleted == ["data/tinyfacts-0001.jsonl"]
    assert "data/tinyfacts-0001.jsonl" not in fake.files


def test_pulling_puts_the_hub_rows_first(fake, config, tmp_path):
    hub.push(store_with(tmp_path / "them", ["a", "b"]), config, token="tok")
    mine = store_with(tmp_path / "me", ["c"])
    result = hub.pull(mine, config, token="tok")
    assert [row.id for row in mine] == ["test/a", "test/b", "test/c"]
    assert (result.remote_rows, result.added) == (2, 1)


def test_a_local_question_is_not_lost_when_pulling(fake, config, tmp_path):
    hub.push(store_with(tmp_path / "them", ["a"]), config, token="tok")
    mine = store_with(tmp_path / "me", ["a"], instruction="What is a?")
    hub.pull(mine, config, token="tok")
    assert mine.get("test/a").instruction == "What is a?"


def test_a_sync_brings_the_two_together_and_sends_the_result(fake, config, tmp_path):
    hub.push(store_with(tmp_path / "them", ["a", "b"]), config, token="tok")
    mine = store_with(tmp_path / "me", ["c"])
    pull_result, push_result = hub.sync(mine, config, token="tok")
    assert pull_result.added == 1
    assert push_result.rows == 3
    rows = [
        json.loads(line)
        for name, data in sorted(fake.files.items())
        if name.endswith(".jsonl")
        for line in data.decode().splitlines()
    ]
    assert [row["id"] for row in rows] == ["test/a", "test/b", "test/c"]


def test_a_sync_to_a_repo_that_is_not_there_yet_still_pushes(fake, config, tmp_path):
    fake.missing = True
    pull_result, push_result = hub.sync(store_with(tmp_path, ["a"]), config, token="tok")
    assert pull_result.missing
    assert push_result.rows == 1


def test_an_empty_dataset_is_not_pushed(fake, config, tmp_path):
    with pytest.raises(hub.HubError, match="empty"):
        hub.push(DatasetStore(tmp_path / "store"), config, token="tok")


def test_the_card_says_what_is_in_the_dataset(fake, config, tmp_path):
    store = store_with(tmp_path, ["a", "b"], instruction="What is it?")
    card = hub.dataset_card(store, config)
    assert card.startswith("---\nlicense: mit")
    assert "path: data/tinyfacts-*.jsonl" in card
    assert "Rows: **2**" in card
    assert "| `test` | 2 |" in card


def test_a_file_that_is_the_same_up_there_is_told_apart_by_its_hash(fake, config, tmp_path):
    store = store_with(tmp_path, ["a"])
    hub.push(store, config, token="tok")
    data = fake.files["data/tinyfacts-0000.jsonl"]
    assert hub._git_blob_sha1(data) != hashlib.sha256(data).hexdigest()
    assert hub._hashes(data) & {hub._git_blob_sha1(data)}
