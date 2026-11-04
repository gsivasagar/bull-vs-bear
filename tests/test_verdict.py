import pytest

from src.verdict import parse_recommendation


@pytest.mark.parametrize("text,expected", [
    ("BUY\nRationale...", "BUY"), ("sell\nreasons", "SELL"), ("  HOLD  \n\nx", "HOLD"), ("\n\nBUY", "BUY"),
    ("**BUY**\nx", "BUY"), ("Verdict: SELL", "SELL"), ("BUY.", "BUY"),
])
def test_clear_first_line(text, expected):
    assert parse_recommendation(text) == expected


def test_falls_back_to_a_verdict_line_when_the_first_line_is_chatty():
    assert parse_recommendation("Here is my memo.\n**Verdict**: HOLD\nbecause") == "HOLD"


@pytest.mark.parametrize("text", ["", "   ", "I think it depends.", "BUY or SELL, hard to say", "no verdict here\nbuy later"])
def test_unclear_is_unknown_not_a_guess(text):
    assert parse_recommendation(text) == "UNKNOWN"
