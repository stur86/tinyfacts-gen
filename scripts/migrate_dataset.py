"""One-shot: give every generated text its own YAML block.

Before this ran, what was known about a text lived in a table in `dataset.yaml`:
which model wrote each folder, and a pair of templates that worked out the
question a text answered from its file name. That table was the only copy of
that knowledge, and it had to grow a new special case for every run that named
its files a new way.

This script writes all of it into the files themselves, once, so the table can
go away. Every `.txt` under a `*_created` folder becomes a `.md` file with a
YAML block holding its title, the question it answers, the model that wrote it
and the provider it was asked through. The `answer_<n>.txt` files, which were
matched to their questions by counting lines in a separate file, are renamed
after the question they answer.

Already run on 2026-08-26 against the 10,147 files that were in the repository
then. It is kept as the record of where the first dataset's metadata came from.
Nothing imports it and it is not wired into `main.py`.

    python scripts/migrate_dataset.py            # say what would happen
    python scripts/migrate_dataset.py --apply    # do it
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyfacts.dataset.documents import join_frontmatter, split_frontmatter

REPO = Path(__file__).resolve().parent.parent

#: The longest a name made out of a question may be, before it is cut short.
MAX_NAME = 60


@dataclass
class Source:
    """What `dataset.yaml` used to say about one folder of generated text."""

    model: str | None = None
    provider: str | None = None
    tags: list[str] = field(default_factory=list)
    #: The question every text in the folder answers, with '{title}' in it.
    instruction_template: str | None = None
    #: A file of questions, one per line, that '<n>' in the file name points into.
    instructions_file: str | None = None
    instructions_name_pattern: str | None = None
    #: True when the file name says nothing, so the question makes a better name.
    name_from_instruction: bool = False


#: The table as it stood in `dataset.yaml` at commit 265eaa2, before this ran.
SOURCES: dict[str, Source] = {
    "tinyfacts-llama": Source(
        model="tinyfacts-llama",
        provider="local",
        tags=["word-explanation", "fine-tuned"],
        instruction_template="Explain the following word: {title}",
    ),
    "questions_gemini-3-flash-preview_cloud": Source(
        model="gemini-3-flash-preview:cloud",
        provider="ollama",
        tags=["word-explanation"],
        instructions_file="thing_explainer_questions.txt.q",
        instructions_name_pattern=r"answer_(\d+)",
        name_from_instruction=True,
    ),
    "gemini-3-flash-preview_cloud": Source(model="gemini-3-flash-preview:cloud", provider="ollama"),
    "gemini-2_5-flash": Source(model="gemini-2.5-flash", provider="google"),
    "gemini-2_5-pro": Source(model="gemini-2.5-pro", provider="google"),
    "gpt-5_1": Source(model="gpt-5.1", provider="openai"),
    "gpt-5-mini": Source(model="gpt-5-mini", provider="openai"),
    "gpt-oss_120b-cloud": Source(model="gpt-oss:120b-cloud", provider="ollama"),
    "nemotron-3-super_cloud": Source(model="nemotron-3-super:cloud", provider="ollama"),
    "gemma-e4b-long": Source(model="gemma-e4b-long", provider="ollama"),
    "big_pickle": Source(model="big_pickle", provider="ollama"),
    "claude_code": Source(model="claude-code", provider="anthropic"),
    "claude_sonnet_4_5": Source(model="claude-sonnet-4-5", provider="anthropic"),
    "manually": Source(model=None, provider="human", tags=["hand-written"]),
}

_UNSAFE = re.compile(r"[^a-z0-9]+")


def slugify(question: str) -> str:
    """A file name made out of a question, cut short on a word boundary."""
    slug = _UNSAFE.sub("_", question.lower()).strip("_")
    if len(slug) <= MAX_NAME:
        return slug or "question"
    cut = slug[:MAX_NAME].rsplit("_", 1)[0]
    return cut or slug[:MAX_NAME]


def _unquote(path: str) -> str:
    """Undo the quoting git puts on a path with odd characters in it.

    A few of the files have double quotes in their names, and git writes those
    as "what_\\"real\\"_means.txt". Left alone, they would match nothing.
    """
    if not (path.startswith('"') and path.endswith('"')):
        return path
    raw = path[1:-1]
    return (
        raw.encode("latin-1", "backslashreplace")
        .decode("unicode_escape")
        .encode("latin-1")
        .decode("utf-8", "replace")
    )


def added_dates() -> dict[str, str]:
    """When git first saw each generated file, in one pass over the history.

    The files carry no date of their own, so this is the closest thing to when
    each text was made. Renames are not followed, so a file that moved folders
    counts as added where it now sits. Files git has never seen get no date.
    """
    try:
        out = subprocess.run(
            [
                "git", "log", "--reverse", "--diff-filter=A", "--no-renames",
                "--format=commit %aI", "--name-only",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    dates: dict[str, str] = {}
    when = ""
    for line in out.splitlines():
        if line.startswith("commit "):
            when = line[len("commit ") :].strip()
        elif line.strip() and "_created/" in line:
            dates.setdefault(_unquote(line.strip()), when)
    return dates


def questions_of(folder: Path, source: Source) -> list[str]:
    if not source.instructions_file:
        return []
    path = folder / source.instructions_file
    return path.read_text().splitlines() if path.exists() else []


def instruction_of(name: str, title: str, source: Source, questions: list[str]) -> str | None:
    """The question a text answers, worked out the way `dataset.yaml` used to."""
    if source.instructions_name_pattern and questions:
        match = re.search(source.instructions_name_pattern, name)
        if match:
            line = int(match.group(1))
            if 0 <= line < len(questions) and questions[line].strip():
                return questions[line].strip()
        return None
    if source.instruction_template:
        return source.instruction_template.format(title=title)
    return None


@dataclass
class Move:
    """One file, and what it is about to become."""

    old: Path
    new: Path
    metadata: dict
    text: str

    @property
    def renamed(self) -> bool:
        return self.old.stem != self.new.stem


def plan_folder(folder: Path, source_name: str, dates: dict[str, str]) -> tuple[list[Move], list[Path]]:
    """Work out what every file in one folder becomes. Nothing is written."""
    source = SOURCES.get(source_name, Source())
    questions = questions_of(folder, source)
    moves: list[Move] = []
    lost: list[Path] = []
    taken: set[str] = set()
    for path in sorted(folder.glob("*.txt"), key=lambda p: p.stem):
        existing, text = split_frontmatter(path.read_text())
        if existing:
            continue  # Already been through here
        name = path.stem
        title = name.replace("_", " ")
        instruction = instruction_of(name, title, source, questions)
        if source.instructions_name_pattern and instruction is None:
            lost.append(path)  # A numbered answer whose question is gone
            continue
        if source.name_from_instruction and instruction:
            title = instruction
            name = slugify(instruction)
        unique = name
        count = 2
        while unique in taken:
            unique = f"{name}_{count}"
            count += 1
        taken.add(unique)
        relative = path.relative_to(REPO).as_posix()
        moves.append(
            Move(
                old=path,
                new=folder / f"{unique}.md",
                text=text,
                metadata={
                    "title": title,
                    "instruction": instruction,
                    "model": source.model,
                    "provider": source.provider,
                    "created_at": dates.get(relative),
                    "tags": source.tags,
                },
            )
        )
    return moves, lost


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the files. Without it, nothing changes.")
    args = parser.parse_args()

    dates = added_dates()
    folders = sorted(path for path in REPO.glob("*_created") if path.is_dir())
    total = 0
    renamed = 0
    all_lost: list[Path] = []
    clashes: list[Move] = []
    per_folder: dict[str, tuple[int, int]] = {}

    for folder in folders:
        source_name = folder.name[: -len("_created")]
        if source_name not in SOURCES:
            print(f"  ! {folder.name}: not in the table, its rows will carry no model")
        moves, lost = plan_folder(folder, source_name, dates)
        all_lost.extend(lost)
        for move in moves:
            if move.new.exists() and move.new != move.old:
                clashes.append(move)
        per_folder[folder.name] = (len(moves), sum(1 for m in moves if m.renamed))
        total += len(moves)
        renamed += sum(1 for m in moves if m.renamed)
        if args.apply and not clashes:
            for move in moves:
                move.new.write_text(join_frontmatter(move.metadata, move.text))
                if move.new != move.old:
                    move.old.unlink()

    width = max((len(name) for name in per_folder), default=0)
    for name, (count, moved) in per_folder.items():
        note = f"  ({moved} renamed)" if moved else ""
        print(f"  {name:<{width}}  {count:>5} file(s){note}")
    print(f"\n{total} file(s), {renamed} of them renamed.")
    if all_lost:
        print(f"{len(all_lost)} numbered answer(s) had no question and were left alone:")
        for path in all_lost[:10]:
            print(f"  {path.relative_to(REPO)}")
    if clashes:
        print(f"\nSTOPPED: {len(clashes)} new name(s) are already taken, e.g. {clashes[0].new.name}")
        return 1
    if not args.apply:
        print("\nNothing was written. Run again with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
