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
from config import ZONES, ZONES_GEO, AGENCIES_JSON, SCROLL_DELAY_MIN, SCROLL_DELAY_MAX
from models import Agency
from scraper.pages_jaunes_scraper import parse_network_affiliation, normalize_phone
from utils import load_agencies, save_agencies, random_delay

console = Console(legacy_windows=False)

# Concurrency limit for detail page fetches
MAX_CONCURRENT_DETAILS = 3
# Retry config for detail page fetches
DETAIL_MAX_RETRIES = 2
DETAIL_RETRY_DELAY = 3.0


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
        return int(m.group(1).replace(" ", "").replace("\u202f", ""))
    return None


def parse_opening_hours_text(raw: str) -> dict[str, str]:
    """Convert multiline 'Day: Hours' text to a dict."""
    hours: dict[str, str] = {}
    for line in raw.strip().splitlines():
        if ":" in line:
            day, _, time = line.partition(":")
            hours[day.strip()] = time.strip()
    return hours


def extract_gbp_photo_count(aria_or_text: str) -> int | None:
    """Extract photo count from Google Maps photo button label."""
    if not aria_or_text:
        return None
    m = re.search(r"(\d[\d\s]*)\s*photo", aria_or_text, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(" ", "").replace("\u202f", ""))
    return None


def extract_gbp_category(raw: str) -> str | None:
    """Clean up a GBP category string."""
    if not raw:
        return None
    cleaned = raw.strip()
    return cleaned if cleaned else None


async def _accept_google_consent(page) -> None:
    """Click through Google's consent page if present."""
    try:
        for selector in [
            "button[aria-label*='Tout accepter']",
            "button[aria-label*='Accept all']",
            "button[aria-label*='Accept']",
            "button[aria-label*='Accepter']",
            # Text-based fallback: look for buttons with consent text
            "form[action*='consent'] button",
            # GDPR-style cookie banners
            "button:has-text('Tout accepter')",
            "button:has-text('Accept all')",
        ]:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                    console.log("[cyan]Google consent accepted[/cyan]")
                    return
            except Exception:
                continue
    except Exception:
        pass


def _grid_points(lat_min: float, lat_max: float, lng_min: float, lng_max: float,
                 rows: int = 3, cols: int = 3) -> list[tuple[float, float]]:
    """Generate evenly-spaced (lat, lng) points covering a bounding box."""
    lats = [lat_min + (lat_max - lat_min) * i / (rows - 1) for i in range(rows)]
    lngs = [lng_min + (lng_max - lng_min) * j / (cols - 1) for j in range(cols)]
    return [(lat, lng) for lat in lats for lng in lngs]


async def _scroll_results_feed(page, results_pane) -> None:
    """Scroll the results feed until end-of-list or no new results appear."""
    prev_count = 0
    stable_streak = 0
    for scroll_i in range(50):
        await results_pane.evaluate("el => el.scrollBy(0, 800)")
        await random_delay(0.8, 1.5)

        items = await page.query_selector_all("div[role='feed'] > div > div > a")
        new_count = len(items)

        # Multiple end-of-list markers (Google changes these)
        for end_sel in ["span.HlvSq", "p.fontBodyMedium > span > span"]:
            end_marker = await page.query_selector(end_sel)
            if end_marker:
                end_text = await end_marker.inner_text()
                if "résultat" in end_text.lower() or "end of" in end_text.lower() or "fin" in end_text.lower():
                    return

        if new_count == prev_count:
            stable_streak += 1
            if stable_streak >= 4:
                break
        else:
            stable_streak = 0
        prev_count = new_count


async def _collect_hrefs_at_point(session: BrowserSession, page, lat: float, lng: float,
                                   seen_hrefs: set[str]) -> list[str]:
    """Search at a single grid point, return new place hrefs not yet seen."""
    url = f"https://www.google.com/maps/search/agence+immobili%C3%A8re/@{lat},{lng},15z"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await random_delay(2.0, 3.0)
    except Exception as e:
        console.log(f"[yellow]Grid point ({lat:.4f},{lng:.4f}) nav error: {e}[/yellow]")
        return []

    results_pane = await page.query_selector("div[role='feed']")
    if not results_pane:
        # Maybe the page hasn't loaded — wait a bit and retry
        await random_delay(2.0, 3.0)
        results_pane = await page.query_selector("div[role='feed']")
        if not results_pane:
            console.log(f"[yellow]No results feed at ({lat:.4f},{lng:.4f})[/yellow]")
            return []

    try:
        await page.wait_for_selector("div[role='feed'] > div > div > a", timeout=8_000)
    except Exception:
        pass

    await _scroll_results_feed(page, results_pane)

    links = await page.query_selector_all("div[role='feed'] > div > div > a")
    new_hrefs = []
    for link in links:
        href = await link.get_attribute("href") or ""
        if "maps/place" in href and href not in seen_hrefs:
            seen_hrefs.add(href)
            new_hrefs.append(href)
    return new_hrefs


