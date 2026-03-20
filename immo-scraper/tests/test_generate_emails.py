import pytest
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from emails.generate_emails import build_prompt_messages, load_system_prompt, parse_claude_response
from scraper.lead_scorer import OFFER_PHOTO, OFFER_SITE


def test_load_system_prompt_photo_contains_mosaic():
    prompt = load_system_prompt(OFFER_PHOTO)
    assert "Mosaic" in prompt
    assert "photo" in prompt.lower()


def test_load_system_prompt_site_contains_visite():
    prompt = load_system_prompt(OFFER_SITE)
    assert "Mosaic" in prompt
    assert "visite" in prompt.lower()


def test_build_prompt_messages_structure_photo():
    agency_data = {"name": "Test Agency", "email": "test@test.fr", "website": "http://test.fr"}
    messages = build_prompt_messages(agency_data, screenshot_b64=None, offer=OFFER_PHOTO)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert any(isinstance(c, dict) and c.get("type") == "text" for c in content)


def test_build_prompt_messages_structure_site():
    agency_data = {"name": "Agence Test", "email": "info@test.fr"}
    messages = build_prompt_messages(agency_data, screenshot_b64=None, offer=OFFER_SITE)
    content = messages[0]["content"]
    text_parts = [c["text"] for c in content if c.get("type") == "text"]
    assert any("visite" in t.lower() for t in text_parts)


def test_build_prompt_messages_with_screenshot():
    agency_data = {"name": "Agence Rivoli", "email": "info@rivoli.fr"}
    messages = build_prompt_messages(agency_data, screenshot_b64="abc123", offer=OFFER_PHOTO)
    content = messages[0]["content"]
    types = [c.get("type") for c in content]
    assert "image" in types
    assert "text" in types


def test_parse_claude_response_valid_json():
    raw = '{"subject": "Votre présence en ligne", "body": "Bonjour..."}'
    result = parse_claude_response(raw)
    assert result["subject"] == "Votre présence en ligne"


def test_parse_claude_response_strips_markdown():
    raw = '```json\n{"subject": "Test", "body": "Corps"}\n```'
    result = parse_claude_response(raw)
    assert result["subject"] == "Test"


def test_parse_claude_response_raises_on_invalid():
    with pytest.raises(ValueError):
        parse_claude_response("not json at all")
