"""Turning folders of generated text into dataset rows."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ..check_words import check_words_with_context
from .config import DatasetConfig, SourceConfig
from .documents import iter_documents, read_document
from .records import DatasetRecord, make_id


@dataclass
class IngestReport:
    """What was found while reading the folders."""

    scanned: int = 0
    invalid: list[Path] = field(default_factory=list)
    empty: list[Path] = field(default_factory=list)
    skipped_folders: list[Path] = field(default_factory=list)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid)


def _questions_for(folder: Path, source_config: SourceConfig) -> list[str]:
    """The lines of the questions file of a folder, if it has one."""
    if not source_config.instructions_file:
        return []
    path = folder / source_config.instructions_file
    if not path.exists():
        return []
    return path.read_text().splitlines()


def _is_helper_file(path: Path, source_config: SourceConfig) -> bool:
    """True for files in a folder that are not generations themselves."""
    return path.name == source_config.instructions_file


def document_to_record(
    path: Path,
    source: str,
    source_config: SourceConfig,
    questions: list[str] | None = None,
) -> DatasetRecord | None:
    """Read one file and make the row for it, or None when it holds no text.

    What the file says about itself in its YAML block wins over what the config
    file says about the folder it is in.
    """
    document = read_document(path)
    if not document.text.strip():
        return None
    metadata = document.metadata
    title = document.title
    instruction = metadata.get("instruction")
    if not instruction:
        instruction = source_config.instruction_for(document.name, title, questions or [])
    if not metadata.get("title"):
        title = source_config.title_for(document.name, title, instruction if isinstance(instruction, str) else None)
    tags = metadata.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return DatasetRecord.build(
        id=make_id(source, document.name),
        text=document.text,
        title=title,
        source=source,
        model=metadata.get("model") or source_config.model or (None if source_config.known else source),
        provider=metadata.get("provider") or source_config.provider,
        instruction=instruction.strip() if isinstance(instruction, str) else None,
        instruction_model=metadata.get("instruction_model") or source_config.instruction_model,
        tags=sorted({*tags, *source_config.tags}),
    )


def iter_folder_records(
    folder: Path,
    config: DatasetConfig,
    report: IngestReport,
    allow_invalid: bool = False,
) -> Iterator[DatasetRecord]:
    """Every row a folder of generated text has to give."""
    source, source_config = config.source_for_folder(folder)
    if source_config.skip:
        report.skipped_folders.append(folder)
        return
    questions = _questions_for(folder, source_config)
    for path in iter_documents(folder):
        if _is_helper_file(path, source_config):
            continue
        report.scanned += 1
        record = document_to_record(path, source, source_config, questions)
        if record is None:
            report.empty.append(path)
            continue
        if not allow_invalid and check_words_with_context(record.text).invalid_words:
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
        config: Where the folders are and what is known about them.
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