async def _fetch_place_detail(session: BrowserSession, href: str,
                               semaphore: asyncio.Semaphore | None = None) -> Agency | None:
    """Visit a Google Maps place page and extract agency data, with retry."""
    sem = semaphore or asyncio.Semaphore(1)

    for attempt in range(1, DETAIL_MAX_RETRIES + 1):
        async with sem:
            detail_page = await session.new_page()
            try:
                await session.navigate(detail_page, href, wait_until="networkidle")

                name_el = await detail_page.query_selector("h1")
                if not name_el:
                    if attempt < DETAIL_MAX_RETRIES:
                        console.log(f"[yellow]No h1 found (attempt {attempt}), retrying: {href[:80]}[/yellow]")
                        await detail_page.close()
                        await random_delay(DETAIL_RETRY_DELAY, DETAIL_RETRY_DELAY + 2)
                        continue
                    return None
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

                # Rating + review count from span[role='img'] elements
                rating = None
                review_count = None
                rating_imgs = await detail_page.query_selector_all("span[role='img']")
                for img_el in rating_imgs:
                    aria = await img_el.get_attribute("aria-label") or ""
                    # Match "5,0 étoiles" or "4.8 stars" (the first one without "avis" is the main rating)
                    if ("toile" in aria or "star" in aria) and rating is None:
                        m = re.search(r"([\d][,.][\d])", aria)
                        if m:
                            rating = parse_rating(m.group(1))
                    # Match "110 avis" or "42 reviews"
                    if ("avis" in aria or "review" in aria) and review_count is None:
                        review_count = parse_review_count(aria)

                # Opening hours
                hours_btn = await detail_page.query_selector("div[jsaction*='openhours']")
                opening_hours = None
                if hours_btn:
                    opening_hours = parse_opening_hours_text(await hours_btn.inner_text())

                # --- GBP enrichment data ---

                # Category (e.g., "Agent immobilier")
                gbp_category = None
                cat_el = await detail_page.query_selector("button[jsaction*='category']")
                if cat_el:
                    gbp_category = extract_gbp_category(await cat_el.inner_text())
                if not gbp_category:
                    # Fallback: category often in a span below the name
                    cat_span = await detail_page.query_selector("span.DkEaL")
                    if cat_span:
                        gbp_category = extract_gbp_category(await cat_span.inner_text())

                # Photo count
                gbp_photo_count = None
                photo_btn = await detail_page.query_selector(
                    "button[aria-label*='photo'], button[aria-label*='Photo']"
                )
                if photo_btn:
                    photo_aria = await photo_btn.get_attribute("aria-label") or ""
                    gbp_photo_count = extract_gbp_photo_count(photo_aria)

                # GBP posts (updates tab)
                gbp_has_posts = None
                posts_tab = await detail_page.query_selector(
                    "button[data-tab-id='updates'], button[aria-label*='Posts'], button[aria-label*='Actualités']"
                )
                if posts_tab:
                    gbp_has_posts = True

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
                    gbp_category=gbp_category,
                    gbp_photo_count=gbp_photo_count,
                    gbp_has_posts=gbp_has_posts,
                )

                return agency

            except Exception as e:
                console.log(f"[yellow]Detail error (attempt {attempt}/{DETAIL_MAX_RETRIES}): {e}[/yellow]")
                if attempt < DETAIL_MAX_RETRIES:
                    await detail_page.close()
                    await random_delay(DETAIL_RETRY_DELAY, DETAIL_RETRY_DELAY + 2)
                    continue
                return None
            finally:
                try:
                    await detail_page.close()
                except Exception:
                    pass

    return None


async def _fetch_details_batch(session: BrowserSession, hrefs: list[str],
                                max_concurrent: int = MAX_CONCURRENT_DETAILS) -> list[Agency]:
    """Fetch place details in small batches to avoid overwhelming the browser."""
    agencies = []
    total = len(hrefs)
    for i in range(0, total, max_concurrent):
        batch = hrefs[i:i + max_concurrent]
        semaphore = asyncio.Semaphore(max_concurrent)
        tasks = [_fetch_place_detail(session, href, semaphore=semaphore) for href in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Agency):
                agencies.append(r)
            elif isinstance(r, Exception):
                console.log(f"[yellow]Batch detail exception: {r}[/yellow]")
        done = min(i + max_concurrent, total)
        console.log(f"[dim]  details: {done}/{total} processed, {len(agencies)} extracted[/dim]")
    return agencies


