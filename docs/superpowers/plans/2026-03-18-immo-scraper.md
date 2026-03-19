# Immo Scraper — Full Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a resumable, multi-step pipeline that scrapes real estate agencies from Google Maps and Pages Jaunes, enriches each record with website/GBP data + screenshots, then generates hyper-personalized French cold emails via the Claude API with Vision.

**Architecture:** Five sequential, independently runnable stages share a single Pydantic data model and a shared async Playwright browser context manager. State is checkpointed to `data/state.json` at every save so any stage can resume from where it left off. Each stage reads from and writes to `data/agences_immo.json`.

**Tech Stack:** Python 3.11+, Playwright (async) + playwright-stealth, Pydantic v2, rich, python-dotenv, anthropic SDK, pytest + pytest-asyncio

---

## Chunk 1: Project Scaffold, Config & Data Models

### Task 1: Directory scaffold + requirements

**Files:**
- Create: `immo-scraper/requirements.txt`
- Create: `immo-scraper/.env.example`
- Create: `immo-scraper/config.py`

- [ ] **Step 1: Create the project skeleton directories**

```bash
cd /c/Users/mdrag/Documents/mosaic/immo-scraper
mkdir -p scraper emails data screenshots tests
touch data/.gitkeep screenshots/.gitkeep
```

- [ ] **Step 2: Write `requirements.txt`**

```
playwright==1.44.0
playwright-stealth==1.0.6
pydantic==2.7.1
python-dotenv==1.0.1
anthropic==0.28.0
rich==13.7.1
aiofiles==23.2.1
pytest==8.2.2
pytest-asyncio==0.23.7
```

- [ ] **Step 3: Write `.env.example`**

```
ANTHROPIC_API_KEY=sk-ant-...
```

- [ ] **Step 4: Write `config.py`**

```python
from __future__ import annotations
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = "claude-sonnet-4-6"

# Zones to scrape — configurable list of (query_term, city_slug) pairs
ZONES: list[tuple[str, str]] = [
    # Paris arrondissements
    ("agence immobilière Paris 1", "paris-01"),
    ("agence immobilière Paris 2", "paris-02"),
    ("agence immobilière Paris 3", "paris-03"),
    ("agence immobilière Paris 4", "paris-04"),
    ("agence immobilière Paris 5", "paris-05"),
    ("agence immobilière Paris 6", "paris-06"),
    ("agence immobilière Paris 7", "paris-07"),
    ("agence immobilière Paris 8", "paris-08"),
    ("agence immobilière Paris 9", "paris-09"),
    ("agence immobilière Paris 10", "paris-10"),
    ("agence immobilière Paris 11", "paris-11"),
    ("agence immobilière Paris 12", "paris-12"),
    ("agence immobilière Paris 13", "paris-13"),
    ("agence immobilière Paris 14", "paris-14"),
    ("agence immobilière Paris 15", "paris-15"),
    ("agence immobilière Paris 16", "paris-16"),
    ("agence immobilière Paris 17", "paris-17"),
    ("agence immobilière Paris 18", "paris-18"),
    ("agence immobilière Paris 19", "paris-19"),
    ("agence immobilière Paris 20", "paris-20"),
    # Inner suburbs
    ("agence immobilière Boulogne-Billancourt", "boulogne-billancourt"),
    ("agence immobilière Neuilly-sur-Seine", "neuilly-sur-seine"),
    ("agence immobilière Levallois-Perret", "levallois-perret"),
    ("agence immobilière Issy-les-Moulineaux", "issy-les-moulineaux"),
    ("agence immobilière Saint-Denis", "saint-denis"),
    ("agence immobilière Montreuil", "montreuil"),
    ("agence immobilière Vincennes", "vincennes"),
    ("agence immobilière Saint-Mandé", "saint-mande"),
]

# Playwright timing config (seconds)
NAV_DELAY_MIN: float = 2.0
NAV_DELAY_MAX: float = 5.0
SCROLL_DELAY_MIN: float = 0.5
SCROLL_DELAY_MAX: float = 1.5

# Paths
DATA_DIR: str = "data"
SCREENSHOTS_DIR: str = "screenshots"
AGENCIES_JSON: str = f"{DATA_DIR}/agences_immo.json"
AGENCIES_CSV: str = f"{DATA_DIR}/agences_immo.csv"
EMAILS_JSON: str = f"{DATA_DIR}/emails_generated.json"
STATE_JSON: str = f"{DATA_DIR}/state.json"

# User-agent pool
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]
```

- [ ] **Step 5: Install dependencies and Playwright browser**

```bash
cd /c/Users/mdrag/Documents/mosaic/immo-scraper
pip install -r requirements.txt
playwright install chromium
```

Expected: all packages install, Chromium downloaded.

- [ ] **Step 6: Commit**

```bash
cd /c/Users/mdrag/Documents/mosaic/immo-scraper
git init
git add .
git commit -m "chore: scaffold project with config and requirements"
```

---

### Task 2: Pydantic data model

**Files:**
- Create: `immo-scraper/models.py`
- Create: `immo-scraper/tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_models.py
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
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd /c/Users/mdrag/Documents/mosaic/immo-scraper
pytest tests/test_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 3: Write `models.py`**

```python
from __future__ import annotations
import re
import unicodedata
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class EnrichmentStatus(str, Enum):
    SCRAPED = "scraped"
    ENRICHED = "enriched"
    SCREENSHOT_DONE = "screenshot_done"
    READY_FOR_EMAIL = "ready_for_email"


