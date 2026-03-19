"""
Unit tests for SIRENE scraper — mock the API calls, never hit the network.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from scraper.sirene_scraper import _best_name, _extract_agencies, _api_get


# ---------------------------------------------------------------------------
# _best_name
# ---------------------------------------------------------------------------

def test_best_name_prefers_enseigne():
    company = {"nom_complet": "SCI DUPONT"}
    etab = {"liste_enseignes": ["Agence Dupont Immobilier"], "nom_commercial": None}
    assert _best_name(company, etab) == "Agence Dupont Immobilier"


def test_best_name_falls_back_to_nom_commercial():
    company = {"nom_complet": "SCI MARTIN"}
    etab = {"liste_enseignes": None, "nom_commercial": "Century 21 Martin"}
    assert _best_name(company, etab) == "Century 21 Martin"


def test_best_name_falls_back_to_nom_complet():
    company = {"nom_complet": "AGENCE XYZ SARL"}
    etab = {"liste_enseignes": None, "nom_commercial": None}
    assert _best_name(company, etab) == "AGENCE XYZ SARL"


# ---------------------------------------------------------------------------
# _extract_agencies
# ---------------------------------------------------------------------------

def _make_company(postal_code: str, status: str = "A", name: str = "AGENCE TEST") -> dict:
    return {
        "nom_complet": name,
        "matching_etablissements": [
            {
                "siret": "12345678900001",
                "code_postal": postal_code,
                "etat_administratif": status,
                "adresse": f"1 RUE TEST {postal_code} PARIS",
                "liste_enseignes": None,
                "nom_commercial": None,
            }
        ],
        "siege": {},
    }


def test_extract_agencies_returns_active_in_target_cp():
    company = _make_company("75013", status="A")
    agencies = _extract_agencies(company, "75013")
    assert len(agencies) == 1
    assert agencies[0].address == "1 RUE TEST 75013 PARIS"


def test_extract_agencies_skips_closed_establishments():
    company = _make_company("75013", status="F")
    agencies = _extract_agencies(company, "75013")
    assert len(agencies) == 0


def test_extract_agencies_skips_wrong_postal_code():
    company = _make_company("75014", status="A")
    agencies = _extract_agencies(company, "75013")
    assert len(agencies) == 0


def test_extract_agencies_sets_source_sirene():
    company = _make_company("75013")
    agencies = _extract_agencies(company, "75013")
    assert agencies[0].source == "sirene"


def test_extract_agencies_detects_network():
    company = _make_company("75013", name="Century 21 Nation")
    agencies = _extract_agencies(company, "75013")
    assert agencies[0].network_affiliation == "Century 21"


# ---------------------------------------------------------------------------
# _api_get (smoke test with mock)
# ---------------------------------------------------------------------------

def test_api_get_returns_parsed_json():
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"total_results": 5, "results": []}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = _api_get("https://fake-url.test/search")
    assert result["total_results"] == 5
