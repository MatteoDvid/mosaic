import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.google_maps_scraper import (
    parse_rating,
    parse_review_count,
    parse_opening_hours_text,
)


def test_parse_rating_valid():
    assert parse_rating("4,5") == 4.5


def test_parse_rating_dot_separator():
    assert parse_rating("3.8") == 3.8


def test_parse_rating_none_on_invalid():
    assert parse_rating("N/A") is None


def test_parse_review_count_strips_parens():
    assert parse_review_count("(128)") == 128
    assert parse_review_count("128 avis") == 128


def test_parse_review_count_none_on_empty():
    assert parse_review_count("") is None


def test_parse_opening_hours_text_returns_dict():
    raw = "Lundi: 9h–18h\nMardi: 9h–18h\nMercredi: Fermé"
    hours = parse_opening_hours_text(raw)
    assert hours["Lundi"] == "9h–18h"
    assert hours["Mercredi"] == "Fermé"
