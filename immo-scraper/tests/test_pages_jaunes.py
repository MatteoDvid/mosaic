import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.pages_jaunes_scraper import (
    parse_network_affiliation,
    normalize_phone,
)


def test_parse_network_affiliation_century21():
    assert parse_network_affiliation("Century 21 - Agence Paris") == "Century 21"


def test_parse_network_affiliation_orpi():
    assert parse_network_affiliation("Orpi Immobilier Rivoli") == "Orpi"


def test_parse_network_affiliation_laforet():
    assert parse_network_affiliation("Laforêt - Paris 11") == "Laforêt"


def test_parse_network_affiliation_independent():
    assert parse_network_affiliation("Agence Dupont Immobilier") == "indépendant"


def test_normalize_phone_strips_spaces():
    assert normalize_phone("01 23 45 67 89") == "01 23 45 67 89"


def test_normalize_phone_none_on_empty():
    assert normalize_phone("") is None


def test_normalize_phone_none_on_none():
    assert normalize_phone(None) is None
