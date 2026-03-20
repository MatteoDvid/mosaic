"""
Lead Scorer — ranks agencies by digital-presence weakness (higher = better lead).

Scoring is weighted towards Mosaic's two core offers:
  1. Professional real-estate photography
  2. Website redesign with interactive property tours

Computes a 0-100 score where higher means weaker digital presence,
i.e. a better prospect for Mosaic's services.

Usage:
    python -m scraper.lead_scorer [--limit 20]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AGENCIES_JSON
from models import Agency
from utils import load_agencies, save_agencies

console = Console(legacy_windows=False)


# ---------------------------------------------------------------------------
# Scoring rules  (raw max = 100)
#
# Weights are tuned to surface agencies that need:
#   - Better property photos  (photos: 20pts)
#   - A modern website with virtual tours  (site_quality: 20pts, virtual_tour: 15pts)
#   - Independents with weak online presence  (network: 10pts)
# ---------------------------------------------------------------------------

def _score_photos(count: int | None) -> int:
    """GBP photo count — fewer photos = higher score (max 20)."""
    if count is None:
        return 20
    if count < 5:
        return 16
    if count < 10:
        return 10
    if count < 20:
        return 5
    return 0


def _score_site_quality(quality: str | None) -> int:
    """Website quality — worse site = higher score (max 20)."""
    if quality in (None, "none", "outdated"):
        return 20
    if quality == "dated":
        return 12
    return 0  # "modern"


def _score_virtual_tour(has_tour: bool | None) -> int:
    """Virtual tour presence — no tour = higher score (max 15)."""
    if has_tour is None or not has_tour:
        return 15
    return 0


def _score_rating(rating: float | None) -> int:
    """Google rating (max 10)."""
    if rating is None:
        return 10
    if rating < 3.5:
        return 8
    if rating < 4.0:
        return 5
    if rating < 4.5:
        return 2
    return 0


def _score_reviews(count: int | None) -> int:
    """Google review count (max 10)."""
    if count is None:
        return 10
    if count < 5:
        return 8
    if count < 15:
        return 5
    if count < 30:
        return 2
    return 0


def _score_mobile(is_mobile: bool | None) -> int:
    """Mobile-friendly (max 5)."""
    return 0 if is_mobile else 5


def _score_network(affiliation: str | None) -> int:
    """Network affiliation — independents are better leads (max 10)."""
    if affiliation is None or affiliation.lower() == "indépendant":
        return 10
    return 0


def _score_posts(has_posts: bool | None) -> int:
    """GBP posts presence (max 5)."""
    return 0 if has_posts else 5


def _score_blog(has_blog: bool | None) -> int:
    """Blog presence (max 5)."""
    return 0 if has_blog else 5


# ---------------------------------------------------------------------------
# Offer relevance helpers
# ---------------------------------------------------------------------------

OFFER_PHOTO = "photo"
OFFER_SITE = "site_visite"

OFFER_LABELS = {
    OFFER_PHOTO: "Photos pro de biens",
    OFFER_SITE: "Refonte site + visite interactive",
}


def suggest_offers(agency: Agency, details: dict[str, int]) -> list[str]:
    """Return a list of relevant offer keys for this agency."""
    offers = []
    # Photo offer: weak photos on GBP
    if details.get("photos", 0) >= 10:
        offers.append(OFFER_PHOTO)
    # Site + virtual tour offer: weak site or no virtual tour
    if details.get("site_quality", 0) >= 12 or details.get("virtual_tour", 0) >= 15:
        offers.append(OFFER_SITE)
    # If nothing strongly stands out, suggest both
    if not offers:
        offers = [OFFER_PHOTO, OFFER_SITE]
    return offers


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_lead_score(agency: Agency) -> tuple[float, dict[str, int]]:
    """Return (score_0_100, details_dict) for a single agency."""
    details = {
        "photos": _score_photos(agency.gbp_photo_count),
        "site_quality": _score_site_quality(agency.site_quality),
        "virtual_tour": _score_virtual_tour(agency.has_virtual_tour),
        "rating": _score_rating(agency.google_rating),
        "reviews": _score_reviews(agency.google_review_count),
        "mobile": _score_mobile(agency.is_mobile_friendly),
        "network": _score_network(agency.network_affiliation),
        "posts": _score_posts(agency.gbp_has_posts),
        "blog": _score_blog(agency.has_blog),
    }
    score = float(sum(details.values()))  # max 100
    return score, details


def score_all(agencies: list[Agency]) -> list[Agency]:
    """Compute and attach lead scores to all agencies in-place."""
    for a in agencies:
        score, details = compute_lead_score(a)
        a.lead_score = score
        a.lead_score_details = details
    return agencies


def _top_weaknesses(details: dict[str, int], top_n: int = 3) -> str:
    """Return a comma-separated string of the top N weakness categories."""
    sorted_items = sorted(details.items(), key=lambda x: x[1], reverse=True)
    return ", ".join(k for k, v in sorted_items[:top_n] if v > 0)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Score agencies by lead potential")
    parser.add_argument("--limit", type=int, default=20, help="Number of top leads to display")
    args = parser.parse_args()

    agencies = load_agencies(AGENCIES_JSON)
    if not agencies:
        console.print("[red]No agencies found.[/red]")
        return

    score_all(agencies)
    save_agencies(agencies, AGENCIES_JSON)
    console.print(f"[green]Scored {len(agencies)} agencies and saved to {AGENCIES_JSON}[/green]")

    # Sort by score descending (best leads first)
    ranked = sorted(agencies, key=lambda a: a.lead_score or 0, reverse=True)

    table = Table(title=f"Top {args.limit} Leads", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Score", style="bold cyan", width=6)
    table.add_column("Agency", style="white", max_width=35)
    table.add_column("Network", style="dim", max_width=15)
    table.add_column("Rating", width=6)
    table.add_column("Reviews", width=8)
    table.add_column("Site", width=10)
    table.add_column("V.Tour", width=6)
    table.add_column("Offers", style="magenta", max_width=25)
    table.add_column("Top Weaknesses", style="yellow", max_width=30)

    for i, a in enumerate(ranked[:args.limit], 1):
        details = a.lead_score_details or {}
        offers = suggest_offers(a, details)
        offer_str = ", ".join(OFFER_LABELS.get(o, o) for o in offers)
        table.add_row(
            str(i),
            f"{a.lead_score:.0f}",
            a.name[:35],
            (a.network_affiliation or "—")[:15],
            f"{a.google_rating:.1f}" if a.google_rating else "—",
            str(a.google_review_count) if a.google_review_count else "—",
            (a.site_quality or "—")[:10],
            "Oui" if a.has_virtual_tour else "Non",
            offer_str[:25],
            _top_weaknesses(details),
        )

    console.print(table)


if __name__ == "__main__":
    main()
