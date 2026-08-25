"""Reading and writing the text files that generations are saved as.

A generated file is either a plain `.txt` file, which is only text, or a `.md`
file that may start with a block of YAML between two `---` lines. That block
holds what is known about the text: its title, the question it answers, the
model that wrote it. Everything in it is optional.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

#: The file kinds a generation may be saved as. `.md` comes first because it is
#: the one new generations use.
DOCUMENT_SUFFIXES = (".md", ".txt")

_FENCE = "---"

#: A YAML block: a line of three dashes, some YAML, and another line of three
#: dashes, all at the very start of the file.
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Split a file into its YAML block, if it has one, and its text.

    A file with no block, or with a broken one, is treated as being all text,
    so nothing is ever lost by reading a file that was written by hand.
    """
    match = _FRONTMATTER_RE.match(raw)
    if match is None:
        return {}, raw
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}, raw
    if not isinstance(metadata, dict):
        return {}, raw
    return metadata, raw[match.end() :].lstrip("\n")


def join_frontmatter(metadata: dict[str, Any], text: str) -> str:
    """Put a YAML block and a text back together into one file."""
    text = text.strip() + "\n"
    clean = {key: value for key, value in metadata.items() if value not in (None, "", [])}
    if not clean:
        return text
    block = yaml.safe_dump(clean, sort_keys=False, allow_unicode=True).strip()
    return f"{_FENCE}\n{block}\n{_FENCE}\n\n{text}"


@dataclass
class GeneratedDocument:
    """One saved generation: where it is, what it says, what is known about it."""

    path: Path
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """The file name with no suffix. Rows are named after it."""
        return self.path.stem

    @property
    def title(self) -> str:
        """The title from the YAML block, or one made from the file name."""
        title = self.metadata.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        return self.name.replace("_", " ")


def read_document(path: Path) -> GeneratedDocument:
    """Read a `.md` or `.txt` generation from disk."""
    metadata, text = split_frontmatter(path.read_text())
    return GeneratedDocument(path=path, text=text.strip(), metadata=metadata)


def write_document(path: Path, text: str, metadata: dict[str, Any] | None = None) -> Path:
    """Write a generation, with its YAML block if there is anything to put in one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(join_frontmatter(metadata or {}, text))
    return path


def iter_documents(folder: Path) -> Iterator[Path]:
    """All generation files in a folder, in name order, `.md` and `.txt` alike."""
    paths = [p for suffix in DOCUMENT_SUFFIXES for p in folder.glob(f"*{suffix}")]
    yield from sorted(paths, key=lambda p: (p.stem, p.suffix))


def find_document(folder: Path, name: str) -> Path | None:
    """The file a generation with this name is already saved as, if any."""
    for suffix in DOCUMENT_SUFFIXES:
        candidate = folder / f"{name}{suffix}"
        if candidate.exists():
            return candidate
    return None