def _slugify(text: str) -> str:
    """Convert text to URL-safe slug (strips accents, lowercase, hyphens)."""
    # Normalize unicode → decompose accents
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    # Lowercase, replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug


class Agency(BaseModel):
    # Identity
    name: str
    slug: str = Field(default="")
    address: str
    source: str  # "google_maps" | "pages_jaunes"

    # Contact
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    # Google Maps
    google_maps_url: Optional[str] = None
    google_rating: Optional[float] = None
    google_review_count: Optional[int] = None
    gbp_link: Optional[str] = None
    opening_hours: Optional[dict[str, str]] = None

    # Network
    network_affiliation: Optional[str] = None  # "Century 21", "Orpi", etc. or "indépendant"

    # Enrichment
    agents_names: list[str] = Field(default_factory=list)
    has_blog: Optional[bool] = None
    site_quality: Optional[str] = None  # "modern" | "dated" | "outdated" | "none"
    is_mobile_friendly: Optional[bool] = None
    gbp_photo_count: Optional[int] = None
    gbp_last_photo_date: Optional[str] = None
    gbp_has_posts: Optional[bool] = None
    gbp_category: Optional[str] = None

    # Pipeline state
    screenshot_path: Optional[str] = None
    enrichment_status: EnrichmentStatus = EnrichmentStatus.SCRAPED

    @model_validator(mode="after")
    def _generate_slug(self) -> "Agency":
        if not self.slug:
            self.slug = _slugify(self.name)
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add Agency pydantic model and EnrichmentStatus enum"
```

---

### Task 3: Shared utilities (storage, delays, email extraction)

**Files:**
- Create: `immo-scraper/utils.py`
- Create: `immo-scraper/tests/test_utils.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_utils.py
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
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_utils.py -v
```
Expected: `ModuleNotFoundError: No module named 'utils'`

- [ ] **Step 3: Write `utils.py`**

```python
from __future__ import annotations
import asyncio
import csv
import json
import random
import re
from pathlib import Path
from typing import Optional

from models import Agency, EnrichmentStatus


# ---------------------------------------------------------------------------
# Email extraction
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
_SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".webp"}


