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
sources:
  words:
    model: tinyfacts-llama
    provider: local
    instruction_template: "Explain the following word: {title}"
    tags: [word-explanation]
  answers:
    model: some-model
    instructions_file: questions.q
    instructions_name_pattern: "answer_(\\\\d+)"
    title_template: "{instruction}"
  hand:
    provider: human
  old:
    skip: true
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "dataset.yaml").write_text(CONFIG)
    (tmp_path / "words_created").mkdir()
    (tmp_path / "words_created" / "sun.txt").write_text("The sun is a big hot light.")
    answers = tmp_path / "answers_created"
    answers.mkdir()
    (answers / "questions.q").write_text("What is the sun?\nWhat is rain?\n")
    (answers / "answer_1.txt").write_text("Rain is water that falls.")
    hand = tmp_path / "hand_created"
    hand.mkdir()
    write_document(
        hand / "stars.md",
        "Stars are far away.",
        {"title": "Stars", "instruction": "What is a star?", "model": "me", "tags": ["night"]},
    )
    (tmp_path / "old_created").mkdir()
    (tmp_path / "old_created" / "bad.txt").write_text("Old stuff.")
    return tmp_path


def records_of(repo: Path, **kwargs):
    config = DatasetConfig.load(repo / "dataset.yaml")
    report = IngestReport()
    rows = {row.id: row for row in iter_records(config, report=report, **kwargs)}
    return rows, report


def test_a_folder_gives_its_model_and_question_to_its_rows(repo: Path):
    rows, _ = records_of(repo)
    row = rows["words/sun"]
    assert row.model == "tinyfacts-llama"
    assert row.provider == "local"
    assert row.instruction == "Explain the following word: sun"
    assert row.tags == ["word-explanation"]
    assert row.word_count == 7


def test_a_numbered_answer_is_matched_to_its_question(repo: Path):
    rows, _ = records_of(repo)
    row = rows["answers/answer_1"]
    assert row.instruction == "What is rain?"
    assert row.title == "What is rain?"


def test_what_a_file_says_about_itself_wins(repo: Path):
    rows, _ = records_of(repo)
    row = rows["hand/stars"]
    assert row.model == "me"  # The config file says nothing about the model
    assert row.provider == "human"
    assert row.instruction == "What is a star?"
    assert row.tags == ["night"]


def test_a_skipped_folder_gives_nothing(repo: Path):
    rows, report = records_of(repo)
    assert not any(row_id.startswith("old/") for row_id in rows)
    assert repo / "old_created" in report.skipped_folders


def test_texts_with_words_outside_the_list_are_left_out(repo: Path):
    bad = repo / "words_created" / "cat.txt"
    bad.write_text("A cat is a small feline quadruped.")
    rows, report = records_of(repo)
    assert "words/cat" not in rows
    assert bad in report.invalid
    rows, _ = records_of(repo, allow_invalid=True)
    assert "words/cat" in rows


def test_folders_can_be_picked_out_by_name(repo: Path):
    rows, _ = records_of(repo, include="^words")
    assert set(rows) == {"words/sun"}
    rows, _ = records_of(repo, exclude="^(words|answers)")
    assert set(rows) == {"hand/stars"}


def test_a_folder_nobody_named_still_works(repo: Path):
    other = repo / "mystery-model_created"
    other.mkdir()
    (other / "wind.txt").write_text("Wind is air that moves.")
    rows, _ = records_of(repo)
    row = rows["mystery-model/wind"]
    assert row.model == "mystery-model"
    assert row.instruction is None


def test_the_questions_file_is_not_a_row_itself(repo: Path):
    rows, _ = records_of(repo)
    assert not any(row_id.endswith("questions") for row_id in rows)
