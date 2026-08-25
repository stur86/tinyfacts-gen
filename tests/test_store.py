from pathlib import Path

import pytest

from tinyfacts.dataset.records import DatasetRecord
from tinyfacts.dataset.store import DatasetStore, StoreError


def record(name: str, **fields) -> DatasetRecord:
    fields.setdefault("title", name)
    fields.setdefault("source", "test")
    return DatasetRecord.build(id=f"test/{name}", text=f"Words about {name}.", **fields)


def test_rows_are_cut_into_chunks(tmp_path: Path):
    store = DatasetStore(tmp_path, chunk_size=2)
    store.add_many(record(name) for name in "abcde")
    written = store.save()
    assert [path.name for path in written] == [
        "tinyfacts-0000.jsonl",
        "tinyfacts-0001.jsonl",
        "tinyfacts-0002.jsonl",
    ]
    assert len(written[0].read_text().splitlines()) == 2
    assert len(written[-1].read_text().splitlines()) == 1


def test_what_is_written_is_read_back(tmp_path: Path):
    store = DatasetStore(tmp_path, chunk_size=2)
    store.add_many(record(name) for name in "abc")
    store.save()
    again = DatasetStore.open(tmp_path, chunk_size=2)
    assert [row.id for row in again] == ["test/a", "test/b", "test/c"]
    assert again.get("test/b").text == "Words about b."


def test_adding_the_same_id_again_only_fills_in_what_is_missing(tmp_path: Path):
    store = DatasetStore(tmp_path)
    store.add(record("a", model="gpt-5.1"))
    result = store.add_many([record("a", instruction="What is a?", model="other")])
    assert (result.added, result.updated) == (0, 1)
    row = store.get("test/a")
    assert row.instruction == "What is a?"
    assert row.model == "gpt-5.1"  # What was already known is kept
    assert len(store) == 1


def test_overwrite_lets_the_new_row_win(tmp_path: Path):
    store = DatasetStore(tmp_path)
    store.add(record("a", model="gpt-5.1"))
    store.add(record("a", model="other"), overwrite=True)
    assert store.get("test/a").model == "other"


def test_a_row_that_says_nothing_new_is_left_alone(tmp_path: Path):
    store = DatasetStore(tmp_path)
    store.add(record("a", model="gpt-5.1"))
    assert store.add(record("a", model="gpt-5.1")) == "unchanged"


def test_only_the_chunks_that_changed_are_written(tmp_path: Path):
    store = DatasetStore(tmp_path, chunk_size=2)
    store.add_many(record(name) for name in "abcd")
    store.save()
    first, second = store.existing_chunks()
    stamps = {path: path.stat().st_mtime_ns for path in (first, second)}
    store.add(record("e"))
    store.save()
    assert first.stat().st_mtime_ns == stamps[first]  # Untouched
    assert len(store.existing_chunks()) == 3


def test_chunks_that_are_no_longer_needed_are_taken_away(tmp_path: Path):
    store = DatasetStore(tmp_path, chunk_size=2)
    store.add_many(record(name) for name in "abcd")
    store.save()
    store.remove("test/d")
    store.remove("test/c")
    store.save()
    assert [path.name for path in store.existing_chunks()] == ["tinyfacts-0000.jsonl"]


def test_rebase_puts_the_hub_rows_first_and_keeps_the_local_ones(tmp_path: Path):
    store = DatasetStore(tmp_path)
    store.add(record("c"))
    store.add(record("a", instruction="What is a?"))
    remote = [record("a"), record("b")]
    result = store.rebase(remote)
    assert [row.id for row in store] == ["test/a", "test/b", "test/c"]
    assert store.get("test/a").instruction == "What is a?"  # The local row wins
    assert (result.added, result.updated) == (1, 1)


def test_rebase_can_let_the_hub_win(tmp_path: Path):
    store = DatasetStore(tmp_path)
    store.add(record("a", instruction="Mine"))
    store.rebase([record("a", instruction="Theirs")], prefer_local=False)
    assert store.get("test/a").instruction == "Theirs"


def test_a_broken_row_is_reported_with_its_line(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "tinyfacts-0000.jsonl").write_text(
        '{"id": "test/a", "text": "Words."}\nnot json\n'
    )
    with pytest.raises(StoreError, match="line 2"):
        DatasetStore.open(tmp_path)
