from __future__ import annotations
import asyncio
import csv
import json
import random
import re
import unicodedata
from pathlib import Path
from typing import Optional

from models import Agency, EnrichmentStatus


# ---------------------------------------------------------------------------
# Address / name normalization helpers (used for cross-source dedup)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Strip accents, lowercase, collapse whitespace."""
    n = unicodedata.normalize("NFD", text or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]", " ", n.lower()).split())


_STREET_ABBREVS = {"r": "rue", "av": "avenue", "bd": "boulevard", "pl": "place", "sq": "square"}
_DROP_WORDS = {"agence", "immobiliere", "immobilier", "immo", "paris", "france", "sarl",
               "sas", "sci", "eurl", "sa", "de", "du", "des", "la", "le", "les", "et", "l"}


def _addr_key(addr: str) -> str:
    """Canonical address key: street_number + normalized street name (before postal code)."""
    n = _normalize(addr)
    # Cut off at postal code (75xxx)
    n = re.sub(r"\b75\d{3}\b.*", "", n).strip()
    # Expand common abbreviations
    words = n.split()
    words = [_STREET_ABBREVS.get(w, w) for w in words]
    return " ".join(words[:6])  # number + up to 5 street words


def _name_words(name: str) -> set[str]:
    """Significant words in an agency name (drop generic words)."""
    return {w for w in _normalize(name).split() if w not in _DROP_WORDS and len(w) > 2}


def _names_overlap(a: str, b: str) -> bool:
    """True if the two names share at least one significant word."""
    return bool(_name_words(a) & _name_words(b))


# ---------------------------------------------------------------------------
# Email extraction
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
_SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".webp"}


def extract_emails_from_html(html: str) -> list[str]:
    """Extract unique email addresses from raw HTML, skipping file references."""
    found = _EMAIL_RE.findall(html)
    emails: list[str] = []
    seen: set[str] = set()
    for e in found:
        if any(e.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
            continue
        e_lower = e.lower()
        if e_lower not in seen:
            seen.add(e_lower)
            emails.append(e)
    return emails


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _merge_into(base: Agency, extra: Agency) -> Agency:
    """Copy non-null fields from extra into base. Returns new merged Agency."""
    merged = base.model_dump()
    for field, value in extra.model_dump().items():
        if field == "source":
            if value and value not in merged["source"]:
                merged["source"] = f"{merged['source']},{value}"
        elif field == "slug":
            pass  # keep base slug
        elif value is not None and merged.get(field) is None:
            merged[field] = value
    return Agency(**merged)


def deduplicate_agencies(agencies: list[Agency]) -> list[Agency]:
    """
    Two-pass dedup:
    1. Same-slug merge (intra-source duplicates, e.g. two google_maps entries).
    2. Cross-source merge: match a google_maps agency to a sirene agency when
       they share the same street address AND at least one significant name word.
       The sirene record wins (keeps SIRET slug); google_maps data fills blanks.
    """
    # Pass 1: slug-based merge
    by_slug: dict[str, Agency] = {}
    for agency in agencies:
        slug = agency.slug
        if slug not in by_slug:
            by_slug[slug] = agency
        else:
            by_slug[slug] = _merge_into(by_slug[slug], agency)

    all_agencies = list(by_slug.values())

    # Pass 2: cross-source address+name merge
    sirene = [a for a in all_agencies if "sirene" in a.source]
    non_sirene = [a for a in all_agencies if "sirene" not in a.source]

    absorbed_slugs: set[str] = set()
    for gm in non_sirene:
        gm_key = _addr_key(gm.address)
        if not gm_key:
            continue
        for si in sirene:
            si_key = _addr_key(si.address)
            if gm_key == si_key and _names_overlap(gm.name, si.name):
                # Merge google_maps data into sirene record
                updated = _merge_into(si, gm)
                by_slug[si.slug] = updated
                absorbed_slugs.add(gm.slug)
                break

    return [a for a in by_slug.values() if a.slug not in absorbed_slugs]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_agencies(agencies: list[Agency], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [a.model_dump() for a in agencies]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def load_agencies(path: str) -> list[Agency]:
    if not Path(path).exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Agency(**d) for d in data]


def export_csv(agencies: list[Agency], path: str) -> None:
    if not agencies:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(Agency.model_fields.keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for agency in agencies:
            row = agency.model_dump()
            # Serialize complex types to strings
            row["opening_hours"] = json.dumps(row["opening_hours"], ensure_ascii=False) if row["opening_hours"] else ""
            row["agents_names"] = ", ".join(row["agents_names"]) if row["agents_names"] else ""
            row["lead_score_details"] = json.dumps(row["lead_score_details"], ensure_ascii=False) if row["lead_score_details"] else ""
            writer.writerow(row)


def export_emails_csv(emails_json_path: str, csv_path: str) -> None:
    """Export generated emails to CSV for bulk sending tools."""
    p = Path(emails_json_path)
    if not p.exists():
        return
    with open(p, encoding="utf-8") as f:
        emails = json.load(f)
    if not emails:
        return

    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["email_to", "agency_name", "offer", "offer_label", "subject", "body", "generated_at"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for em in emails:
            writer.writerow({k: em.get(k, "") for k in fieldnames})


# ---------------------------------------------------------------------------
# Delays
# ---------------------------------------------------------------------------

async def random_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    """Async sleep for a random duration to mimic human behaviour."""
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)
