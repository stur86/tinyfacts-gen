"""Tests of the `generate` command: how lines are named, and what gets asked."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

import main
from main import _make_name, _name_arguments, _read_prompt_template, app
from tinyfacts.dataset import read_document

runner = CliRunner()


@pytest.mark.parametrize(
    "argument, expected",
    [
        ("sun", "sun"),
        ("The Sun", "the_sun"),
        ("What is a black hole?", "what_is_a_black_hole"),
        ("  e-mail  ", "e_mail"),
        ("Ünicode Wörds", "ünicode_wörds"),
        ("???", ""),
    ],
)
def test_a_line_names_its_own_file(argument: str, expected: str):
    assert _make_name(argument) == expected


def test_a_name_can_be_put_in_front():
    assert _make_name("The Sun", "My Run") == "my_run_the_sun"
    assert _make_name("???", "My Run") == "my_run"


def test_lines_that_come_to_the_same_name_are_told_apart():
    assert _name_arguments(["sun", "sun", "Sun!", "rain"]) == [
        "sun",
        "sun_2",
        "sun_3",
        "rain",
    ]
    assert _name_arguments(["???"]) == ["item"]


def test_a_prompt_can_be_given_as_a_file_or_as_itself(tmp_path: Path):
    template = tmp_path / "prompt.txt"
    template.write_text("Tell me about {{argument}}.\n")
    assert _read_prompt_template(str(template)) == "Tell me about {{argument}}."
    assert _read_prompt_template("Say {{argument}}") == "Say {{argument}}"


class FakeClient:
    """Stands in for the OpenAI style client, and keeps what it was asked."""

    asked: list[str] = []

    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, model, messages):
        prompt = messages[0]["content"]
        FakeClient.asked.append(prompt)
        message = type("Message", (), {"content": f"An answer to: {prompt}"})()
        return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()


@pytest.fixture
def client(monkeypatch) -> type[FakeClient]:
    FakeClient.asked = []
    monkeypatch.setattr(main.openai, "OpenAI", FakeClient)
    return FakeClient


def run(*args: str):
    result = runner.invoke(app, ["generate", *args])
    assert result.exit_code in (0, 1), result.output
    return result


def test_every_line_is_put_into_the_prompt(tmp_path: Path, client):
    lines = tmp_path / "arguments.txt"
    lines.write_text("the sun\nWhat is rain?\n\n")
    out = tmp_path / "out"
    run("-a", str(lines), "-p", "Tell me about {{argument}}.", "-o", str(out))

    assert client.asked == [
        "Tell me about the sun.",
        "Tell me about What is rain?.",
    ]
    document = read_document(out / "what_is_rain.md")
    assert document.metadata["title"] == "What is rain?"
    assert document.metadata["instruction"] == "Tell me about What is rain?."
    assert document.text == "An answer to: Tell me about What is rain?."


def test_a_name_goes_in_front_of_every_file(tmp_path: Path, client):
    lines = tmp_path / "arguments.txt"
    lines.write_text("the sun\n")
    out = tmp_path / "out"
    run("-a", str(lines), "-n", "my run", "-o", str(out))
    assert (out / "my_run_the_sun.md").exists()


def test_lines_that_already_have_a_file_are_skipped(tmp_path: Path, client):
    lines = tmp_path / "arguments.txt"
    lines.write_text("the sun\nrain\n")
    out = tmp_path / "out"
    run("-a", str(lines), "-o", str(out))
    assert len(client.asked) == 2

    client.asked = []
    result = run("-a", str(lines), "-o", str(out))
    assert client.asked == []
    assert "0 to do, 2 already there" in result.output


def test_the_default_prompt_still_explains_a_word(tmp_path: Path, client):
    lines = tmp_path / "arguments.txt"
    lines.write_text("sun\n")
    run("-a", str(lines), "-o", str(tmp_path / "out"))
    assert client.asked == ["Explain the following word: sun"]


def test_a_prompt_with_no_spot_for_the_line_is_refused(tmp_path: Path, client):
    lines = tmp_path / "arguments.txt"
    lines.write_text("sun\n")
    result = runner.invoke(
        app, ["generate", "-a", str(lines), "-p", "Explain a word", "-o", str(tmp_path / "out")]
    )
    assert result.exit_code == 1
    assert "no '{{argument}}' in it" in result.output
    assert client.asked == []


def test_a_call_that_fails_does_not_stop_the_run(tmp_path: Path, client, monkeypatch):
    def create(self, model, messages):
        if "rain" in messages[0]["content"]:
            raise RuntimeError("no answer")
        FakeClient.asked.append(messages[0]["content"])
        message = type("Message", (), {"content": "ok"})()
        return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()

    monkeypatch.setattr(FakeClient, "create", create)
    lines = tmp_path / "arguments.txt"
    lines.write_text("rain\nsun\n")
    out = tmp_path / "out"
    result = run("-a", str(lines), "-o", str(out))
    assert "1 line(s) failed" in result.output
    assert "rain: no answer" in result.output
    assert (out / "sun.md").exists()
    assert not (out / "rain.md").exists()
