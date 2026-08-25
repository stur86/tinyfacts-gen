"""The dataset itself: rows kept in a folder of .jsonl chunks.

Rows are held in the order they were added, and chunks are cut at a fixed
number of rows. This way adding new rows only changes the last chunk, so a push
to the Hub sends one small file instead of the whole dataset.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .records import DatasetRecord

_CHUNK_RE = re.compile(r"-(\d+)\.jsonl$")


class StoreError(Exception):
    """The working copy on disk is not readable."""


@dataclass
class AddResult:
    """What `add_many` did."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.added + self.updated + self.unchanged


class DatasetStore:
    """A folder of .jsonl chunks, read into memory and written back out."""

    def __init__(
        self,
        path: Path,
        chunk_size: int = 2000,
        data_dir: str = "data",
        chunk_prefix: str = "tinyfacts",
    ) -> None:
        self.path = Path(path)
        self.chunk_size = max(1, chunk_size)
        self.data_dir = data_dir
        self.chunk_prefix = chunk_prefix
        self._records: list[DatasetRecord] = []
        self._index: dict[str, int] = {}

    # Reading and writing --------------------------------------------------

    @property
    def data_path(self) -> Path:
        return self.path / self.data_dir

    @classmethod
    def open(cls, path: Path, **kwargs) -> "DatasetStore":
        """Make a store and read whatever is already on disk."""
        store = cls(path, **kwargs)
        store.load()
        return store

    def load(self) -> "DatasetStore":
        """Read every chunk in the folder, in chunk order."""
        self._records = []
        self._index = {}
        for chunk in self.existing_chunks():
            for number, line in enumerate(chunk.read_text().splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = DatasetRecord(**json.loads(line))
                except (json.JSONDecodeError, ValueError) as exc:
                    raise StoreError(f"Bad row in {chunk}, line {number}: {exc}") from exc
                self._put(record)
        return self

    def existing_chunks(self) -> list[Path]:
        """The chunk files on disk, in order."""
        if not self.data_path.is_dir():
            return []
        chunks = list(self.data_path.glob(f"{self.chunk_prefix}-*.jsonl"))
        return sorted(chunks, key=lambda p: _chunk_number(p))

    def chunk_path(self, number: int) -> Path:
        return self.data_path / f"{self.chunk_prefix}-{number:04d}.jsonl"

    def save(self) -> list[Path]:
        """Write every chunk out, and take away any chunk that is not needed.

        Returns the chunk files the dataset is now made of.
        """
        self.data_path.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for number, rows in enumerate(self._chunks()):
            path = self.chunk_path(number)
            body = "".join(row.to_json_line() + "\n" for row in rows)
            if not path.exists() or path.read_text() != body:
                path.write_text(body)
            written.append(path)
        for stale in self.existing_chunks():
            if stale not in written:
                stale.unlink()
        return written

    def _chunks(self) -> Iterator[list[DatasetRecord]]:
        if not self._records:
            return
        for start in range(0, len(self._records), self.chunk_size):
            yield self._records[start : start + self.chunk_size]

    # Rows -----------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[DatasetRecord]:
        return iter(self._records)

    def __contains__(self, record_id: object) -> bool:
        return record_id in self._index

    @property
    def records(self) -> list[DatasetRecord]:
        return list(self._records)

    def get(self, record_id: str) -> DatasetRecord | None:
        index = self._index.get(record_id)
        return None if index is None else self._records[index]

    def _put(self, record: DatasetRecord) -> None:
        self._index[record.id] = len(self._records)
        self._records.append(record)

    def add(self, record: DatasetRecord, overwrite: bool = False) -> str:
        """Put one row in.

        A row whose id is already there is merged into the one that is there, so
        nothing that is already known is lost. With `overwrite`, the new row
        wins on every field it fills in.

        Returns "added", "updated" or "unchanged".
        """
        index = self._index.get(record.id)
        if index is None:
            self._put(record)
            return "added"
        current = self._records[index]
        merged = record.merged_with(current) if overwrite else current.merged_with(record)
        merged.added_at = current.added_at
        if merged == current:
            return "unchanged"
        self._records[index] = merged
        return "updated"

    def add_many(self, records: Iterable[DatasetRecord], overwrite: bool = False) -> AddResult:
        result = AddResult()
        for record in records:
            outcome = self.add(record, overwrite=overwrite)
            setattr(result, outcome, getattr(result, outcome) + 1)
        return result

    def replace(self, record: DatasetRecord) -> None:
        """Put a row in place of the one with the same id, keeping its place."""
        index = self._index.get(record.id)
        if index is None:
            self._put(record)
        else:
            self._records[index] = record

    def remove(self, record_id: str) -> bool:
        index = self._index.get(record_id)
        if index is None:
            return False
        del self._records[index]
        self._reindex()
        return True

    def _reindex(self) -> None:
        self._index = {record.id: number for number, record in enumerate(self._records)}

    def rebase(self, base: list[DatasetRecord], prefer_local: bool = True) -> AddResult:
        """Put `base` first, then whatever this store has that `base` does not.

        This is what a pull does: the rows already on the Hub keep their order,
        so the chunks line up with the ones up there and only the last of them
        has to be sent back. Rows in both places are merged, and by default the
        local row wins wherever the two disagree.
        """
        mine = self._records
        self._records = []
        self._index = {}
        result = AddResult()
        for record in base:
            self._put(record)
        for record in mine:
            outcome = self.add(record, overwrite=prefer_local)
            setattr(result, outcome, getattr(result, outcome) + 1)
        return result

    def filter(self, predicate: Callable[[DatasetRecord], bool]) -> list[DatasetRecord]:
        return [record for record in self._records if predicate(record)]


def _chunk_number(path: Path) -> int:
    match = _CHUNK_RE.search(path.name)
    return int(match.group(1)) if match else 0


def read_jsonl_records(path: Path) -> list[DatasetRecord]:
    """Read rows from one .jsonl file."""
    records: list[DatasetRecord] = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(DatasetRecord(**json.loads(line)))
        except (json.JSONDecodeError, ValueError) as exc:
            raise StoreError(f"Bad row in {path}, line {number}: {exc}") from exc
    return records
