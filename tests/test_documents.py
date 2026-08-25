from pathlib import Path

from tinyfacts.dataset.documents import (
    find_document,
    iter_documents,
    join_frontmatter,
    read_document,
    split_frontmatter,
    write_document,
)


def test_plain_text_has_no_metadata():
    metadata, text = split_frontmatter("Just words.\n")
    assert metadata == {}
    assert text == "Just words.\n"


def test_yaml_block_is_read_and_taken_off():
    raw = "---\ntitle: The sun\nmodel: gpt-5.1\n---\n\nThe sun is big.\n"
    metadata, text = split_frontmatter(raw)
    assert metadata == {"title": "The sun", "model": "gpt-5.1"}
    assert text == "The sun is big.\n"


def test_a_broken_yaml_block_is_kept_as_text():
    raw = "---\ntitle: [oops\n---\nBody.\n"
    metadata, text = split_frontmatter(raw)
    assert metadata == {}
    assert text == raw


def test_a_line_of_dashes_in_the_text_is_not_a_block():
    raw = "The sun is big.\n\n---\n\nIt is far away.\n"
    metadata, text = split_frontmatter(raw)
    assert metadata == {}
    assert text == raw


def test_round_trip(tmp_path: Path):
    path = write_document(
        tmp_path / "sun.md", "The sun is big.", {"title": "The sun", "instruction": None}
    )
    document = read_document(path)
    assert document.text == "The sun is big."
    assert document.metadata == {"title": "The sun"}  # Empty fields are left out
    assert document.title == "The sun"


def test_title_comes_from_the_file_name_when_there_is_no_block(tmp_path: Path):
    path = tmp_path / "how_bees_make_honey.txt"
    path.write_text("They work together.")
    assert read_document(path).title == "how bees make honey"


def test_join_leaves_out_a_block_when_there_is_nothing_to_say():
    assert join_frontmatter({}, "Words.") == "Words.\n"
    assert join_frontmatter({"title": None, "tags": []}, "Words.") == "Words.\n"


def test_both_kinds_of_file_are_found(tmp_path: Path):
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "notes.rst").write_text("no")
    assert [p.name for p in iter_documents(tmp_path)] == ["a.md", "b.txt"]
    assert find_document(tmp_path, "b") == tmp_path / "b.txt"
    assert find_document(tmp_path, "nothing") is None
