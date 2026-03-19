import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.google_maps_scraper import (
    parse_rating,
    parse_review_count,
    parse_opening_hours_text,
    extract_gbp_photo_count,
    extract_gbp_category,
    _grid_points,
    DETAIL_MAX_RETRIES,
    MAX_CONCURRENT_DETAILS,
)


# --- parse_rating ---

def test_parse_rating_valid():
    assert parse_rating("4,5") == 4.5


def test_parse_rating_dot_separator():
    assert parse_rating("3.8") == 3.8


def test_parse_rating_none_on_invalid():
    assert parse_rating("N/A") is None


def test_parse_rating_none_on_empty():
    assert parse_rating("") is None
    assert parse_rating(None) is None


def test_parse_rating_with_whitespace():
    assert parse_rating("  4,2  ") == 4.2


def test_parse_rating_integer():
    assert parse_rating("5") == 5.0


# --- parse_review_count ---

def test_parse_review_count_strips_parens():
    assert parse_review_count("(128)") == 128
    assert parse_review_count("128 avis") == 128


def test_parse_review_count_none_on_empty():
    assert parse_review_count("") is None


def test_parse_review_count_none_on_none():
    assert parse_review_count(None) is None


def test_parse_review_count_with_spaces():
    assert parse_review_count("1 234 avis") == 1234


def test_parse_review_count_with_narrow_no_break_space():
    assert parse_review_count("1\u202f234 avis") == 1234


# --- parse_opening_hours_text ---

def test_parse_opening_hours_text_returns_dict():
    raw = "Lundi: 9h–18h\nMardi: 9h–18h\nMercredi: Fermé"
    hours = parse_opening_hours_text(raw)
    assert hours["Lundi"] == "9h–18h"
    assert hours["Mercredi"] == "Fermé"


def test_parse_opening_hours_text_empty():
    assert parse_opening_hours_text("") == {}


def test_parse_opening_hours_text_no_colon():
    assert parse_opening_hours_text("No hours available") == {}


# --- extract_gbp_photo_count ---

def test_extract_gbp_photo_count_french():
    assert extract_gbp_photo_count("42 photos") == 42


def test_extract_gbp_photo_count_singular():
    assert extract_gbp_photo_count("1 photo") == 1


def test_extract_gbp_photo_count_with_spaces():
    assert extract_gbp_photo_count("1 234 photos") == 1234


def test_extract_gbp_photo_count_none_on_empty():
    assert extract_gbp_photo_count("") is None
    assert extract_gbp_photo_count(None) is None


def test_extract_gbp_photo_count_no_match():
    assert extract_gbp_photo_count("No images") is None


# --- extract_gbp_category ---

def test_extract_gbp_category_normal():
    assert extract_gbp_category("Agent immobilier") == "Agent immobilier"


def test_extract_gbp_category_strips_whitespace():
    assert extract_gbp_category("  Agent immobilier  ") == "Agent immobilier"


def test_extract_gbp_category_none_on_empty():
    assert extract_gbp_category("") is None
    assert extract_gbp_category(None) is None
    assert extract_gbp_category("   ") is None


# --- _grid_points ---

def test_grid_points_default_3x3():
    points = _grid_points(48.85, 48.87, 2.33, 2.35)
    assert len(points) == 9


def test_grid_points_custom_size():
    points = _grid_points(48.85, 48.87, 2.33, 2.35, rows=2, cols=2)
    assert len(points) == 4


def test_grid_points_corners():
    points = _grid_points(0.0, 1.0, 0.0, 1.0, rows=2, cols=2)
    assert (0.0, 0.0) in points
    assert (0.0, 1.0) in points
    assert (1.0, 0.0) in points
    assert (1.0, 1.0) in points


# --- Config constants ---

def test_detail_max_retries_is_positive():
    assert DETAIL_MAX_RETRIES >= 1


def test_max_concurrent_details_is_positive():
    assert MAX_CONCURRENT_DETAILS >= 1
