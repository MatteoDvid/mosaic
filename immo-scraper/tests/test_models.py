import pytest
from models import Agency, EnrichmentStatus


def test_agency_slug_generated_from_name_and_city():
    a = Agency(name="Agence XYZ", address="12 rue de Rivoli, Paris 1er", source="pages_jaunes")
    assert a.slug == "agence-xyz"


def test_agency_slug_strips_accents_and_spaces():
    a = Agency(name="Immobilier Île-de-France", address="Neuilly", source="google_maps")
    assert a.slug == "immobilier-ile-de-france"


def test_default_enrichment_status_is_scraped():
    a = Agency(name="Test", address="Paris", source="google_maps")
    assert a.enrichment_status == EnrichmentStatus.SCRAPED


def test_agency_dict_round_trip():
    a = Agency(name="Test", address="Paris", source="pages_jaunes", phone="+33 1 23 45 67 89")
    d = a.model_dump()
    a2 = Agency(**d)
    assert a2.phone == a.phone


def test_enrichment_status_values():
    assert EnrichmentStatus.SCRAPED == "scraped"
    assert EnrichmentStatus.ENRICHED == "enriched"
    assert EnrichmentStatus.SCREENSHOT_DONE == "screenshot_done"
    assert EnrichmentStatus.READY_FOR_EMAIL == "ready_for_email"
