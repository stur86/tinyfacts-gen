"""End to end tests of the `dataset` commands, on a small make-believe repo."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tinyfacts.dataset.cli import app

runner = CliRunner()

CONFIG = """
hub:
  repo_id: someone/tinyfacts
store:
  path: .dataset
  chunk_size: 2
sources:
  words:
    model: tinyfacts-llama
    instruction_template: "Explain the following word: {title}"
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "dataset.yaml").write_text(CONFIG)
    folder = tmp_path / "words_created"
    folder.mkdir()
    (folder / "sun.txt").write_text("The sun is a big hot light.")
    (folder / "rain.txt").write_text("Rain is water that falls from the sky.")
    (folder / "wind.md").write_text(
        "---\ntitle: Wind\ninstruction: What is wind?\n---\n\nWind is air that moves.\n"
    )
    return tmp_path


def run(repo: Path, *args: str):
    result = runner.invoke(app, [*args, "--config", str(repo / "dataset.yaml")])
    assert result.exit_code in (0, 1), result.output
    return result


def test_add_then_export(repo: Path):
    result = run(repo, "add")
    assert "Added 3" in result.output
    assert (repo / ".dataset" / "data" / "tinyfacts-0000.jsonl").exists()

    out = repo / "out.jsonl"
    run(repo, "export", str(out), "--format", "instruct")
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 3
    by_id = {row["id"]: row for row in rows}
    assert by_id["words/sun"]["user"] == "Explain the following word: sun"
    assert by_id["words/wind"]["user"] == "What is wind?"  # The file said so itself
    assert by_id["words/wind"]["assistant"] == "Wind is air that moves."


def test_add_twice_changes_nothing(repo: Path):
    run(repo, "add")
    result = run(repo, "add")
    assert "Added 0" in result.output
    assert "left 3 as they were" in result.output


def test_export_can_filter(repo: Path):
    run(repo, "add")
    out = repo / "out.jsonl"
    run(repo, "export", str(out), "--title", "^(sun|rain)$")
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert sorted(row["id"] for row in rows) == ["words/rain", "words/sun"]


def test_stats_counts_rows(repo: Path):
    run(repo, "add")
    result = run(repo, "stats")
    assert "Rows: 3 of 3" in result.output
    assert "tinyfacts-llama" in result.output


def test_show_one_row(repo: Path):
    run(repo, "add")
    result = run(repo, "show", "words/wind")
    assert "What is wind?" in result.output
    result = run(repo, "show", "words/nothing")
    assert "No row with id" in result.output


def test_push_without_a_token_says_so(repo: Path, monkeypatch):
    for name in ("TINYFACTS_HF_TOKEN", "HF_TOKEN", "HUGGINGFACE_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    run(repo, "add")
    result = runner.invoke(app, ["push", "--config", str(repo / "dataset.yaml")])
    assert result.exit_code == 1
    assert "No Hugging Face token" in result.output


def test_the_repo_can_be_given_on_the_command_line(repo: Path, monkeypatch):
    """`--repo` wins over the config file, and a dry run sends nothing."""
    from tinyfacts.dataset import hub

    from .test_hub import FakeApi

    api = FakeApi()
    monkeypatch.setattr(hub, "_api", lambda token=None: api)
    monkeypatch.setenv("TINYFACTS_HF_TOKEN", "tok")
    run(repo, "add")
    result = runner.invoke(
        app,
        ["push", "--dry-run", "--repo", "other/place", "--config", str(repo / "dataset.yaml")],
    )
    assert result.exit_code == 0, result.output
    assert "other/place" in result.output
    assert "--dry-run: nothing was sent" in result.output
    assert api.commits == []


class FakeQuestionAgent:
    """Stands in for the agent that works out questions."""

    def __init__(self, provider_name=None, model_name=None):
        self.model_name = model_name or "fake-model"
        self.asked: list[str] = []

    async def generate_question(self, text, title=None):
        self.asked.append(title or text)
        return type("Result", (), {"question": f"What is {title}?"})()


def test_enrich_keeps_the_questions_it_makes(repo: Path, monkeypatch):
    from tinyfacts.dataset import cli

    made: list[FakeQuestionAgent] = []

    def build(provider_name=None, model_name=None):
        agent = FakeQuestionAgent(provider_name, model_name)
        made.append(agent)
        return agent

    monkeypatch.setattr(cli, "QuestionAgent", build)
    run(repo, "add")
    # Only 'wind' has a question of its own; the other two get one from the
    # folder's template, so there is nothing left to ask about.
    result = run(repo, "enrich")
    assert "already has an instruction" in result.output
    assert made == []

    result = run(repo, "enrich", "--overwrite", "--title", "Wind")
    assert "Wrote 1 question" in result.output
    result = run(repo, "show", "words/wind")
    assert "What is Wind?" in result.output
    assert "fake-model" in result.output


def test_enrich_can_be_asked_what_it_would_do(repo: Path, monkeypatch):
    from tinyfacts.dataset import cli

    monkeypatch.setattr(cli, "QuestionAgent", FakeQuestionAgent)
    run(repo, "add")
    result = run(repo, "enrich", "--overwrite", "--dry-run")
    assert "3 row(s) need a question" in result.output
    assert "nothing was written" in result.output
