import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.enricher import assess_site_quality, extract_agent_names_from_html, detect_virtual_tour


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


# ---------------------------------------------------------------------------
# Virtual tour detection
# ---------------------------------------------------------------------------

def test_detect_virtual_tour_matterport():
    html = '<iframe src="https://my.matterport.com/show/?m=abc123"></iframe>'
    assert detect_virtual_tour(html) is True


def test_detect_virtual_tour_visite_virtuelle_text():
    html = '<a href="/biens/123">Visite virtuelle disponible</a>'
    assert detect_virtual_tour(html) is True


def test_detect_virtual_tour_360():
    html = '<div class="visite-360">Découvrez ce bien en vue 360</div>'
    assert detect_virtual_tour(html) is True


def test_detect_virtual_tour_nodalview():
    html = '<iframe src="https://nodalview.com/tour/abc"></iframe>'
    assert detect_virtual_tour(html) is True


def test_detect_virtual_tour_absent():
    html = '<p>Bel appartement 3 pièces, lumineux</p><img src="photo.jpg">'
    assert detect_virtual_tour(html) is False


def test_detect_virtual_tour_visite_3d():
    html = '<h2>Visite 3D interactive</h2>'
    assert detect_virtual_tour(html) is True
