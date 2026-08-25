import pytest

from tinyfacts.dataset.filters import FilterError, RecordFilter
from tinyfacts.dataset.records import DatasetRecord

ROWS = [
    DatasetRecord.build(
        id="words/sun",
        text="The sun is a big hot light.",
        title="sun",
        source="words",
        model="tinyfacts-llama",
        instruction="Explain the following word: sun",
        tags=["word-explanation"],
    ),
    DatasetRecord.build(
        id="hand/stars",
        text="Stars are far away suns.",
        title="Stars",
        source="hand",
        model=None,
        tags=["night"],
    ),
    DatasetRecord.build(
        id="notes/how_rain_falls",
        text="Water goes up and comes back down as rain, again and again.",
        title="how rain falls",
        source="notes",
        model="gpt-5.1",
        instruction="How does rain work?",
    ),
]


def ids(record_filter: RecordFilter) -> list[str]:
    return [row.id for row in record_filter.apply(ROWS)]


def test_no_filter_keeps_everything():
    assert len(ids(RecordFilter.build())) == 3
    assert RecordFilter.build().is_empty


def test_title_is_matched_as_a_regular_expression():
    assert ids(RecordFilter.build(title="^how ")) == ["notes/how_rain_falls"]
    assert ids(RecordFilter.build(title="STARS")) == ["hand/stars"]  # Case does not matter


def test_sources_and_models_can_be_given_more_than_one_way():
    assert ids(RecordFilter.build(source=["words", "hand"])) == ["words/sun", "hand/stars"]
    assert ids(RecordFilter.build(source=["words,hand"])) == ["words/sun", "hand/stars"]
    assert ids(RecordFilter.build(model=["gpt-5.1"])) == ["notes/how_rain_falls"]


def test_rows_can_be_picked_by_whether_they_have_a_question():
    assert ids(RecordFilter.build(has_instruction=False)) == ["hand/stars"]
    assert len(ids(RecordFilter.build(has_instruction=True))) == 2


def test_asking_about_the_question_only_looks_at_rows_that_have_one():
    assert ids(RecordFilter.build(instruction="rain")) == ["notes/how_rain_falls"]


def test_word_counts():
    assert ids(RecordFilter.build(min_words=8)) == ["notes/how_rain_falls"]
    assert ids(RecordFilter.build(max_words=5)) == ["hand/stars"]


def test_tags_and_text():
    assert ids(RecordFilter.build(tag=["night"])) == ["hand/stars"]
    assert ids(RecordFilter.build(text="far away")) == ["hand/stars"]


def test_every_test_has_to_pass():
    assert ids(RecordFilter.build(source=["words"], min_words=100)) == []


def test_a_bad_regular_expression_is_reported():
    with pytest.raises(FilterError, match="--title"):
        RecordFilter.build(title="(unclosed")
