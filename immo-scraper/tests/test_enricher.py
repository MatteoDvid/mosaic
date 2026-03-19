import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.enricher import assess_site_quality, extract_agent_names_from_html


def test_assess_site_quality_modern():
    html = '<meta name="viewport" content="width=device-width"><div class="flex grid">'
    assert assess_site_quality(html) == "modern"


def test_assess_site_quality_outdated_table_layout():
    html = "<table><tr><td>menu</td><td>content</td></tr></table>" * 5
    assert assess_site_quality(html) == "outdated"


def test_assess_site_quality_dated():
    # Has viewport but no modern CSS framework
    html = '<meta name="viewport"><div id="main"><p>content</p></div>'
    assert assess_site_quality(html) == "dated"


def test_extract_agent_names_from_common_pattern():
    html = """
    <div class="team-member"><h3>Jean Dupont</h3><p>Directeur</p></div>
    <div class="team-member"><h3>Marie Martin</h3><p>Agent</p></div>
    """
    names = extract_agent_names_from_html(html)
    assert "Jean Dupont" in names
    assert "Marie Martin" in names


def test_extract_agent_names_empty_on_no_pattern():
    html = "<p>Bienvenue sur notre site</p>"
    assert extract_agent_names_from_html(html) == []
