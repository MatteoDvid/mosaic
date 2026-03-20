"""
Lead Scorer — ranks agencies by digital-presence weakness (higher = better lead).

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
# ---------------------------------------------------------------------------

def _score_rating(rating: float | None) -> int:
    if rating is None:
        return 15
    if rating < 3.5:
        return 12
    if rating < 4.0:
        return 8
    if rating < 4.5:
        return 4
    return 0


def _score_reviews(count: int | None) -> int:
    if count is None:
        return 15
    if count < 5:
        return 12
    if count < 15:
        return 8
    if count < 30:
        return 4
    return 0


def _score_site_quality(quality: str | None) -> int:
    if quality in (None, "none", "outdated"):
        return 15
    if quality == "dated":
        return 10
    return 0  # "modern"


def _score_blog(has_blog: bool | None) -> int:
    return 0 if has_blog else 10


def _score_mobile(is_mobile: bool | None) -> int:
    return 0 if is_mobile else 10


def _score_photos(count: int | None) -> int:
    if count is None:
        return 10
    if count < 5:
        return 8
    if count < 10:
        return 4
    return 0


def _score_posts(has_posts: bool | None) -> int:
    return 0 if has_posts else 10


def _score_network(affiliation: str | None) -> int:
    if affiliation is None or affiliation.lower() == "indépendant":
        return 15
    return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_lead_score(agency: Agency) -> tuple[float, dict[str, int]]:
    """Return (score_0_100, details_dict) for a single agency."""
    details = {
        "rating": _score_rating(agency.google_rating),
        "reviews": _score_reviews(agency.google_review_count),
        "site_quality": _score_site_quality(agency.site_quality),
        "blog": _score_blog(agency.has_blog),
        "mobile": _score_mobile(agency.is_mobile_friendly),
        "photos": _score_photos(agency.gbp_photo_count),
        "posts": _score_posts(agency.gbp_has_posts),
        "network": _score_network(agency.network_affiliation),
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
    table.add_column("Top Weaknesses", style="yellow", max_width=30)

    for i, a in enumerate(ranked[:args.limit], 1):
        details = a.lead_score_details or {}
        table.add_row(
            str(i),
            f"{a.lead_score:.0f}",
            a.name[:35],
            (a.network_affiliation or "—")[:15],
            f"{a.google_rating:.1f}" if a.google_rating else "—",
            str(a.google_review_count) if a.google_review_count else "—",
            (a.site_quality or "—")[:10],
            _top_weaknesses(details),
        )

    console.print(table)


if __name__ == "__main__":
    main()
