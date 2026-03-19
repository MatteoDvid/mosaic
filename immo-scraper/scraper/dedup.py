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

console = Console(legacy_windows=False)


def run() -> None:
    agencies = load_agencies(AGENCIES_JSON)
    before = len(agencies)
    agencies = deduplicate_agencies(agencies)
    after = len(agencies)
    save_agencies(agencies, AGENCIES_JSON)
    export_csv(agencies, AGENCIES_CSV)
    console.print(f"[bold]Dedup complete.[/bold] {before} >> {after} agencies ({before - after} duplicates removed)")
    console.print(f"Saved JSON >> [cyan]{AGENCIES_JSON}[/cyan]")
    console.print(f"Saved CSV  >> [cyan]{AGENCIES_CSV}[/cyan]")


if __name__ == "__main__":
    run()
