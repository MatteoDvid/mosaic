"""
Email generator — uses Claude Vision to craft personalized cold emails.

Usage:
    python -m emails.generate_emails [--dry-run] [--limit 5]
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

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, AGENCIES_JSON, EMAILS_JSON
from models import Agency, EnrichmentStatus
from utils import load_agencies

console = Console(legacy_windows=False)
SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _encode_screenshot(path: str) -> Optional[str]:
    p = Path(path)
    if not p.exists():
        return None
    return base64.standard_b64encode(p.read_bytes()).decode("utf-8")


def build_prompt_messages(agency_data: dict, screenshot_b64: Optional[str]) -> list[dict]:
    system_prompt = load_system_prompt()
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


def run(dry_run: bool = False, limit: Optional[int] = None) -> None:
    agencies = load_agencies(AGENCIES_JSON)
    ready = [a for a in agencies if a.enrichment_status == EnrichmentStatus.READY_FOR_EMAIL]
    if limit:
        ready = ready[:limit]

    if not ready:
        console.print("[yellow]No agencies with status 'ready_for_email'. Run enricher first.[/yellow]")
        return

    existing_emails = _load_existing_emails(EMAILS_JSON)
    already_done = {e["agency_name"] for e in existing_emails}
    to_process = [a for a in ready if a.name not in already_done]

    if not to_process:
        console.print("[green]All ready agencies already have emails generated.[/green]")
        return

    if dry_run:
        console.print(f"[bold yellow]DRY RUN[/bold yellow] — would generate {len(to_process)} emails. No API calls made.")
        for a in to_process[:5]:
            console.print(f"  • {a.name} <{a.email}>")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("Generating emails", total=len(to_process))

        for agency in to_process:
            try:
                screenshot_b64 = _encode_screenshot(agency.screenshot_path) if agency.screenshot_path else None
                messages = build_prompt_messages(agency.model_dump(), screenshot_b64)

                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=1024,
                    messages=messages,
                )
                raw_text = response.content[0].text
                parsed = parse_claude_response(raw_text)

                email_record = {
                    "agency_name": agency.name,
                    "email_to": agency.email,
                    "subject": parsed.get("subject", ""),
                    "body": parsed.get("body", ""),
                    "screenshot_used": agency.screenshot_path or "",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                existing_emails.append(email_record)
                _save_emails(existing_emails, EMAILS_JSON)
                console.log(f"[green]✓[/green] Email generated for {agency.name}")

            except Exception as e:
                console.log(f"[red]Error for {agency.name}: {e}[/red]")

            progress.advance(task)

    console.print(f"[bold green]Done. {len(existing_emails)} total emails in {EMAILS_JSON}[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate personalized cold emails via Claude Vision")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without API calls")
    parser.add_argument("--limit", type=int, default=None, help="Process only N agencies")
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
