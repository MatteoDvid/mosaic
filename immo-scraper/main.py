#!/usr/bin/env python3
"""
Mosaic Pipeline — run the full prospecting pipeline end-to-end.

Stages:
  1. SIRENE scraper (API — fast, exhaustive)
  2. Google Maps scraper (browser — ratings, reviews, GBP data)
  3. Deduplication
  4. Website enricher (emails, screenshots, site quality, virtual tours)
  5. Lead scoring + offer suggestion
  6. Linkup enricher (optional — director, social media)
  7. Email generation (Claude Vision — 2 variants per agency)

Usage:
    python main.py                       # run all stages
    python main.py --from enricher       # resume from a specific stage
    python main.py --only scorer         # run a single stage
    python main.py --zones paris-13      # limit to specific zones
    python main.py --limit 10            # limit enrichment/email to N agencies
    python main.py --dry-run             # preview without API calls
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

console = Console(legacy_windows=False)

BASE_DIR = Path(__file__).resolve().parent

STAGES = [
    "sirene",
    "google_maps",
    "dedup",
    "enricher",
    "scorer",
    "linkup",
    "emails",
]


def _run_module(module: str, extra_args: list[str] | None = None) -> bool:
    """Run a Python module and return True if it succeeded."""
    cmd = [sys.executable, "-m", module]
    if extra_args:
        cmd.extend(extra_args)
    console.rule(f"[bold cyan]{module}[/bold cyan]")
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        console.print(f"[red]Stage {module} failed (exit {result.returncode})[/red]")
        return False
    return True


def run_pipeline(
    from_stage: str | None = None,
    only_stage: str | None = None,
    zones: str | None = None,
    limit: int | None = None,
    headed: bool = False,
    dry_run: bool = False,
    skip_linkup: bool = False,
    offer: str = "both",
) -> None:
    # Determine which stages to run
    if only_stage:
        stages_to_run = [only_stage]
    elif from_stage:
        idx = STAGES.index(from_stage)
        stages_to_run = STAGES[idx:]
    else:
        stages_to_run = list(STAGES)

    if skip_linkup and "linkup" in stages_to_run:
        stages_to_run.remove("linkup")

    console.print(Panel(
        f"[bold]Stages:[/bold] {' → '.join(stages_to_run)}\n"
        f"[bold]Zones:[/bold] {zones or 'toutes'}\n"
        f"[bold]Limit:[/bold] {limit or 'aucune'}\n"
        f"[bold]Offre:[/bold] {offer}\n"
        f"[bold]Dry run:[/bold] {'oui' if dry_run else 'non'}",
        title="Mosaic Pipeline",
        border_style="cyan",
    ))

    zone_args = ["--zones", zones] if zones else []
    limit_args = ["--limit", str(limit)] if limit else []
    headed_args = ["--headed"] if headed else []

    for stage in stages_to_run:
        ok = True

        if stage == "sirene":
            ok = _run_module("scraper.sirene_scraper", zone_args)

        elif stage == "google_maps":
            ok = _run_module("scraper.google_maps_scraper", zone_args + headed_args)

        elif stage == "dedup":
            ok = _run_module("scraper.dedup")

        elif stage == "enricher":
            ok = _run_module("scraper.enricher", limit_args + headed_args)

        elif stage == "scorer":
            ok = _run_module("scraper.lead_scorer", limit_args)

        elif stage == "linkup":
            args = limit_args[:]
            if dry_run:
                args.append("--dry-run")
            ok = _run_module("scraper.linkup_enricher", args)

        elif stage == "emails":
            args = limit_args[:]
            if dry_run:
                args.append("--dry-run")
            if offer != "both":
                args.extend(["--offer", offer])
            ok = _run_module("emails.generate_emails", args)

        if not ok:
            console.print(f"\n[red bold]Pipeline stopped at stage: {stage}[/red bold]")
            console.print(f"[yellow]Fix the issue and resume with: python main.py --from {stage}[/yellow]")
            sys.exit(1)

    console.print("\n[bold green]Pipeline terminé avec succès ![/bold green]")
    console.print("[dim]Lancez le CRM : python -m crm.app[/dim]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Mosaic prospecting pipeline")
    parser.add_argument("--from", dest="from_stage", choices=STAGES,
                        help="Resume from this stage")
    parser.add_argument("--only", dest="only_stage", choices=STAGES,
                        help="Run only this stage")
    parser.add_argument("--zones", type=str, default=None,
                        help="Comma-separated zone slugs (e.g., paris-13,paris-14)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit enrichment/email generation to N agencies")
    parser.add_argument("--headed", action="store_true",
                        help="Run browser in headed mode (visible)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without API calls")
    parser.add_argument("--skip-linkup", action="store_true",
                        help="Skip the Linkup enrichment stage")
    parser.add_argument("--offer", choices=["photo", "site_visite", "both"],
                        default="both", help="Which offer to generate emails for")
    args = parser.parse_args()

    run_pipeline(
        from_stage=args.from_stage,
        only_stage=args.only_stage,
        zones=args.zones,
        limit=args.limit,
        headed=args.headed,
        dry_run=args.dry_run,
        skip_linkup=args.skip_linkup,
        offer=args.offer,
    )
