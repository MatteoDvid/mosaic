import pytest
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from emails.generate_emails import build_prompt_messages, load_system_prompt, parse_claude_response


def test_load_system_prompt_contains_mosaic():
    prompt = load_system_prompt()
    assert "Mosaic" in prompt


def test_build_prompt_messages_structure():
    agency_data = {"name": "Test Agency", "email": "test@test.fr", "website": "http://test.fr"}
    messages = build_prompt_messages(agency_data, screenshot_b64=None)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert any(isinstance(c, dict) and c.get("type") == "text" for c in content)


def test_build_prompt_messages_with_screenshot():
    agency_data = {"name": "Agence Rivoli", "email": "info@rivoli.fr"}
    messages = build_prompt_messages(agency_data, screenshot_b64="abc123")
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
