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
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "dataset.yaml").write_text(CONFIG)
    (tmp_path / "README_HF.md").write_text("# Tinyfacts\n\n{{rows}} rows.\n")
    folder = tmp_path / "words_created"
    folder.mkdir()
    for name, text in [
        ("sun", "The sun is a big hot light."),
        ("rain", "Rain is water that falls from the sky."),
    ]:
        (folder / f"{name}.md").write_text(
            f"---\ntitle: {name}\ninstruction: 'Explain the following word: {name}'\n"
            f"model: tinyfacts-llama\n---\n\n{text}\n"
        )
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


def test_a_dry_run_leaves_the_card_where_it_can_be_read(repo: Path, monkeypatch):
    from tinyfacts.dataset import hub

    from .test_hub import FakeApi

    monkeypatch.setattr(hub, "_api", lambda token=None: FakeApi())
    run(repo, "add")
    result = runner.invoke(
        app, ["push", "--dry-run", "--config", str(repo / "dataset.yaml")]
    )
    assert result.exit_code == 0, result.output
    preview = repo / ".preview" / "README.md"
    assert preview.exists()
    assert "3 rows." in preview.read_text()  # The template, filled in
    assert ".preview" in result.output


def test_a_dry_run_with_no_card_leaves_nothing(repo: Path, monkeypatch):
    from tinyfacts.dataset import hub

    from .test_hub import FakeApi

    monkeypatch.setattr(hub, "_api", lambda token=None: FakeApi())
    run(repo, "add")
    runner.invoke(app, ["push", "--dry-run", "--no-card", "--config", str(repo / "dataset.yaml")])
    assert not (repo / ".preview").exists()


def test_push_says_when_there_is_no_card_to_send(repo: Path, monkeypatch):
    from tinyfacts.dataset import hub

    from .test_hub import FakeApi

    monkeypatch.setattr(hub, "_api", lambda token=None: FakeApi())
    monkeypatch.setenv("TINYFACTS_HF_TOKEN", "tok")
    (repo / "README_HF.md").unlink()
    run(repo, "add")
    result = runner.invoke(app, ["push", "--config", str(repo / "dataset.yaml")])
    assert result.exit_code == 1
    assert "No dataset card" in result.output
    # ...and it can be pushed anyway without one
    result = runner.invoke(app, ["push", "--no-card", "--config", str(repo / "dataset.yaml")])
    assert result.exit_code == 0, result.output


def test_remove_takes_a_row_out_once_it_is_agreed_to(repo: Path):
    run(repo, "add")
    result = runner.invoke(
        app, ["remove", "words/sun", "--config", str(repo / "dataset.yaml")], input="y\n"
    )
    assert result.exit_code == 0, result.output
    assert "Took out 1 row" in result.output
    # A sync would put it back, so the command has to say so
    assert "not `dataset sync`" in result.output
    assert run(repo, "show", "words/sun").output.count("No row with id") == 1
    assert "Rows: 2 of 2" in run(repo, "stats").output


def test_remove_leaves_everything_alone_when_it_is_not_agreed_to(repo: Path):
    run(repo, "add")
    result = runner.invoke(
        app, ["remove", "words/sun", "--config", str(repo / "dataset.yaml")], input="n\n"
    )
    assert result.exit_code == 1
    assert "Nothing was taken out" in result.output
    assert "Rows: 3 of 3" in run(repo, "stats").output


def test_remove_can_take_out_everything_a_filter_picks(repo: Path):
    run(repo, "add")
    result = run(repo, "remove", "--title", "^(sun|rain)$", "--yes")
    assert "Took out 2 row" in result.output
    assert "Rows: 1 of 1" in run(repo, "stats").output


def test_remove_with_nothing_to_go_on_takes_nothing_out(repo: Path):
    """Left to itself it would match every row, so it has to be told."""
    run(repo, "add")
    result = runner.invoke(app, ["remove", "--yes", "--config", str(repo / "dataset.yaml")])
    assert result.exit_code == 1
    assert "Say which rows to take out" in result.output
    assert "Rows: 3 of 3" in run(repo, "stats").output


def test_remove_will_not_take_ids_and_a_filter_at_once(repo: Path):
    run(repo, "add")
    result = runner.invoke(
        app,
        ["remove", "words/sun", "--source", "words", "--yes", "--config", str(repo / "dataset.yaml")],
    )
    assert result.exit_code == 1
    assert "not both" in result.output


def test_remove_says_when_an_id_is_not_there(repo: Path):
    run(repo, "add")
    result = run(repo, "remove", "words/nothing", "--yes")
    assert "No row with id 'words/nothing'" in result.output
    assert "nothing taken out" in result.output


def test_remove_can_be_asked_what_would_go(repo: Path):
    run(repo, "add")
    result = run(repo, "remove", "--source", "words", "--dry-run")
    assert "3 row(s) of 3 would go" in result.output
    assert "nothing was taken out" in result.output
    assert "Rows: 3 of 3" in run(repo, "stats").output


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
    # Every file came with a question of its own, so there is nothing to ask about.
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
