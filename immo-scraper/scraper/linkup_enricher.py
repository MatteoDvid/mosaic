"""
Linkup enricher — uses the Linkup search API to discover missing data
for agencies: email, director name, social media, tech stack, etc.

Uses sourcedAnswer mode (richer results) then parses the answer text
to extract structured fields.

Usage:
    python -m scraper.linkup_enricher [--limit 20] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

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
# Config
# ---------------------------------------------------------------------------
LINKUP_DELAY_SECONDS: float = 2.0


# ---------------------------------------------------------------------------
# Structured schema (used for final parsing)
# ---------------------------------------------------------------------------

class AgencyWebInfo(BaseModel):
    """Structured data extracted about a real-estate agency."""
    email: Optional[str] = Field(None, description="Contact email address")
    director_name: Optional[str] = Field(None, description="Name of the director/manager")
    phone: Optional[str] = Field(None, description="Phone number")
    instagram_url: Optional[str] = Field(None, description="Instagram profile URL")
    facebook_url: Optional[str] = Field(None, description="Facebook page URL")
    linkedin_url: Optional[str] = Field(None, description="LinkedIn page URL")
    website_tech: Optional[str] = Field(None, description="CMS/tech: WordPress, Wix, etc.")
    year_founded: Optional[int] = Field(None, description="Year the agency was founded")
    description: Optional[str] = Field(None, description="1-sentence description")


# ---------------------------------------------------------------------------
# Text parsing — extract fields from Linkup's sourcedAnswer text
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:0[1-9][\s.]?\d{2}[\s.]?\d{2}[\s.]?\d{2}[\s.]?\d{2}|\+33\s?\d[\s.]?\d{2}[\s.]?\d{2}[\s.]?\d{2}[\s.]?\d{2})")
_URL_RE = re.compile(r"https?://[^\s\)\]\"',]+")


def _extract_social(text: str, domain: str) -> str | None:
    """Extract first URL containing domain from text."""
    for url in _URL_RE.findall(text):
        if domain in url.lower():
            return url.rstrip(".")
    return None


def _extract_name_after_keywords(text: str) -> str | None:
    """Extract a person name after keywords like 'dirigeant', 'gérant', 'fondé par'."""
    patterns = [
        r"(?:dirigeant|gérant|directeur|directrice|fondateur|fondatrice|fondée?\s+par|dirigée?\s+par)\s*(?::?\s*)([A-ZÀ-Ÿ][a-zà-ÿ\-]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ\-]+)+)",
        r"(?:Mme|Mr|M\.)\s+([A-ZÀ-Ÿ][a-zà-ÿ\-]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ\-]+)+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # Filter out obviously wrong matches (too many words = sentence fragment)
            if len(name.split()) <= 4:
                return name
    return None


def _extract_year(text: str) -> int | None:
    """Extract founding year from text."""
    patterns = [
        r"(?:fondée?|créée?|établie?)\s+(?:en\s+)?(\d{4})",
        r"(?:depuis|en)\s+(\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            if 1900 <= year <= 2026:
                return year
    return None


def parse_sourced_answer(text: str) -> AgencyWebInfo:
    """Parse a Linkup sourcedAnswer text into structured fields."""
    emails = _EMAIL_RE.findall(text)
    phones = _PHONE_RE.findall(text)

    # Filter out file-like emails
    skip_ext = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js"}
    emails = [e for e in emails if not any(e.lower().endswith(ext) for ext in skip_ext)]

    return AgencyWebInfo(
        email=emails[0] if emails else None,
        director_name=_extract_name_after_keywords(text),
        phone=phones[0] if phones else None,
        instagram_url=_extract_social(text, "instagram.com"),
        facebook_url=_extract_social(text, "facebook.com"),
        linkedin_url=_extract_social(text, "linkedin.com"),
        website_tech=None,  # hard to extract from text, skip
        year_founded=_extract_year(text),
        description=None,  # we'll use the full answer as description if short enough
    )


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

def _build_query(agency: Agency) -> str:
    """Build a targeted search query."""
    parts = [f'"{agency.name}"']

    if agency.website:
        domain = urlparse(agency.website).netloc
        if domain:
            parts.append(domain)

    if agency.address:
        postal = re.search(r"\b(75\d{3}|9[234]\d{3})\b", agency.address)
        if postal:
            parts.append(postal.group(0))

    parts.append("email contact dirigeant gérant réseaux sociaux Instagram Facebook LinkedIn")
    return " ".join(parts)


def _needs_linkup(agency: Agency) -> bool:
    """Check if an agency would benefit from Linkup enrichment."""
    missing = 0
    if not agency.email:
        missing += 1
    if not agency.director_name:
        missing += 1
    if not agency.instagram_url:
        missing += 1
    if not agency.facebook_url:
        missing += 1
    if not agency.linkedin_url:
        missing += 1
    if not agency.website_tech:
        missing += 1
    return missing >= 2


def _apply_linkup_data(agency: Agency, info: AgencyWebInfo) -> tuple[Agency, list[str]]:
    """Apply Linkup results to agency, only filling blanks."""
    filled: list[str] = []

    if info.email and not agency.email:
        agency.email = info.email
        filled.append("email")

    if info.director_name and not agency.director_name:
        agency.director_name = info.director_name
        filled.append("director_name")

    if info.phone and not agency.phone:
        agency.phone = info.phone
        filled.append("phone")

    if info.instagram_url and not agency.instagram_url:
        agency.instagram_url = info.instagram_url
        filled.append("instagram")

    if info.facebook_url and not agency.facebook_url:
        agency.facebook_url = info.facebook_url
        filled.append("facebook")

    if info.linkedin_url and not agency.linkedin_url:
        agency.linkedin_url = info.linkedin_url
        filled.append("linkedin")

    if info.website_tech and not agency.website_tech:
        agency.website_tech = info.website_tech
        filled.append("website_tech")

    if info.year_founded and not agency.year_founded:
        agency.year_founded = info.year_founded
        filled.append("year_founded")

    if info.description and not agency.linkup_description:
        agency.linkup_description = info.description
        filled.append("description")

    return agency, filled


# ---------------------------------------------------------------------------
# Core enrichment function
# ---------------------------------------------------------------------------

def enrich_agency_via_linkup(client, agency: Agency, dry_run: bool = False) -> tuple[Agency, list[str]]:
    """Search Linkup for agency info and fill missing fields."""
    query = _build_query(agency)

    if dry_run:
        console.log(f"[dim]  DRY RUN query: {query[:100]}[/dim]")
        return agency, []

    console.log(f"[dim]  query: {query[:100]}[/dim]")

    for attempt in range(1, 4):
        try:
            response = client.search(
                query=query,
                depth="deep",
                output_type="sourcedAnswer",
            )

            answer = response.answer if hasattr(response, "answer") else str(response)
            sources = response.sources if hasattr(response, "sources") else []

            # Parse the answer text into structured fields
            info = parse_sourced_answer(answer)

            # Also check source URLs for social media links
            for src in sources:
                url = getattr(src, "url", "") or ""
                if "facebook.com" in url and not info.facebook_url:
                    info.facebook_url = url
                if "instagram.com" in url and not info.instagram_url:
                    info.instagram_url = url
                if "linkedin.com" in url and not info.linkedin_url:
                    info.linkedin_url = url

            # Use first 200 chars of answer as description
            if answer and len(answer) > 20:
                info.description = answer[:200].replace("\n", " ").strip()

            found = [k for k, v in info.model_dump().items() if v is not None]
            console.log(f"[dim]  found: {', '.join(found) if found else 'nothing'}[/dim]")

            return _apply_linkup_data(agency, info)

        except Exception as e:
            if "SSL" in str(e) and attempt < 3:
                console.log(f"[yellow]  SSL error (attempt {attempt}/3), retrying...[/yellow]")
                time.sleep(2 * attempt)
                continue
            console.log(f"[yellow]  Linkup error for {agency.name}: {e}[/yellow]")
            return agency, []

    return agency, []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run(limit: int | None = None, dry_run: bool = False) -> None:
    if not LINKUP_API_KEY and not dry_run:
        console.print("[red]LINKUP_API_KEY not set. Add it to .env or environment.[/red]")
        return

    import ssl
    import httpx
    from linkup import LinkupClient

    # Work around SSL cert issues in sandboxed environments
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    http_client = httpx.Client(verify=ssl_ctx)

    client = LinkupClient(api_key=LINKUP_API_KEY) if not dry_run else None
    if client is not None:
        client._client = http_client  # type: ignore[attr-defined]

    agencies = load_agencies(AGENCIES_JSON)
    if not agencies:
        console.print("[red]No agencies found.[/red]")
        return

    # Deduplicate by slug, filter, sort by lead score (best leads first)
    seen_slugs: set[str] = set()
    candidates: list[Agency] = []
    for a in agencies:
        if a.slug not in seen_slugs and _needs_linkup(a):
            candidates.append(a)
            seen_slugs.add(a.slug)
    candidates.sort(key=lambda a: a.lead_score or 0, reverse=True)

    if limit:
        candidates = candidates[:limit]

    console.print(
        f"[cyan]Linkup enrichment: {len(candidates)} agencies to process"
        f"{' (DRY RUN)' if dry_run else ''}[/cyan]"
    )

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

        if i % 10 == 0 and not dry_run:
            save_agencies(list(agency_map.values()), AGENCIES_JSON)

        if not dry_run and i < len(candidates):
            time.sleep(LINKUP_DELAY_SECONDS)

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
