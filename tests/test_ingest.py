from pathlib import Path

import pytest

from tinyfacts.dataset.config import DatasetConfig
from tinyfacts.dataset.documents import write_document
from tinyfacts.dataset.ingest import IngestReport, iter_records

CONFIG = """
hub:
  repo_id: someone/tinyfacts
store:
  path: .dataset
  chunk_size: 3
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "dataset.yaml").write_text(CONFIG)
    words = tmp_path / "words_created"
    words.mkdir()
    write_document(
        words / "sun.md",
        "The sun is a big hot light.",
        {
            "title": "sun",
            "instruction": "Explain the following word: sun",
            "model": "tinyfacts-llama",
            "provider": "local",
            "tags": ["word-explanation"],
        },
    )
    hand = tmp_path / "hand_created"
    hand.mkdir()
    write_document(
        hand / "stars.md",
        "Stars are far away.",
        {"title": "Stars", "instruction": "What is a star?", "model": "me", "tags": "night"},
    )
    plain = tmp_path / "plain_created"
    plain.mkdir()
    (plain / "wind.txt").write_text("Wind is air that moves.")
    return tmp_path


def records_of(repo: Path, **kwargs):
    config = DatasetConfig.load(repo / "dataset.yaml")
    report = IngestReport()
    rows = {row.id: row for row in iter_records(config, report=report, **kwargs)}
    return rows, report


def test_a_row_is_built_out_of_the_yaml_block(repo: Path):
    rows, _ = records_of(repo)
    row = rows["words/sun"]
    assert row.model == "tinyfacts-llama"
    assert row.provider == "local"
    assert row.instruction == "Explain the following word: sun"
    assert row.tags == ["word-explanation"]
    assert row.word_count == 7


def test_the_folder_name_gives_the_source(repo: Path):
    rows, _ = records_of(repo)
    assert rows["hand/stars"].source == "hand"
    assert rows["hand/stars"].title == "Stars"
    assert rows["hand/stars"].tags == ["night"]  # One tag needs no list


def test_a_file_with_no_block_still_makes_a_row(repo: Path):
    """Its title comes from its name, and it knows nothing else about itself."""
    rows, _ = records_of(repo)
    row = rows["plain/wind"]
    assert row.title == "wind"
    assert row.model is None
    assert row.provider is None
    assert row.instruction is None


def test_texts_with_words_outside_the_list_are_left_out(repo: Path):
    bad = repo / "words_created" / "cat.md"
    write_document(bad, "A cat is a small feline quadruped.", {"title": "cat"})
    rows, report = records_of(repo)
    assert "words/cat" not in rows
    assert bad in report.invalid
    rows, _ = records_of(repo, allow_invalid=True)
    assert "words/cat" in rows


def test_folders_can_be_picked_out_by_name(repo: Path):
    rows, _ = records_of(repo, include="^words")
    assert set(rows) == {"words/sun"}
    rows, _ = records_of(repo, exclude="^(words|plain)")
    assert set(rows) == {"hand/stars"}


def test_a_file_with_no_text_gives_no_row(repo: Path):
    empty = repo / "words_created" / "nothing.md"
    write_document(empty, "   ", {"title": "nothing"})
    rows, report = records_of(repo)
    assert "words/nothing" not in rows
    assert empty in report.empty
