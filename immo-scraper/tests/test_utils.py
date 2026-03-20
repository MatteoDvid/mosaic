import pytest
import json
import tempfile
import os
from utils import (
    extract_emails_from_html,
    deduplicate_agencies,
    random_delay,
    load_agencies,
    save_agencies,
)
from models import Agency
from scraper.lead_scorer import compute_lead_score, suggest_offers, OFFER_PHOTO, OFFER_SITE


def test_extract_emails_finds_mailto_links():
    html = '<a href="mailto:contact@agence.fr">Nous contacter</a>'
    assert "contact@agence.fr" in extract_emails_from_html(html)


def test_extract_emails_finds_bare_email_in_text():
    html = "<p>Écrivez-nous à info@immo-paris.com pour plus d'infos.</p>"
    assert "info@immo-paris.com" in extract_emails_from_html(html)


def test_extract_emails_deduplicates():
    html = "contact@test.fr contact@test.fr"
    emails = extract_emails_from_html(html)
    assert emails.count("contact@test.fr") == 1


def test_extract_emails_skips_images_and_css():
    html = "background.png style.css logo@2x.png"
    assert extract_emails_from_html(html) == []


def test_deduplicate_agencies_merges_on_slug():
    a1 = Agency(name="Agence ABC", address="Paris", source="pages_jaunes", phone="0101010101")
    a2 = Agency(name="Agence ABC", address="Paris", source="google_maps", google_rating=4.5)
    merged = deduplicate_agencies([a1, a2])
    assert len(merged) == 1
    assert merged[0].phone == "0101010101"
    assert merged[0].google_rating == 4.5


def test_deduplicate_agencies_keeps_distinct():
    a1 = Agency(name="Agence ABC", address="Paris 1", source="pages_jaunes")
    a2 = Agency(name="Agence XYZ", address="Paris 2", source="pages_jaunes")
    merged = deduplicate_agencies([a1, a2])
    assert len(merged) == 2


def test_deduplicate_cross_source_absorbs_gm_into_sirene():
    """Google Maps entry at same address + overlapping name merges INTO the sirene record."""
    sirene = Agency(
        name="Fredelion Immobilier",
        address="229 RUE DE LA CROIX NIVERT 75015 PARIS",
        source="sirene",
        siret="12345678900001",
        slug="fredelion-immobilier-00001",
    )
    gm = Agency(
        name="FREDeLION Paris 13",
        address="229 rue de la Croix Nivert 75015 Paris",
        source="google_maps",
        phone="0183641213",
        website="https://fredelion.com",
    )
    result = deduplicate_agencies([sirene, gm])
    assert len(result) == 1
    assert result[0].siret == "12345678900001"   # kept sirene slug
    assert result[0].phone == "0183641213"        # got gm phone
    assert result[0].website == "https://fredelion.com"
    assert "sirene" in result[0].source
    assert "google_maps" in result[0].source


def test_deduplicate_cross_source_no_match_different_address():
    """Different address -> kept as separate entries."""
    sirene = Agency(name="Orpi Nation", address="10 rue de la Nation 75011 Paris", source="sirene", slug="orpi-nation-00001")
    gm     = Agency(name="Orpi Corvisart", address="5 rue Corvisart 75013 Paris", source="google_maps")
    result = deduplicate_agencies([sirene, gm])
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Lead scorer tests
# ---------------------------------------------------------------------------

def test_lead_score_max_for_weak_agency():
    """Agency with no data at all should get max score (100)."""
    a = Agency(name="Weak Agency", address="Paris", source="google_maps")
    score, details = compute_lead_score(a)
    assert score == 100.0


def test_lead_score_low_for_strong_agency():
    """Agency with strong digital presence should score low."""
    a = Agency(
        name="Strong Agency", address="Paris", source="google_maps",
        google_rating=4.8, google_review_count=50,
        site_quality="modern", has_blog=True, is_mobile_friendly=True,
        gbp_photo_count=30, gbp_has_posts=True, has_virtual_tour=True,
        network_affiliation="Century 21",
    )
    score, details = compute_lead_score(a)
    assert score == 0.0


def test_suggest_offers_photo_when_few_photos():
    """Agency with few GBP photos should get photo offer."""
    a = Agency(name="Test", address="Paris", source="google_maps", gbp_photo_count=2,
               site_quality="modern", has_virtual_tour=True)
    score, details = compute_lead_score(a)
    offers = suggest_offers(a, details)
    assert OFFER_PHOTO in offers


def test_suggest_offers_site_when_outdated_site():
    """Agency with outdated site should get site offer."""
    a = Agency(name="Test", address="Paris", source="google_maps",
               gbp_photo_count=25, site_quality="outdated", has_virtual_tour=False)
    score, details = compute_lead_score(a)
    offers = suggest_offers(a, details)
    assert OFFER_SITE in offers


def test_suggest_offers_site_when_no_virtual_tour():
    """Agency with no virtual tour should get site offer."""
    a = Agency(name="Test", address="Paris", source="google_maps",
               gbp_photo_count=25, site_quality="modern", has_virtual_tour=False)
    score, details = compute_lead_score(a)
    offers = suggest_offers(a, details)
    assert OFFER_SITE in offers


def test_virtual_tour_field_in_model():
    """has_virtual_tour field round-trips correctly."""
    a = Agency(name="Test", address="Paris", source="google_maps", has_virtual_tour=True)
    d = a.model_dump()
    a2 = Agency(**d)
    assert a2.has_virtual_tour is True


def test_save_and_load_agencies_round_trip():
    agencies = [
        Agency(name="Test Agency", address="1 rue Test, Paris", source="google_maps", phone="0101010101"),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        save_agencies(agencies, path)
        loaded = load_agencies(path)
        assert len(loaded) == 1
        assert loaded[0].name == "Test Agency"
        assert loaded[0].phone == "0101010101"
    finally:
        os.unlink(path)
