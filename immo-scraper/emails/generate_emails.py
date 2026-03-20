"""
Email generator — uses Claude Vision to craft personalized cold emails.

Generates up to 2 email variants per agency based on suggested offers:
  - "photo": Professional property photography
  - "site_visite": Website redesign with interactive virtual tours

Usage:
    python -m emails.generate_emails [--dry-run] [--limit 5] [--offer photo|site_visite|both]
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, AGENCIES_JSON, EMAILS_JSON, EMAILS_CSV
from models import Agency, EnrichmentStatus
from scraper.lead_scorer import suggest_offers, OFFER_PHOTO, OFFER_SITE, OFFER_LABELS
from utils import load_agencies, export_emails_csv

console = Console(legacy_windows=False)

PROMPT_DIR = Path(__file__).parent
SYSTEM_PROMPTS = {
    OFFER_PHOTO: PROMPT_DIR / "system_prompt_photo.txt",
    OFFER_SITE: PROMPT_DIR / "system_prompt_site.txt",
}


def load_system_prompt(offer: str) -> str:
    path = SYSTEM_PROMPTS[offer]
    return path.read_text(encoding="utf-8")


def _encode_screenshot(path: str) -> Optional[str]:
    p = Path(path)
    if not p.exists():
        return None
    return base64.standard_b64encode(p.read_bytes()).decode("utf-8")


def build_prompt_messages(agency_data: dict, screenshot_b64: Optional[str], offer: str) -> list[dict]:
    system_prompt = load_system_prompt(offer)
    agency_json_str = json.dumps(agency_data, ensure_ascii=False, indent=2)
    user_text = system_prompt.replace("{agency_json}", agency_json_str)

    content: list[dict] = []
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        })
    content.append({"type": "text", "text": user_text})

    return [{"role": "user", "content": content}]


def parse_claude_response(raw: str) -> dict:
    """Extract JSON from Claude response, stripping markdown code fences if present."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse Claude response as JSON: {e}\nRaw: {raw[:300]}")


def _load_existing_emails(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save_emails(emails: list[dict], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(emails, f, ensure_ascii=False, indent=2)


def run(dry_run: bool = False, limit: Optional[int] = None, offer_filter: Optional[str] = None) -> None:
    agencies = load_agencies(AGENCIES_JSON)
    ready = [a for a in agencies if a.enrichment_status == EnrichmentStatus.READY_FOR_EMAIL]
    if limit:
        ready = ready[:limit]

    if not ready:
        console.print("[yellow]No agencies with status 'ready_for_email'. Run enricher first.[/yellow]")
        return

    existing_emails = _load_existing_emails(EMAILS_JSON)
    # Track what's already generated: (agency_name, offer)
    already_done = {(e["agency_name"], e.get("offer", "")) for e in existing_emails}

    # Build work items: (agency, offer_key)
    work_items = []
    for a in ready:
        details = a.lead_score_details or {}
        offers = suggest_offers(a, details)

        # Apply CLI filter
        if offer_filter == OFFER_PHOTO:
            offers = [o for o in offers if o == OFFER_PHOTO]
        elif offer_filter == OFFER_SITE:
            offers = [o for o in offers if o == OFFER_SITE]

        for offer in offers:
            if (a.name, offer) not in already_done:
                work_items.append((a, offer))

    if not work_items:
        console.print("[green]All emails already generated for matching agencies/offers.[/green]")
        return

    console.print(f"[cyan]Will generate {len(work_items)} emails across {len(ready)} agencies.[/cyan]")
    for offer_key in [OFFER_PHOTO, OFFER_SITE]:
        count = sum(1 for _, o in work_items if o == offer_key)
        if count:
            console.print(f"  • {OFFER_LABELS[offer_key]}: {count} emails")

    if dry_run:
        console.print(f"[bold yellow]DRY RUN[/bold yellow] — no API calls made.")
        for a, offer in work_items[:10]:
            console.print(f"  • {a.name} → {OFFER_LABELS[offer]}")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("Generating emails", total=len(work_items))

        for agency, offer in work_items:
            try:
                screenshot_b64 = _encode_screenshot(agency.screenshot_path) if agency.screenshot_path else None
                messages = build_prompt_messages(agency.model_dump(), screenshot_b64, offer)

                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=1024,
                    messages=messages,
                )
                raw_text = response.content[0].text
                parsed = parse_claude_response(raw_text)

                email_record = {
                    "agency_name": agency.name,
                    "agency_slug": agency.slug,
                    "email_to": agency.email,
                    "offer": offer,
                    "offer_label": OFFER_LABELS[offer],
                    "subject": parsed.get("subject", ""),
                    "body": parsed.get("body", ""),
                    "screenshot_used": agency.screenshot_path or "",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                existing_emails.append(email_record)
                _save_emails(existing_emails, EMAILS_JSON)
                console.log(f"[green]✓[/green] {agency.name} — {OFFER_LABELS[offer]}")

            except Exception as e:
                console.log(f"[red]Error for {agency.name} ({offer}): {e}[/red]")

            progress.advance(task)

    # Auto-export to CSV for bulk sending
    export_emails_csv(EMAILS_JSON, EMAILS_CSV)
    console.print(f"[bold green]Done. {len(existing_emails)} total emails in {EMAILS_JSON}[/bold green]")
    console.print(f"[dim]CSV export: {EMAILS_CSV}[/dim]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate personalized cold emails via Claude Vision")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without API calls")
    parser.add_argument("--limit", type=int, default=None, help="Process only N agencies")
    parser.add_argument("--offer", choices=["photo", "site_visite", "both"], default="both",
                        help="Which offer to generate emails for (default: both)")
    args = parser.parse_args()

    offer_filter = None
    if args.offer == "photo":
        offer_filter = OFFER_PHOTO
    elif args.offer == "site_visite":
        offer_filter = OFFER_SITE

    run(dry_run=args.dry_run, limit=args.limit, offer_filter=offer_filter)