async def _scrape_zone(session: BrowserSession, zone_query: str, zone_slug: str,
                       bounds: tuple[float, float, float, float] | None = None) -> list[Agency]:
    agencies: list[Agency] = []
    seen_hrefs: set[str] = set()

    # Use geographic grid if bounds provided, else fall back to single text search
    if bounds:
        lat_min, lat_max, lng_min, lng_max = bounds
        points = _grid_points(lat_min, lat_max, lng_min, lng_max)
        console.log(f"[magenta]Google Maps[/magenta] >> {zone_query} ({len(points)}-point grid)")

        # Use a single page for all grid searches (avoids re-accepting consent each time)
        grid_page = await session.new_page()
        # Accept consent on first point
        first_url = f"https://www.google.com/maps/search/agence+immobili%C3%A8re/@{points[0][0]},{points[0][1]},15z"
        try:
            await grid_page.goto(first_url, wait_until="domcontentloaded", timeout=30_000)
            await random_delay(2.0, 3.0)
            await _accept_google_consent(grid_page)
        except Exception as e:
            console.log(f"[red]Consent error: {e}[/red]")

        all_hrefs: list[str] = []
        for lat, lng in points:
            new_hrefs = await _collect_hrefs_at_point(session, grid_page, lat, lng, seen_hrefs)
            all_hrefs.extend(new_hrefs)
            console.log(f"[dim]  ({lat:.4f},{lng:.4f}) -> {len(new_hrefs)} new links (total {len(seen_hrefs)})[/dim]")

        await grid_page.close()
    else:
        # Fallback: single text-based search (used when no bounds available)
        search_url = f"https://www.google.com/maps/search/{quote(zone_query)}"
        console.log(f"[magenta]Google Maps[/magenta] >> {zone_query} (text search)")
        grid_page = await session.new_page()
        try:
            await session.navigate(grid_page, search_url, wait_until="networkidle")
            await _accept_google_consent(grid_page)
            if not await grid_page.query_selector("div[role='feed']"):
                await session.navigate(grid_page, search_url, wait_until="domcontentloaded")
                await random_delay(2.0, 3.0)
        except Exception as e:
            console.log(f"[red]Nav error: {e}[/red]")
            await grid_page.close()
            return agencies
        all_hrefs = await _collect_hrefs_at_point(session, grid_page, 0, 0, seen_hrefs)
        await grid_page.close()

    console.log(f"[cyan]{zone_slug}[/cyan]: {len(all_hrefs)} unique places found, fetching details...")

    # Fetch details concurrently in batches
    agencies = await _fetch_details_batch(session, all_hrefs)
    console.log(f"[cyan]{zone_slug}[/cyan]: {len(agencies)}/{len(all_hrefs)} details extracted")

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

    # Build lookup: slug -> bounds from ZONES_GEO
    geo_bounds: dict[str, tuple[float, float, float, float]] = {
        slug: (lat_min, lat_max, lng_min, lng_max)
        for _, slug, _cp, lat_min, lat_max, lng_min, lng_max in ZONES_GEO
    }

    zones = [(f"agence immobilière {label}", slug) for label, slug, _cp in ZONES
             if zone_slugs is None or slug in zone_slugs]
    zones_to_do = [(q, s) for q, s in zones if s not in already_scraped_zones]

    if not zones_to_do:
        console.print("[green]All Google Maps zones already scraped.[/green]")
        return

    all_agencies: list[Agency] = list(existing)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("Scraping Google Maps", total=len(zones_to_do))

        async with BrowserSession(headless=headless) as session:
            for zone_query, zone_slug in zones_to_do:
                bounds = geo_bounds.get(zone_slug)
                new_agencies = await _scrape_zone(session, zone_query, zone_slug, bounds=bounds)
                for a in new_agencies:
                    if a.slug not in existing_slugs:
                        all_agencies.append(a)
                        existing_slugs.add(a.slug)

                already_scraped_zones.add(zone_slug)
                save_agencies(all_agencies, AGENCIES_JSON)
                current_state = {}
                if state_path.exists():
                    with open(state_path) as f:
                        current_state = json.load(f)
                current_state["gm_scraped_zones"] = list(already_scraped_zones)
                with open(state_path, "w") as f:
                    json.dump(current_state, f)

                progress.advance(task)
                console.log(f"[green]OK[/green] {zone_slug} -- {len(new_agencies)} agencies")

    console.print(f"[bold green]Google Maps done. Total agencies: {len(all_agencies)}[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--zones", type=str, default=None)
    args = parser.parse_args()
    zone_slugs = args.zones.split(",") if args.zones else None
    asyncio.run(run(headless=not args.headed, zone_slugs=zone_slugs))