def extract_emails_from_html(html: str) -> list[str]:
    """Extract unique email addresses from raw HTML, skipping file references."""
    found = _EMAIL_RE.findall(html)
    emails: list[str] = []
    seen: set[str] = set()
    for e in found:
        # Skip if the "email" ends with a known non-email extension
        if any(e.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
            continue
        e_lower = e.lower()
        if e_lower not in seen:
            seen.add(e_lower)
            emails.append(e)
    return emails


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_agencies(agencies: list[Agency]) -> list[Agency]:
    """Merge agencies with the same slug, combining non-null fields."""
    by_slug: dict[str, Agency] = {}
    for agency in agencies:
        slug = agency.slug
        if slug not in by_slug:
            by_slug[slug] = agency
        else:
            existing = by_slug[slug]
            # Merge: prefer non-None values from the new record
            merged_data = existing.model_dump()
            for field, value in agency.model_dump().items():
                if value is not None and merged_data.get(field) is None:
                    merged_data[field] = value
                # Special: keep the better source set
                if field == "source" and value != merged_data[field]:
                    merged_data[field] = f"{merged_data[field]},{value}"
            by_slug[slug] = Agency(**merged_data)
    return list(by_slug.values())


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_agencies(agencies: list[Agency], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [a.model_dump() for a in agencies]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def load_agencies(path: str) -> list[Agency]:
    if not Path(path).exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Agency(**d) for d in data]


def export_csv(agencies: list[Agency], path: str) -> None:
    if not agencies:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(Agency.model_fields.keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for agency in agencies:
            row = agency.model_dump()
            # Flatten complex fields
            row["opening_hours"] = json.dumps(row["opening_hours"], ensure_ascii=False) if row["opening_hours"] else ""
            row["agents_names"] = ", ".join(row["agents_names"])
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Delays
# ---------------------------------------------------------------------------

async def random_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    """Async sleep for a random duration to mimic human behaviour."""
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_utils.py -v
```
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_utils.py
git commit -m "feat: add utils — email extraction, dedup, save/load, random delay"
```

---

### Task 4: Shared browser context manager

**Files:**
- Create: `immo-scraper/browser.py`
- Create: `immo-scraper/tests/test_browser.py`

- [ ] **Step 1: Write the failing test (lightweight — just verifies the context manager contract)**

```python
# tests/test_browser.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_browser_context_manager_returns_page():
    """BrowserSession.__aenter__ must yield a Page object."""
    mock_page = MagicMock()
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_playwright = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("browser.async_playwright") as mock_ap:
        mock_ap.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_ap.return_value.__aexit__ = AsyncMock(return_value=None)

        from browser import BrowserSession
        async with BrowserSession(headless=True) as session:
            page = await session.new_page()
            assert page is not None
```

- [ ] **Step 2: Run to verify test fails**

```bash
pytest tests/test_browser.py -v
```
Expected: `ModuleNotFoundError: No module named 'browser'`

- [ ] **Step 3: Write `browser.py`**

```python
from __future__ import annotations
import random
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import stealth_async

from config import USER_AGENTS, NAV_DELAY_MIN, NAV_DELAY_MAX
from utils import random_delay


class BrowserSession:
    """
    Async context manager that owns a single Playwright browser + context.
    Usage:
        async with BrowserSession() as session:
            page = await session.new_page()
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._user_agent = random.choice(USER_AGENTS)

    async def __aenter__(self) -> "BrowserSession":
        self._playwright_ctx = async_playwright()
        self._playwright = await self._playwright_ctx.__aenter__()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=self._user_agent,
            viewport={"width": 1366, "height": 768},
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        return self

    async def new_page(self) -> Page:
        assert self._context is not None, "BrowserSession not started"
        page = await self._context.new_page()
        await stealth_async(page)
        return page

    async def navigate(self, page: Page, url: str) -> None:
        """Navigate with random delay to mimic human browsing."""
        await random_delay(NAV_DELAY_MIN, NAV_DELAY_MAX)
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    async def __aexit__(self, *args) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright_ctx:
            await self._playwright_ctx.__aexit__(*args)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_browser.py -v
```
Expected: 1 PASSED

- [ ] **Step 5: Commit**

```bash
git add browser.py tests/test_browser.py
git commit -m "feat: add BrowserSession shared context manager with stealth"
```

---

## Chunk 2: Pages Jaunes Scraper

### Task 5: Pages Jaunes scraper

**Files:**
- Create: `immo-scraper/scraper/pages_jaunes_scraper.py`
- Create: `immo-scraper/scraper/__init__.py`
- Create: `immo-scraper/tests/test_pages_jaunes.py`

> Note: The scraper itself requires live network access. Unit tests cover the HTML parsing helpers; the `run()` function is tested via integration test stubs.

- [ ] **Step 1: Write unit tests for the HTML parsing helpers**

```python
# tests/test_pages_jaunes.py
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
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_pages_jaunes.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `scraper/__init__.py` (empty)**

```bash
touch /c/Users/mdrag/Documents/mosaic/immo-scraper/scraper/__init__.py
```

- [ ] **Step 4: Write `scraper/pages_jaunes_scraper.py`**

```python
"""
Pages Jaunes scraper — scrapes agences immobilières for a list of zones.

Usage:
    python -m scraper.pages_jaunes_scraper [--headed] [--zones paris-01,paris-02]
"""
from __future__ import annotations
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

# Add parent dir to path when run as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from browser import BrowserSession
from config import ZONES, AGENCIES_JSON, SCROLL_DELAY_MIN, SCROLL_DELAY_MAX
from models import Agency, EnrichmentStatus
from utils import load_agencies, save_agencies, random_delay

console = Console()

# Known real-estate network keywords → canonical name
_NETWORKS: dict[str, str] = {
    "century 21": "Century 21",
    "orpi": "Orpi",
    "laforêt": "Laforêt",
    "laforet": "Laforêt",
    "era immobilier": "ERA Immobilier",
    "guy hoquet": "Guy Hoquet",
    "square habitat": "Square Habitat",
    "lj résidentiel": "LJ Résidentiel",
    "foncia": "Foncia",
    "nexity": "Nexity",
    "stéphane plaza": "Stéphane Plaza",
    "stephane plaza": "Stéphane Plaza",
    "human immobilier": "Human Immobilier",
    "sextant": "Sextant",
    "l'adresse": "L'Adresse",
    "l adresse": "L'Adresse",
    "arthur immo": "Arthur Immo",
    "agences de france": "Agences de France",
}


def parse_network_affiliation(name: str) -> str:
    """Return known network name from agency name, or 'indépendant'."""
    name_lower = name.lower()
    for keyword, canonical in _NETWORKS.items():
        if keyword in name_lower:
            return canonical
    return "indépendant"


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    cleaned = phone.strip()
    return cleaned if cleaned else None


async def _scrape_zone(session: BrowserSession, zone_query: str, zone_slug: str) -> list[Agency]:
    """Scrape one zone from Pages Jaunes and return a list of Agency objects."""
    agencies: list[Agency] = []
    page = await session.new_page()

    # Pages Jaunes search URL
    # quoi = what, ou = where
    quoi = "agences+immobili%C3%A8res"
    ou = zone_query.replace(" ", "+").replace(",", "")
    url = f"https://www.pagesjaunes.fr/annuaire/chercher?quoi={quoi}&ou={ou}"

    console.log(f"[cyan]Pages Jaunes[/cyan] → {zone_query}")
    try:
        await session.navigate(page, url)
    except Exception as e:
        console.log(f"[red]Nav error for {zone_query}: {e}[/red]")
        await page.close()
        return agencies

    page_num = 1
    while True:
        await random_delay(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX)

        # Each result card
        cards = await page.query_selector_all("div.bi-content")
        if not cards:
            break

        for card in cards:
            try:
                # Name
                name_el = await card.query_selector("a.denomination-links span")
                if not name_el:
                    continue
                name = (await name_el.inner_text()).strip()

                # Address
                address_el = await card.query_selector("span.adresse")
                address = (await address_el.inner_text()).strip() if address_el else ""

                # Phone
                phone_el = await card.query_selector("a[href^='tel:']")
                phone_raw = await phone_el.get_attribute("href") if phone_el else None
                phone = normalize_phone(phone_raw.replace("tel:", "") if phone_raw else None)

                # Website
                web_el = await card.query_selector("a.url-website")
                website = await web_el.get_attribute("href") if web_el else None

                agency = Agency(
                    name=name,
                    address=address,
                    source="pages_jaunes",
                    phone=phone,
                    website=website,
                    network_affiliation=parse_network_affiliation(name),
                )
                agencies.append(agency)
            except Exception as e:
                console.log(f"[yellow]Card parse error: {e}[/yellow]")

        # Try to click next page
        next_btn = await page.query_selector("a[aria-label='Page suivante']")
        if not next_btn:
            break
        page_num += 1
        await next_btn.click()
        await random_delay(2.0, 4.0)

    await page.close()
    return agencies


async def run(headless: bool = True, zone_slugs: list[str] | None = None) -> None:
    """Main entry point — scrape all configured zones and save to JSON."""
    # Load existing state for resumability
    existing = load_agencies(AGENCIES_JSON)
    existing_slugs = {a.slug for a in existing}
    already_scraped_zones: set[str] = set()

    state_path = Path("data/state.json")
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
        already_scraped_zones = set(state.get("pj_scraped_zones", []))

    # Filter zones if requested
    zones = [(q, s) for q, s in ZONES if zone_slugs is None or s in zone_slugs]
    zones_to_do = [(q, s) for q, s in zones if s not in already_scraped_zones]

    if not zones_to_do:
        console.print("[green]All zones already scraped. Nothing to do.[/green]")
        return

    all_agencies: list[Agency] = list(existing)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scraping Pages Jaunes", total=len(zones_to_do))

        async with BrowserSession(headless=headless) as session:
            for zone_query, zone_slug in zones_to_do:
                new_agencies = await _scrape_zone(session, zone_query, zone_slug)
                # Only add agencies not already in the dataset
                for a in new_agencies:
                    if a.slug not in existing_slugs:
                        all_agencies.append(a)
                        existing_slugs.add(a.slug)

                already_scraped_zones.add(zone_slug)
                # Save state after each zone (resumability)
                save_agencies(all_agencies, AGENCIES_JSON)
                with open(state_path, "w") as f:
                    json.dump({"pj_scraped_zones": list(already_scraped_zones)}, f)

                progress.advance(task)
                console.log(f"[green]✓[/green] {zone_slug} — {len(new_agencies)} agencies found")

    console.print(f"[bold green]Pages Jaunes done. Total agencies: {len(all_agencies)}[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Pages Jaunes real estate agencies")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--zones", type=str, default=None, help="Comma-separated zone slugs to scrape")
    args = parser.parse_args()
    zone_slugs = args.zones.split(",") if args.zones else None
    asyncio.run(run(headless=not args.headed, zone_slugs=zone_slugs))
```

- [ ] **Step 5: Run unit tests**

```bash
pytest tests/test_pages_jaunes.py -v
```
Expected: 7 PASSED

- [ ] **Step 6: Manual smoke test (optional, requires network)**

```bash
cd /c/Users/mdrag/Documents/mosaic/immo-scraper
python -m scraper.pages_jaunes_scraper --headed --zones paris-01
```
Expected: browser opens, scrolls Pages Jaunes, saves JSON to `data/agences_immo.json`.

- [ ] **Step 7: Commit**

```bash
git add scraper/ tests/test_pages_jaunes.py
git commit -m "feat: Pages Jaunes scraper with resumable zone state"
```

---

## Chunk 3: Google Maps Scraper

### Task 6: Google Maps scraper

**Files:**
- Create: `immo-scraper/scraper/google_maps_scraper.py`
- Create: `immo-scraper/tests/test_google_maps.py`

- [ ] **Step 1: Write unit tests for parsing helpers**

```python
# tests/test_google_maps.py
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
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_google_maps.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `scraper/google_maps_scraper.py`**

```python
"""
Google Maps scraper — searches "agence immobilière" for each configured zone.

Usage:
    python -m scraper.google_maps_scraper [--headed] [--zones paris-01,paris-02]
"""
from __future__ import annotations
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser import BrowserSession
from config import ZONES, AGENCIES_JSON, SCROLL_DELAY_MIN, SCROLL_DELAY_MAX
from models import Agency
from scraper.pages_jaunes_scraper import parse_network_affiliation, normalize_phone
from utils import load_agencies, save_agencies, random_delay

console = Console()


def parse_rating(raw: str) -> float | None:
    if not raw:
        return None
    cleaned = raw.replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_review_count(raw: str) -> int | None:
    if not raw:
        return None
    m = re.search(r"(\d[\d\s]*)", raw)
    if m:
        return int(m.group(1).replace(" ", ""))
    return None


def parse_opening_hours_text(raw: str) -> dict[str, str]:
    """Convert multiline 'Day: Hours' text to a dict."""
    hours: dict[str, str] = {}
    for line in raw.strip().splitlines():
        if ":" in line:
            day, _, time = line.partition(":")
            hours[day.strip()] = time.strip()
    return hours


async def _scrape_zone(session: BrowserSession, zone_query: str, zone_slug: str) -> list[Agency]:
    agencies: list[Agency] = []
    page = await session.new_page()

    search_url = f"https://www.google.com/maps/search/{quote(zone_query)}"
    console.log(f"[magenta]Google Maps[/magenta] → {zone_query}")

    try:
        await session.navigate(page, search_url)
    except Exception as e:
        console.log(f"[red]Nav error: {e}[/red]")
        await page.close()
        return agencies

    # Scroll through the results list
    results_pane = await page.query_selector("div[role='feed']")
    if not results_pane:
        console.log(f"[yellow]No results pane found for {zone_query}[/yellow]")
        await page.close()
        return agencies

    # Scroll down the list until we hit the end
    prev_count = 0
    for _ in range(30):  # max 30 scrolls
        await results_pane.evaluate("el => el.scrollBy(0, 800)")
        await random_delay(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX)
        items = await page.query_selector_all("div[role='feed'] > div > div > a")
        if len(items) == prev_count:
            break
        prev_count = len(items)

    # Now iterate each result card
    result_links = await page.query_selector_all("div[role='feed'] > div > div > a")
    for link_el in result_links:
        try:
            href = await link_el.get_attribute("href") or ""
            if "maps/place" not in href:
                continue

            # Open detail page in same context
            detail_page = await session.new_page()
            try:
                await session.navigate(detail_page, href)

                # Name
                name_el = await detail_page.query_selector("h1")
                if not name_el:
                    continue
                name = (await name_el.inner_text()).strip()

                # Address
                addr_el = await detail_page.query_selector("button[data-item-id='address']")
                address = (await addr_el.inner_text()).strip() if addr_el else ""

                # Phone
                phone_el = await detail_page.query_selector("button[data-item-id^='phone:tel:']")
                phone_raw = await phone_el.inner_text() if phone_el else None
                phone = normalize_phone(phone_raw)

                # Website
                web_el = await detail_page.query_selector("a[data-item-id='authority']")
                website = await web_el.get_attribute("href") if web_el else None

                # Rating
                rating_el = await detail_page.query_selector("div[jsaction*='pane.rating'] span[aria-hidden='true']")
                rating = parse_rating(await rating_el.inner_text() if rating_el else "")

                # Review count
                review_el = await detail_page.query_selector("div[jsaction*='pane.rating'] button > span")
                review_count = parse_review_count(await review_el.inner_text() if review_el else "")

                # Opening hours
                hours_btn = await detail_page.query_selector("div[jsaction*='openhours']")
                opening_hours = None
                if hours_btn:
                    raw_hours = await hours_btn.inner_text()
                    opening_hours = parse_opening_hours_text(raw_hours)

                agency = Agency(
                    name=name,
                    address=address,
                    source="google_maps",
                    phone=phone,
                    website=website,
                    google_maps_url=href,
                    google_rating=rating,
                    google_review_count=review_count,
                    opening_hours=opening_hours,
                    network_affiliation=parse_network_affiliation(name),
                )
                agencies.append(agency)

            finally:
                await detail_page.close()

            await random_delay(1.5, 3.0)

        except Exception as e:
            console.log(f"[yellow]Card error: {e}[/yellow]")

    await page.close()
    return agencies


async def run(headless: bool = True, zone_slugs: list[str] | None = None) -> None:
    existing = load_agencies(AGENCIES_JSON)
    existing_slugs = {a.slug for a in existing}

    state_path = Path("data/state.json")
    already_scraped_zones: set[str] = set()
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
        already_scraped_zones = set(state.get("gm_scraped_zones", []))

    zones = [(q, s) for q, s in ZONES if zone_slugs is None or s in zone_slugs]
    zones_to_do = [(q, s) for q, s in zones if s not in already_scraped_zones]

    if not zones_to_do:
        console.print("[green]All Google Maps zones already scraped.[/green]")
        return

    all_agencies: list[Agency] = list(existing)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("Scraping Google Maps", total=len(zones_to_do))

        async with BrowserSession(headless=headless) as session:
            for zone_query, zone_slug in zones_to_do:
                new_agencies = await _scrape_zone(session, zone_query, zone_slug)
                for a in new_agencies:
                    if a.slug not in existing_slugs:
                        all_agencies.append(a)
                        existing_slugs.add(a.slug)

                already_scraped_zones.add(zone_slug)
                save_agencies(all_agencies, AGENCIES_JSON)
                # Persist state
                current_state = {}
                if state_path.exists():
                    with open(state_path) as f:
                        current_state = json.load(f)
                current_state["gm_scraped_zones"] = list(already_scraped_zones)
                with open(state_path, "w") as f:
                    json.dump(current_state, f)

                progress.advance(task)
                console.log(f"[green]✓[/green] {zone_slug} — {len(new_agencies)} agencies")

    console.print(f"[bold green]Google Maps done. Total agencies: {len(all_agencies)}[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--zones", type=str, default=None)
    args = parser.parse_args()
    zone_slugs = args.zones.split(",") if args.zones else None
    asyncio.run(run(headless=not args.headed, zone_slugs=zone_slugs))
```

- [ ] **Step 4: Run unit tests**

```bash
pytest tests/test_google_maps.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add scraper/google_maps_scraper.py tests/test_google_maps.py
git commit -m "feat: Google Maps scraper with resumable zone state"
```

---

### Task 7: Deduplication runner

**Files:**
- Create: `immo-scraper/scraper/dedup.py`

> No separate test needed — deduplication logic is already tested in `test_utils.py`. This is just a thin CLI wrapper.

- [ ] **Step 1: Write `scraper/dedup.py`**

```python
"""
Run after both scrapers to merge duplicates.
Usage: python -m scraper.dedup
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from config import AGENCIES_JSON, AGENCIES_CSV
from utils import load_agencies, save_agencies, export_csv, deduplicate_agencies

console = Console()


def run() -> None:
    agencies = load_agencies(AGENCIES_JSON)
    before = len(agencies)
    agencies = deduplicate_agencies(agencies)
    after = len(agencies)
    save_agencies(agencies, AGENCIES_JSON)
    export_csv(agencies, AGENCIES_CSV)
    console.print(f"[bold]Dedup complete.[/bold] {before} → {after} agencies ({before - after} duplicates removed)")
    console.print(f"Saved JSON → [cyan]{AGENCIES_JSON}[/cyan]")
    console.print(f"Saved CSV  → [cyan]{AGENCIES_CSV}[/cyan]")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Commit**

```bash
git add scraper/dedup.py
git commit -m "feat: dedup runner — merge duplicate agencies and export CSV"
```

---

## Chunk 4: Website Enricher

### Task 8: Enricher — website + screenshots

**Files:**
- Create: `immo-scraper/scraper/enricher.py`
- Create: `immo-scraper/tests/test_enricher.py`

- [ ] **Step 1: Write unit tests for site quality heuristic**

```python
# tests/test_enricher.py
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
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_enricher.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `scraper/enricher.py`**

```python
"""
Website enricher — visits agency websites, extracts emails/agents/site quality,
takes homepage screenshots.

Usage:
    python -m scraper.enricher [--headed] [--limit 10]
"""
from __future__ import annotations
import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser import BrowserSession
from config import AGENCIES_JSON, SCREENSHOTS_DIR
from models import Agency, EnrichmentStatus
from utils import extract_emails_from_html, load_agencies, save_agencies, random_delay

console = Console()


# ---------------------------------------------------------------------------
# Site quality heuristic
# ---------------------------------------------------------------------------

def assess_site_quality(html: str) -> str:
    """
    Heuristic-based site quality: 'modern' | 'dated' | 'outdated'.
    - modern: has viewport meta + modern CSS signals (flexbox/grid/tailwind/bootstrap5)
    - outdated: heavy table-based layout
    - dated: has viewport but no modern CSS signals
    """
    html_lower = html.lower()
    has_viewport = 'name="viewport"' in html_lower
    has_modern_css = bool(
        re.search(r'\bflex\b|\bgrid\b|\btailwind\b|\bbootstrap\b', html_lower)
    )
    table_count = html_lower.count("<table")

    if table_count >= 5:
        return "outdated"
    if has_viewport and has_modern_css:
        return "modern"
    return "dated"


# ---------------------------------------------------------------------------
# Agent name extraction
# ---------------------------------------------------------------------------

_TEAM_HEADING_RE = re.compile(
    r'<(?:h[1-4]|div)[^>]*class="[^"]*(?:team|agent|equipe|collaborateur|staff)[^"]*"[^>]*>'
    r'\s*([A-ZÀ-Ÿ][a-zà-ÿ]+ [A-ZÀ-Ÿ][a-zà-ÿ]+)',
    re.IGNORECASE,
)

_H3_NAME_RE = re.compile(
    r'<h3[^>]*>\s*([A-ZÀ-Ÿ][a-zà-ÿ\-]+ [A-ZÀ-Ÿ][a-zà-ÿ\-]+)\s*</h3>',
    re.IGNORECASE,
)


def extract_agent_names_from_html(html: str) -> list[str]:
    """Extract potential agent/director names from HTML."""
    names: list[str] = []
    for m in _TEAM_HEADING_RE.finditer(html):
        names.append(m.group(1).strip())
    for m in _H3_NAME_RE.finditer(html):
        candidate = m.group(1).strip()
        if candidate not in names:
            names.append(candidate)
    return names[:10]  # cap at 10


# ---------------------------------------------------------------------------
# Core enrichment
# ---------------------------------------------------------------------------

async def _enrich_agency(session: BrowserSession, agency: Agency) -> Agency:
    """Visit website, extract data, take screenshot. Returns updated Agency."""
    if not agency.website:
        return agency

    page = await session.new_page()
    try:
        await session.navigate(page, agency.website)
        html = await page.content()

        # Emails
        emails = extract_emails_from_html(html)
        if emails and not agency.email:
            agency.email = emails[0]

        # Agent names
        agency.agents_names = extract_agent_names_from_html(html)

        # Blog detection
        agency.has_blog = bool(re.search(r'/blog|/actualit|/article', html, re.IGNORECASE))

        # Site quality
        agency.site_quality = assess_site_quality(html)

        # Mobile friendly (viewport meta)
        agency.is_mobile_friendly = 'name="viewport"' in html.lower()

        agency.enrichment_status = EnrichmentStatus.ENRICHED

        # Screenshot
        screenshots_path = Path(SCREENSHOTS_DIR)
        screenshots_path.mkdir(exist_ok=True)
        screenshot_file = screenshots_path / f"{agency.slug}.png"
        await page.screenshot(path=str(screenshot_file), full_page=False)
        agency.screenshot_path = str(screenshot_file)
        agency.enrichment_status = EnrichmentStatus.SCREENSHOT_DONE

    except Exception as e:
        console.log(f"[yellow]Enrichment error for {agency.name}: {e}[/yellow]")
    finally:
        await page.close()

    return agency


async def run(headless: bool = True, limit: Optional[int] = None) -> None:
    agencies = load_agencies(AGENCIES_JSON)
    to_enrich = [
        a for a in agencies
        if a.website and a.enrichment_status == EnrichmentStatus.SCRAPED
    ]
    if limit:
        to_enrich = to_enrich[:limit]

    if not to_enrich:
        console.print("[green]Nothing to enrich.[/green]")
        return

    # Build a lookup to update in-place
    agency_map = {a.slug: a for a in agencies}

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("Enriching websites", total=len(to_enrich))

        async with BrowserSession(headless=headless) as session:
            for agency in to_enrich:
                enriched = await _enrich_agency(session, agency)
                agency_map[enriched.slug] = enriched
                # Save after each agency for resumability
                save_agencies(list(agency_map.values()), AGENCIES_JSON)
                progress.advance(task)
                console.log(f"[green]✓[/green] {agency.name} — {agency.enrichment_status}")

    # Mark screenshot_done agencies as ready if they have an email
    final = list(agency_map.values())
    for a in final:
        if a.enrichment_status == EnrichmentStatus.SCREENSHOT_DONE and a.email:
            a.enrichment_status = EnrichmentStatus.READY_FOR_EMAIL
    save_agencies(final, AGENCIES_JSON)
    console.print(f"[bold green]Enrichment complete. {len(to_enrich)} agencies processed.[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(headless=not args.headed, limit=args.limit))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_enricher.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add scraper/enricher.py tests/test_enricher.py
git commit -m "feat: website enricher with email/agent/quality extraction and screenshots"
```

---

## Chunk 5: Email Generation

### Task 9: System prompt + email generator

**Files:**
- Create: `immo-scraper/emails/system_prompt.txt`
- Create: `immo-scraper/emails/generate_emails.py`
- Create: `immo-scraper/tests/test_generate_emails.py`

- [ ] **Step 1: Write `emails/system_prompt.txt`**

```
Tu es un expert en cold email B2B avec un taux de réponse de 35%. Tu écris pour Mosaic, une agence créative spécialisée en photographie et croissance digitale pour l'immobilier.

DONNÉES DE L'AGENCE :
{agency_json}

SCREENSHOT DU SITE WEB :
[image jointe]

RÈGLES STRICTES :
- Analyse le screenshot : identifie les faiblesses visuelles (photos de mauvaise qualité, design dépassé, mauvaise UX mobile, absence de visites virtuelles, images stock génériques)
- L'email doit faire 5 à 7 lignes MAXIMUM
- Ton : professionnel mais humain, direct, pas corporate
- Accroche : une observation spécifique sur LEUR agence (jamais générique)
- Proposition de valeur : comment Mosaic peut concrètement les aider (photographie pro, GBP optimisé, site moderne)
- CTA : proposer un appel de 15 min ou un audit visuel gratuit de leur présence en ligne
- Pas de flatterie creuse, pas de "je me permets de vous contacter..."
- Signature : Mattéo — Mosaic
- Langue : français uniquement

Réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans explications :
{
  "subject": "...",
  "body": "..."
}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_generate_emails.py
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
    # No screenshot — dry run
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
```

- [ ] **Step 3: Run to verify tests fail**

```bash
pytest tests/test_generate_emails.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 4: Write `emails/__init__.py` and `emails/generate_emails.py`**

First create the `__init__.py`:
```bash
touch /c/Users/mdrag/Documents/mosaic/immo-scraper/emails/__init__.py
```

Then write the generator:

```python
"""
Email generator — uses Claude Vision to craft personalized cold emails.

Usage:
    python -m emails.generate_emails [--dry-run] [--limit 5]
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, AGENCIES_JSON, EMAILS_JSON
from models import Agency, EnrichmentStatus
from utils import load_agencies

console = Console()
SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _encode_screenshot(path: str) -> Optional[str]:
    p = Path(path)
    if not p.exists():
        return None
    return base64.standard_b64encode(p.read_bytes()).decode("utf-8")


def build_prompt_messages(agency_data: dict, screenshot_b64: Optional[str]) -> list[dict]:
    system_prompt = load_system_prompt()
    agency_json_str = json.dumps(agency_data, ensure_ascii=False, indent=2)
    user_text = system_prompt.replace("{agency_json}", agency_json_str)

    content: list[dict] = []
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        })
    content.append({"type": "text", "text": user_text})

    return [{"role": "user", "content": content}]


def parse_claude_response(raw: str) -> dict:
    """Extract JSON from Claude response, stripping markdown code fences if present."""
    cleaned = raw.strip()
    # Strip ```json ... ``` fences
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse Claude response as JSON: {e}\nRaw: {raw[:300]}")


def _load_existing_emails(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save_emails(emails: list[dict], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(emails, f, ensure_ascii=False, indent=2)


def run(dry_run: bool = False, limit: Optional[int] = None) -> None:
    agencies = load_agencies(AGENCIES_JSON)
    ready = [a for a in agencies if a.enrichment_status == EnrichmentStatus.READY_FOR_EMAIL]
    if limit:
        ready = ready[:limit]

    if not ready:
        console.print("[yellow]No agencies with status 'ready_for_email'. Run enricher first.[/yellow]")
        return

    existing_emails = _load_existing_emails(EMAILS_JSON)
    already_done = {e["agency_name"] for e in existing_emails}
    to_process = [a for a in ready if a.name not in already_done]

    if not to_process:
        console.print("[green]All ready agencies already have emails generated.[/green]")
        return

    if dry_run:
        console.print(f"[bold yellow]DRY RUN[/bold yellow] — would generate {len(to_process)} emails. No API calls made.")
        for a in to_process[:5]:
            console.print(f"  • {a.name} <{a.email}>")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("Generating emails", total=len(to_process))

        for agency in to_process:
            try:
                screenshot_b64 = _encode_screenshot(agency.screenshot_path) if agency.screenshot_path else None
                messages = build_prompt_messages(agency.model_dump(), screenshot_b64)

                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=1024,
                    messages=messages,
                )
                raw_text = response.content[0].text
                parsed = parse_claude_response(raw_text)

                email_record = {
                    "agency_name": agency.name,
                    "email_to": agency.email,
                    "subject": parsed.get("subject", ""),
                    "body": parsed.get("body", ""),
                    "screenshot_used": agency.screenshot_path or "",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                existing_emails.append(email_record)
                _save_emails(existing_emails, EMAILS_JSON)
                console.log(f"[green]✓[/green] Email generated for {agency.name}")

            except Exception as e:
                console.log(f"[red]Error for {agency.name}: {e}[/red]")

            progress.advance(task)

    console.print(f"[bold green]Done. {len(existing_emails)} total emails in {EMAILS_JSON}[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate personalized cold emails via Claude Vision")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without API calls")
    parser.add_argument("--limit", type=int, default=None, help="Process only N agencies")
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_generate_emails.py -v
```
Expected: 6 PASSED

- [ ] **Step 6: Commit**

```bash
git add emails/ tests/test_generate_emails.py
git commit -m "feat: email generator with Claude Vision and dry-run mode"
```

---

### Task 10: Final integration — README and full pipeline smoke test

**Files:**
- Create: `immo-scraper/README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Immo Scraper — Mosaic Prospecting Pipeline

Full pipeline: scrape → enrich → screenshot → generate cold emails via Claude Vision.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Fill in your ANTHROPIC_API_KEY in .env
```

## Pipeline (run in order)

```bash
# 1. Scrape Pages Jaunes (simpler, start here)
python -m scraper.pages_jaunes_scraper [--headed] [--zones paris-01,paris-02]

# 2. Scrape Google Maps
python -m scraper.google_maps_scraper [--headed] [--zones paris-01]

# 3. Deduplicate & export CSV
python -m scraper.dedup

# 4. Enrich websites + take screenshots
python -m scraper.enricher [--headed] [--limit 20]

# 5. Generate personalized emails
python -m emails.generate_emails [--dry-run] [--limit 5]
```

## Outputs

| File | Description |
|------|-------------|
| `data/agences_immo.json` | All agencies (source of truth) |
| `data/agences_immo.csv` | Same data in CSV |
| `data/emails_generated.json` | Generated cold emails |
| `screenshots/{slug}.png` | Homepage screenshots |
| `data/state.json` | Resumability checkpoint |

## Resumability

If the scraper crashes, re-run the same command. It reads `data/state.json` to skip already-scraped zones. Enrichment also skips agencies not in `scraped` status.

## Adding Zones

Edit `config.py` — add entries to the `ZONES` list as `("query string", "slug")` tuples.
```

- [ ] **Step 2: Run the full test suite**

```bash
cd /c/Users/mdrag/Documents/mosaic/immo-scraper
pytest tests/ -v
```
Expected: all tests PASSED (models, utils, browser, pages_jaunes, google_maps, enricher, generate_emails)

- [ ] **Step 3: Final commit**

```bash
git add README.md
git commit -m "docs: add README with full pipeline usage guide"
```

---

## Summary

| Stage | Command | Resumes? |
|-------|---------|---------|
| Pages Jaunes scrape | `python -m scraper.pages_jaunes_scraper` | ✅ via `state.json` |
| Google Maps scrape | `python -m scraper.google_maps_scraper` | ✅ via `state.json` |
| Dedup + CSV export | `python -m scraper.dedup` | N/A (idempotent) |
| Website enrichment | `python -m scraper.enricher` | ✅ skips enriched agencies |
| Email generation | `python -m emails.generate_emails` | ✅ skips already-generated |

> **Note on model ID:** `config.py` uses `claude-sonnet-4-6` (the current Sonnet model). The spec referenced `claude-sonnet-4-20250514` which is not a valid model ID — update `CLAUDE_MODEL` in `config.py` if Anthropic releases a new model ID.
