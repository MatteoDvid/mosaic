"""
SIRENE scraper — fetches real estate agencies from the French official
business registry (data.gouv.fr / INSEE SIRENE) via the public API.

No browser needed. No anti-bot issues. Free, no API key required.

NAF code 6831Z / 68.31Z = Agences immobilières

Usage:
    python -m scraper.sirene_scraper [--zones paris-13,paris-14]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AGENCIES_JSON, STATE_JSON, ZONES
from models import Agency, EnrichmentStatus, _slugify
from scraper.pages_jaunes_scraper import parse_network_affiliation
from utils import deduplicate_agencies, load_agencies, save_agencies

_LOWERCASE_FR = {"de", "du", "des", "la", "le", "les", "et", "en", "sur", "sous", "par"}


def _title_case(name: str) -> str:
    """Convert ALL CAPS SIRENE name to Title Case, lowercasing French articles mid-string."""
    words = name.split()
    result = []
    for i, word in enumerate(words):
        low = word.lower()
        if i == 0 or low not in _LOWERCASE_FR:
            result.append(word.capitalize())
        else:
            result.append(low)
    return " ".join(result)

console = Console(legacy_windows=False)

_API_BASE = "https://recherche-entreprises.api.gouv.fr/search"
_NAF_CODE = "68.31Z"
_PER_PAGE = 25
_HEADERS = {"User-Agent": "Mosaic-Scraper/1.0 (contact@mosaic.fr)"}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _api_get(url: str, retries: int = 3) -> dict:
    """Synchronous GET with retry on transient errors."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            raise
    return {}


def _fetch_all_pages(postal_code: str) -> list[dict]:
    """Paginate through all results for a given postal code."""
    url = f"{_API_BASE}?activite_principale={_NAF_CODE}&code_postal={postal_code}&per_page={_PER_PAGE}&page=1"
    first = _api_get(url)
    total = first.get("total_results", 0)
    results = list(first.get("results", []))

    pages = (total + _PER_PAGE - 1) // _PER_PAGE
    for page in range(2, pages + 1):
        url = f"{_API_BASE}?activite_principale={_NAF_CODE}&code_postal={postal_code}&per_page={_PER_PAGE}&page={page}"
        data = _api_get(url)
        results.extend(data.get("results", []))
        time.sleep(0.15)  # polite rate-limit

    return results


# ---------------------------------------------------------------------------
# Agency extraction
# ---------------------------------------------------------------------------

def _best_name(company: dict, etab: dict) -> str:
    """Pick the best display name: enseigne > nom_commercial > nom_complet."""
    enseignes = etab.get("liste_enseignes") or []
    if enseignes:
        return enseignes[0].strip()
    nom_commercial = etab.get("nom_commercial") or ""
    if nom_commercial:
        return nom_commercial.strip()
    return company.get("nom_complet", "").strip()


def _extract_agencies(company: dict, postal_code: str) -> list[Agency]:
    """Turn a company + its matching establishments into Agency objects."""
    agencies: list[Agency] = []
    matching = company.get("matching_etablissements") or []

    # If matching_etablissements is empty, fall back to siege if it's in the postal code
    if not matching:
        siege = company.get("siege", {})
        if siege.get("code_postal") == postal_code and siege.get("etat_administratif") == "A":
            matching = [siege]

    for etab in matching:
        # Only active establishments in our target postal code
        if etab.get("etat_administratif") != "A":
            continue
        if etab.get("code_postal") != postal_code:
            continue

        name = _title_case(_best_name(company, etab))
        if not name:
            continue

        address = etab.get("adresse") or etab.get("geo_adresse") or ""
        siret = etab.get("siret", "")

        # Use SIRET suffix in slug so multi-office companies are not collapsed
        slug = _slugify(name)
        if siret:
            slug = f"{slug}-{siret[-5:]}"

        agency = Agency(
            name=name,
            slug=slug,
            address=address,
            source="sirene",
            siret=siret or None,
            network_affiliation=parse_network_affiliation(name),
        )
        agencies.append(agency)

    return agencies


# ---------------------------------------------------------------------------
# Zone scraper
# ---------------------------------------------------------------------------

def _scrape_zone(label: str, postal_code: str) -> list[Agency]:
    """Fetch all active real-estate agencies for a postal code via SIRENE API."""
    console.log(f"[cyan]SIRENE[/cyan] >> {label} ({postal_code})")
    try:
        companies = _fetch_all_pages(postal_code)
    except Exception as e:
        console.log(f"[red]API error for {postal_code}: {e}[/red]")
        return []

    agencies: list[Agency] = []
    seen_slugs: set[str] = set()
    for company in companies:
        for agency in _extract_agencies(company, postal_code):
            if agency.slug not in seen_slugs:
                agencies.append(agency)
                seen_slugs.add(agency.slug)

    return agencies


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(zone_slugs: list[str] | None = None) -> None:
    """Scrape all configured zones and save to JSON. Resumable via state.json."""
    existing = load_agencies(AGENCIES_JSON)
    existing_slugs = {a.slug for a in existing}

    state_path = Path(STATE_JSON)
    already_scraped: set[str] = set()
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
        already_scraped = set(state.get("sirene_scraped_zones", []))

    zones = [(label, slug, cp) for label, slug, cp in ZONES
             if zone_slugs is None or slug in zone_slugs]
    to_do = [(label, slug, cp) for label, slug, cp in zones
             if slug not in already_scraped]

    if not to_do:
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
        task = progress.add_task("Scraping SIRENE", total=len(to_do))

        for label, slug, postal_code in to_do:
            new_agencies = _scrape_zone(label, postal_code)

            added = 0
            for a in new_agencies:
                if a.slug not in existing_slugs:
                    all_agencies.append(a)
                    existing_slugs.add(a.slug)
                    added += 1

            already_scraped.add(slug)
            # Save state after each zone
            save_agencies(all_agencies, AGENCIES_JSON)
            current_state: dict = {}
            if state_path.exists():
                with open(state_path) as f:
                    current_state = json.load(f)
            current_state["sirene_scraped_zones"] = list(already_scraped)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(state_path, "w") as f:
                json.dump(current_state, f)

            progress.advance(task)
            console.log(f"[green]OK[/green] {label} -- {added} new agencies ({len(new_agencies)} found)")

    # Final dedup pass
    all_agencies = deduplicate_agencies(all_agencies)
    save_agencies(all_agencies, AGENCIES_JSON)
    console.print(f"[bold green]SIRENE done. Total unique agencies: {len(all_agencies)}[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape French real estate agencies via SIRENE API")
    parser.add_argument("--zones", type=str, default=None, help="Comma-separated zone slugs")
    args = parser.parse_args()
    zone_slugs = args.zones.split(",") if args.zones else None
    run(zone_slugs=zone_slugs)
