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
from urllib.parse import quote, quote_plus
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

console = Console(legacy_windows=False)

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

    # Extract location from query (e.g. "agence immobilière Paris 13" -> "Paris 13")
    location = zone_query.replace("agence immobilière ", "").strip()
    quoi = quote_plus("agences immobilières")
    ou = quote_plus(location)
    url = f"https://www.pagesjaunes.fr/annuaire/chercher?quoi={quoi}&ou={ou}"

    location = zone_query.replace("agence immobilière ", "").strip()
    console.log(f"[cyan]Pages Jaunes[/cyan] >> {location}")
    try:
        # Navigate to homepage
        await page.goto("https://www.pagesjaunes.fr/", wait_until="networkidle", timeout=30_000)
        await random_delay(1.0, 2.0)
        # Accept cookies — handle AppConsent iframe
        try:
            consent_frame = None
            for frame in page.frames:
                if "appconsent" in frame.url or "consent" in frame.url:
                    consent_frame = frame
                    break
            if not consent_frame:
                # Try via iframe element
                iframe_el = await page.query_selector("iframe#appconsent, iframe[title*='consentement'], iframe[title*='consent']")
                if iframe_el:
                    consent_frame = await iframe_el.content_frame()
            if consent_frame:
                accept_btn = await consent_frame.query_selector("button.acceptAll, button[id*='accept'], .ac-acceptAll, button.agree")
                if not accept_btn:
                    # Try any button with "accept" or "accepter" text
                    buttons = await consent_frame.query_selector_all("button")
                    for btn in buttons:
                        txt = (await btn.inner_text()).lower()
                        if "accept" in txt or "tout" in txt or "agree" in txt:
                            accept_btn = btn
                            break
                if accept_btn:
                    await accept_btn.click()
                    await random_delay(1.0, 2.0)
                    console.log("[cyan]Cookie banner dismissed[/cyan]")
        except Exception as e:
            console.log(f"[yellow]Cookie banner: {e}[/yellow]")
        # Fill quoi field (id=quoiqui)
        quoi_input = await page.query_selector("input#quoiqui")
        if quoi_input:
            await quoi_input.click()
            await quoi_input.fill("agences immobilières")
        # Fill ou field (id=ou) and wait for autocomplete, then select first suggestion
        ou_input = await page.query_selector("input#ou")
        if ou_input:
            await ou_input.click()
            await ou_input.type(location, delay=80)  # type slowly to trigger autocomplete
            await random_delay(1.5, 2.5)
            await random_delay(1.5, 2.5)
            # Target the 'ou' autocomplete specifically
            suggestion = await page.query_selector(".autocomplete-suggestions.acou .autocomplete-suggestion:not(.autourdemoi)")
            if not suggestion:
                suggestion = await page.query_selector(".acou .autocomplete-suggestion")
            if suggestion:
                await suggestion.click()
                await random_delay(0.5, 1.0)
                console.log("[cyan]OU autocomplete suggestion selected[/cyan]")
            # Now submit the form via JS (bypass hidden button)
            await page.evaluate("""
                const btn = document.querySelector('button[data-pjstats*=TROUVER]');
                if (btn) btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            """)
        await page.wait_for_load_state("networkidle", timeout=30_000)
        await random_delay(1.0, 2.0)
        console.log(f"[cyan]After search URL:[/cyan] {page.url}")
    except Exception as e:
        console.log(f"[red]Nav error for {zone_query}: {e}[/red]")
        await page.close()
        return agencies

    page_num = 1
    while True:
        await random_delay(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX)

        cards = await page.query_selector_all("div.bi-content")
        if not cards:
            # Debug: dump title and first 2000 chars of body text
            title = await page.title()
            body_text = await page.evaluate("document.body.innerText")
            html_source = await page.content()
            console.log(f"[yellow]No cards found. Title: {title}[/yellow]")
            console.log(f"[yellow]URL final: {page.url}[/yellow]")
            console.log(f"[yellow]Body: {body_text[:800]}[/yellow]")
            # Save HTML for inspection
            with open("data/debug_pj.html", "w", encoding="utf-8") as f:
                f.write(html_source)
            break

        for card in cards:
            try:
                name_el = await card.query_selector("a.denomination-links span")
                if not name_el:
                    continue
                name = (await name_el.inner_text()).strip()

                address_el = await card.query_selector("span.adresse")
                address = (await address_el.inner_text()).strip() if address_el else ""

                phone_el = await card.query_selector("a[href^='tel:']")
                phone_raw = await phone_el.get_attribute("href") if phone_el else None
                phone = normalize_phone(phone_raw.replace("tel:", "") if phone_raw else None)

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
    existing = load_agencies(AGENCIES_JSON)
    existing_slugs = {a.slug for a in existing}
    already_scraped_zones: set[str] = set()

    state_path = Path("data/state.json")
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
        already_scraped_zones = set(state.get("pj_scraped_zones", []))

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
                for a in new_agencies:
                    if a.slug not in existing_slugs:
                        all_agencies.append(a)
                        existing_slugs.add(a.slug)

                already_scraped_zones.add(zone_slug)
                save_agencies(all_agencies, AGENCIES_JSON)
                with open(state_path, "w") as f:
                    json.dump({"pj_scraped_zones": list(already_scraped_zones)}, f)

                progress.advance(task)
                console.log(f"[green]OK[/green] {zone_slug} -- {len(new_agencies)} agencies found")

    console.print(f"[bold green]Pages Jaunes done. Total agencies: {len(all_agencies)}[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Pages Jaunes real estate agencies")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--zones", type=str, default=None, help="Comma-separated zone slugs to scrape")
    args = parser.parse_args()
    zone_slugs = args.zones.split(",") if args.zones else None
    asyncio.run(run(headless=not args.headed, zone_slugs=zone_slugs))
