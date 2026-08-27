"""Turning folders of generated text into dataset rows.

A file says what it is: its title, the question it answers, the model that
wrote it all come out of its own YAML block. Nothing here is told anything
about any particular folder, beyond the name it lends its rows.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ..check_words import find_invalid_words
from .config import DatasetConfig
from .documents import iter_documents, read_document
from .records import DatasetRecord, make_id


@dataclass
class IngestReport:
    """What was found while reading the folders."""

    scanned: int = 0
    invalid: list[Path] = field(default_factory=list)
    empty: list[Path] = field(default_factory=list)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid)


def _string(value: Any) -> str | None:
    """A field of a YAML block as text, or None when it says nothing."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _tags(value: Any) -> list[str]:
    """The tags of a YAML block, whether it holds one or many."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return sorted({tag.strip() for tag in value if isinstance(tag, str) and tag.strip()})


def document_to_record(path: Path, source: str) -> DatasetRecord | None:
    """Read one file and make the row for it, or None when it holds no text."""
    document = read_document(path)
    if not document.text.strip():
        return None
    metadata = document.metadata
    return DatasetRecord.build(
        id=make_id(source, document.name),
        text=document.text,
        title=document.title,
        source=source,
        model=_string(metadata.get("model")),
        provider=_string(metadata.get("provider")),
        instruction=_string(metadata.get("instruction")),
        instruction_model=_string(metadata.get("instruction_model")),
        tags=_tags(metadata.get("tags")),
    )


def iter_folder_records(
    folder: Path,
    config: DatasetConfig,
    report: IngestReport,
    allow_invalid: bool = False,
) -> Iterator[DatasetRecord]:
    """Every row a folder of generated text has to give."""
    source = config.source_for_folder(folder)
    for path in iter_documents(folder):
        report.scanned += 1
        record = document_to_record(path, source)
        if record is None:
            report.empty.append(path)
            continue
        if not allow_invalid and find_invalid_words(record.text):
            report.invalid.append(path)
            continue
        yield record


def iter_records(
    config: DatasetConfig,
    root: Path | None = None,
    include: str | None = None,
    exclude: str | None = None,
    allow_invalid: bool = False,
    report: IngestReport | None = None,
) -> Iterator[DatasetRecord]:
    """Every row from every folder of generated text.

    Args:
        config: Where the folders are.
        root: Folder the generation folders sit in. The config root by default.
        include: Only use folders whose name matches this regular expression.
        exclude: Leave out folders whose name matches this one.
        allow_invalid: Keep texts that use words outside the word list.
        report: Filled in with what was found, if given.
    """
    report = report if report is not None else IngestReport()
    include_re = re.compile(include) if include else None
    exclude_re = re.compile(exclude) if exclude else None
    for folder in config.generation_folders(root):
        if include_re is not None and not include_re.search(folder.name):
            continue
        if exclude_re is not None and exclude_re.search(folder.name):
            continue
        yield from iter_folder_records(folder, config, report, allow_invalid=allow_invalid)
