"""
Linkup enricher — uses the Linkup search API to discover missing data
for agencies: email, director name, social media, tech stack, etc.

Fills gaps that Google Maps and website scraping can't reach by searching
the open web with structured output.

Usage:
    python -m scraper.linkup_enricher [--limit 20] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AGENCIES_JSON, LINKUP_API_KEY
from models import Agency
from scraper.lead_scorer import score_all
from utils import load_agencies, save_agencies

console = Console(legacy_windows=False)

# ---------------------------------------------------------------------------
# Rate limiting — be respectful to the API
# ---------------------------------------------------------------------------
LINKUP_DELAY_SECONDS: float = 1.0  # pause between API calls


# ---------------------------------------------------------------------------
# Structured output schemas for Linkup
# ---------------------------------------------------------------------------

class AgencyWebInfo(BaseModel):
    """Structured data extracted from Linkup search about a real-estate agency."""
    email: Optional[str] = Field(None, description="Contact email address of the agency")
    director_name: Optional[str] = Field(None, description="Name of the agency director or manager")
    phone: Optional[str] = Field(None, description="Phone number if different from known")
    instagram_url: Optional[str] = Field(None, description="Instagram profile URL")
    facebook_url: Optional[str] = Field(None, description="Facebook page URL")
    linkedin_url: Optional[str] = Field(None, description="LinkedIn page URL")
    website_tech: Optional[str] = Field(
        None,
        description="Website technology/CMS detected (e.g. WordPress, Wix, Squarespace, custom)"
    )
    year_founded: Optional[int] = Field(None, description="Year the agency was founded or registered")
    description: Optional[str] = Field(
        None,
        description="Short 1-sentence description of the agency and its specialties"
    )


# ---------------------------------------------------------------------------
# New fields to add to models.py via the enricher
# ---------------------------------------------------------------------------
_LINKUP_FIELDS = [
    "director_name", "instagram_url", "facebook_url",
    "linkedin_url", "website_tech", "year_founded",
    "linkup_description",
]


def _build_query(agency: Agency) -> str:
    """Build a targeted search query for an agency."""
    parts = [f'"{agency.name}"']
    if agency.address:
        # Extract city/postal from address
        parts.append(agency.address.split(",")[-1].strip() if "," in agency.address else agency.address)
    parts.append("agence immobilière")
    parts.append("contact email dirigeant")
    return " ".join(parts)


def _needs_linkup(agency: Agency) -> bool:
    """Check if an agency would benefit from Linkup enrichment."""
    missing = 0
    if not agency.email:
        missing += 1
    if not getattr(agency, "director_name", None):
        missing += 1
    if not getattr(agency, "instagram_url", None):
        missing += 1
    if not getattr(agency, "facebook_url", None):
        missing += 1
    if not getattr(agency, "linkedin_url", None):
        missing += 1
    if not getattr(agency, "website_tech", None):
        missing += 1
    # Only worth calling API if at least 2 fields are missing
    return missing >= 2


def _apply_linkup_data(agency: Agency, info: AgencyWebInfo) -> tuple[Agency, list[str]]:
    """Apply Linkup results to an agency, only filling blanks. Returns (agency, list of filled fields)."""
    filled: list[str] = []

    if info.email and not agency.email:
        agency.email = info.email
        filled.append("email")

    if info.director_name and not getattr(agency, "director_name", None):
        agency.director_name = info.director_name  # type: ignore[attr-defined]
        filled.append("director_name")

    if info.phone and not agency.phone:
        agency.phone = info.phone
        filled.append("phone")

    if info.instagram_url and not getattr(agency, "instagram_url", None):
        agency.instagram_url = info.instagram_url  # type: ignore[attr-defined]
        filled.append("instagram_url")

    if info.facebook_url and not getattr(agency, "facebook_url", None):
        agency.facebook_url = info.facebook_url  # type: ignore[attr-defined]
        filled.append("facebook_url")

    if info.linkedin_url and not getattr(agency, "linkedin_url", None):
        agency.linkedin_url = info.linkedin_url  # type: ignore[attr-defined]
        filled.append("linkedin_url")

    if info.website_tech and not getattr(agency, "website_tech", None):
        agency.website_tech = info.website_tech  # type: ignore[attr-defined]
        filled.append("website_tech")

    if info.year_founded and not getattr(agency, "year_founded", None):
        agency.year_founded = info.year_founded  # type: ignore[attr-defined]
        filled.append("year_founded")

    if info.description and not getattr(agency, "linkup_description", None):
        agency.linkup_description = info.description  # type: ignore[attr-defined]
        filled.append("description")

    return agency, filled


def enrich_agency_via_linkup(client, agency: Agency, dry_run: bool = False) -> tuple[Agency, list[str]]:
    """Search Linkup for an agency and fill missing fields. Returns (agency, filled_fields)."""
    query = _build_query(agency)

    if dry_run:
        console.log(f"[dim]  DRY RUN query: {query}[/dim]")
        return agency, []

    try:
        response = client.search(
            query=query,
            depth="standard",
            output_type="structured",
            structured_output_schema=AgencyWebInfo,
        )
        # response.data is the parsed AgencyWebInfo
        info: AgencyWebInfo = response.data if hasattr(response, "data") else response
        return _apply_linkup_data(agency, info)
    except Exception as e:
        console.log(f"[yellow]  Linkup error for {agency.name}: {e}[/yellow]")
        return agency, []


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run(limit: int | None = None, dry_run: bool = False) -> None:
    if not LINKUP_API_KEY and not dry_run:
        console.print("[red]LINKUP_API_KEY not set. Add it to .env or environment.[/red]")
        return

    from linkup import LinkupClient
    client = LinkupClient(api_key=LINKUP_API_KEY) if not dry_run else None

    agencies = load_agencies(AGENCIES_JSON)
    if not agencies:
        console.print("[red]No agencies found.[/red]")
        return

    # Filter to agencies that need enrichment, prioritize by lead score (best leads first)
    candidates = [a for a in agencies if _needs_linkup(a)]
    candidates.sort(key=lambda a: a.lead_score or 0, reverse=True)

    if limit:
        candidates = candidates[:limit]

    console.print(
        f"[cyan]Linkup enrichment: {len(candidates)} agencies to process"
        f"{' (DRY RUN)' if dry_run else ''}[/cyan]"
    )

    # Build slug -> agency map for in-place updates
    agency_map = {a.slug: a for a in agencies}
    stats = {"total": 0, "enriched": 0, "fields_filled": 0}

    table = Table(title="Linkup Enrichment Results", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Agency", max_width=30)
    table.add_column("Score", style="cyan", width=6)
    table.add_column("Fields Filled", style="green", max_width=40)

    for i, agency in enumerate(candidates, 1):
        stats["total"] += 1
        console.log(f"[dim]  [{i}/{len(candidates)}] {agency.name}[/dim]")

        enriched, filled = enrich_agency_via_linkup(client, agency, dry_run=dry_run)
        agency_map[enriched.slug] = enriched

        if filled:
            stats["enriched"] += 1
            stats["fields_filled"] += len(filled)

        table.add_row(
            str(i),
            agency.name[:30],
            f"{agency.lead_score:.0f}" if agency.lead_score else "—",
            ", ".join(filled) if filled else "—",
        )

        # Save periodically (every 10 agencies)
        if i % 10 == 0 and not dry_run:
            save_agencies(list(agency_map.values()), AGENCIES_JSON)

        # Rate limit
        if not dry_run and i < len(candidates):
            time.sleep(LINKUP_DELAY_SECONDS)

    # Final save + re-score
    if not dry_run:
        final = list(agency_map.values())
        score_all(final)
        save_agencies(final, AGENCIES_JSON)

    console.print(table)
    console.print(
        f"\n[bold green]Done.[/bold green] "
        f"{stats['enriched']}/{stats['total']} agencies enriched, "
        f"{stats['fields_filled']} fields filled."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich agencies via Linkup web search")
    parser.add_argument("--limit", type=int, default=20, help="Max agencies to process")
    parser.add_argument("--dry-run", action="store_true", help="Show queries without calling API")
    args = parser.parse_args()
    run(limit=args.limit, dry_run=args.dry_run)
