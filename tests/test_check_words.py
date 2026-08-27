"""Tests of the word check: which words are wrong, and where they are."""

from tinyfacts.check_words import (
    check_words_with_context,
    find_invalid_words,
    split_words,
)
from tinyfacts.word_forms import WordFormsDictionary

TEXT = "The sun is a big hot ball of quantum fire in the quantum sky."


def test_a_good_text_has_nothing_wrong_with_it():
    assert find_invalid_words("The sun is a big hot light.") == set()
    assert check_words_with_context("The sun is a big hot light.").invalid_words == []


def test_the_bad_words_are_found_without_their_places():
    assert find_invalid_words(TEXT) == {"quantum"}


def test_every_use_of_a_bad_word_is_found_with_the_words_around_it():
    found = check_words_with_context(TEXT).invalid_words
    assert [(item.word, item.index) for item in found] == [("quantum", 8), ("quantum", 12)]
    assert found[0].context == "ball of quantum fire in"
    assert found[1].context == "in the quantum sky"  # The end of the text cuts it short


def test_the_two_ways_of_checking_agree():
    with_context = check_words_with_context(TEXT).invalid_words
    assert {item.word for item in with_context} == find_invalid_words(TEXT)


def test_the_word_forms_are_only_loaded_once():
    """Every dictionary shares one copy, so making one per text costs nothing."""
    first, second = WordFormsDictionary(), WordFormsDictionary()
    assert first.allowed_words is second.allowed_words


def test_nothing_is_lost_when_there_are_no_words_at_all():
    assert split_words("") == []
    assert find_invalid_words("") == set()
    assert check_words_with_context("").invalid_words == []
