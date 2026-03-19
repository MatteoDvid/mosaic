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

console = Console(legacy_windows=False)


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

        emails = extract_emails_from_html(html)
        if emails and not agency.email:
            agency.email = emails[0]

        agency.agents_names = extract_agent_names_from_html(html)
        agency.has_blog = bool(re.search(r'/blog|/actualit|/article', html, re.IGNORECASE))
        agency.site_quality = assess_site_quality(html)
        agency.is_mobile_friendly = 'name="viewport"' in html.lower()
        agency.enrichment_status = EnrichmentStatus.ENRICHED

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

    agency_map = {a.slug: a for a in agencies}

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("Enriching websites", total=len(to_enrich))

        async with BrowserSession(headless=headless) as session:
            for agency in to_enrich:
                enriched = await _enrich_agency(session, agency)
                agency_map[enriched.slug] = enriched
                save_agencies(list(agency_map.values()), AGENCIES_JSON)
                progress.advance(task)
                console.log(f"[green]OK[/green] {agency.name} -- {agency.enrichment_status}")

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
