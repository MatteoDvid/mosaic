"""Mini CRM web application for the immo-scraper project."""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import Agency
from scraper.lead_scorer import suggest_offers, OFFER_LABELS

# ---------------------------------------------------------------------------
# Paths (relative to immo-scraper root, since we run from there)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
AGENCIES_JSON = DATA_DIR / "agences_immo.json"
EMAILS_JSON = DATA_DIR / "emails_generated.json"
CRM_JSON = DATA_DIR / "crm_contacts.json"
COORDS_CACHE_JSON = DATA_DIR / "coords_cache.json"

CRM_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = CRM_DIR / "templates"
STATIC_DIR = CRM_DIR / "static"

# ---------------------------------------------------------------------------
# Postal-code → approximate centre (for agencies without Google Maps coords)
# ---------------------------------------------------------------------------
POSTAL_CODE_COORDS: dict[str, tuple[float, float]] = {
    "75001": (48.8600, 2.3444), "75002": (48.8675, 2.3514),
    "75003": (48.8631, 2.3592), "75004": (48.8544, 2.3565),
    "75005": (48.8462, 2.3444), "75006": (48.8497, 2.3325),
    "75007": (48.8566, 2.3125), "75008": (48.8744, 2.3106),
    "75009": (48.8769, 2.3372), "75010": (48.8769, 2.3597),
    "75011": (48.8589, 2.3794), "75012": (48.8406, 2.3878),
    "75013": (48.8281, 2.3597), "75014": (48.8283, 2.3264),
    "75015": (48.8411, 2.2981), "75016": (48.8606, 2.2769),
    "75017": (48.8867, 2.3167), "75018": (48.8925, 2.3444),
    "75019": (48.8869, 2.3825), "75020": (48.8636, 2.3981),
    "92100": (48.8353, 2.2428), "92200": (48.8847, 2.2681),
    "92300": (48.8956, 2.2878), "92130": (48.8236, 2.2706),
    "93200": (48.9361, 2.3567), "93100": (48.8636, 2.4431),
    "94300": (48.8478, 2.4386), "94160": (48.8461, 2.4178),
}

# Small random jitter so markers don't stack at exact same point
import random
random.seed(42)


def _extract_coords_from_gmaps_url(url: str | None) -> tuple[float, float] | None:
    """Try to extract lat/lng from a Google Maps URL."""
    if not url:
        return None
    # Pattern: !3d<lat>!4d<lng>
    m = re.search(r"!3d([\d.]+)!4d([\d.]+)", url)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Pattern: @<lat>,<lng>
    m = re.search(r"@([\d.]+),([\d.]+)", url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def _extract_postal_code(address: str) -> str | None:
    """Extract postal code from a French address."""
    m = re.search(r"\b(75\d{3}|9[234]\d{3})\b", address)
    return m.group(1) if m else None


def _jitter() -> float:
    return random.uniform(-0.002, 0.002)


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> list | dict:
    if not path.exists():
        return [] if path == AGENCIES_JSON else {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _load_crm() -> dict:
    return _load_json(CRM_JSON) if CRM_JSON.exists() else {}


def _save_crm(data: dict) -> None:
    _save_json(CRM_JSON, data)


def _load_coords_cache() -> dict:
    if COORDS_CACHE_JSON.exists():
        with open(COORDS_CACHE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_coords_cache(cache: dict) -> None:
    _save_json(COORDS_CACHE_JSON, cache)


def _get_coords(agency: dict, coords_cache: dict) -> tuple[float, float] | None:
    """Resolve coordinates for an agency."""
    slug = agency.get("slug", "")

    # 1. Check cache
    if slug in coords_cache:
        return tuple(coords_cache[slug])

    # 2. Try Google Maps URL
    coords = _extract_coords_from_gmaps_url(agency.get("google_maps_url"))
    if coords:
        coords_cache[slug] = list(coords)
        return coords

    # 3. Fall back to postal code centroid + jitter
    pc = _extract_postal_code(agency.get("address", ""))
    if pc and pc in POSTAL_CODE_COORDS:
        base = POSTAL_CODE_COORDS[pc]
        coords = (base[0] + _jitter(), base[1] + _jitter())
        coords_cache[slug] = list(coords)
        return coords

    # 4. Default: Paris centre + jitter
    coords = (48.856 + _jitter(), 2.352 + _jitter())
    coords_cache[slug] = list(coords)
    return coords


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Immo CRM", docs_url="/docs")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    html_path = TEMPLATES_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/agencies")
async def list_agencies():
    agencies = _load_json(AGENCIES_JSON)
    crm = _load_crm()
    coords_cache = _load_coords_cache()

    result = []
    cache_dirty = False
    for ag in agencies:
        slug = ag.get("slug", "")
        old_cache_size = len(coords_cache)
        coords = _get_coords(ag, coords_cache)
        if len(coords_cache) > old_cache_size:
            cache_dirty = True

        # Compute suggested offers from score details
        details = ag.get("lead_score_details", {})
        try:
            agency_obj = Agency(**ag)
            offers = suggest_offers(agency_obj, details)
        except Exception:
            offers = []
        offer_labels = [OFFER_LABELS.get(o, o) for o in offers]

        entry = {
            "slug": slug,
            "name": ag.get("name", ""),
            "address": ag.get("address", ""),
            "phone": ag.get("phone", ""),
            "email": ag.get("email", ""),
            "website": ag.get("website", ""),
            "google_rating": ag.get("google_rating"),
            "google_review_count": ag.get("google_review_count"),
            "network_affiliation": ag.get("network_affiliation", ""),
            "lead_score": ag.get("lead_score"),
            "director_name": ag.get("director_name", ""),
            "site_quality": ag.get("site_quality", ""),
            "has_virtual_tour": ag.get("has_virtual_tour", False),
            "suggested_offers": offer_labels,
            "lat": coords[0] if coords else None,
            "lng": coords[1] if coords else None,
            # CRM fields
            "status": crm.get(slug, {}).get("status", "not_contacted"),
            "last_contact_date": crm.get(slug, {}).get("last_contact_date", ""),
        }
        result.append(entry)

    if cache_dirty:
        _save_coords_cache(coords_cache)

    return result


@app.get("/api/agencies/{slug}")
async def get_agency(slug: str):
    agencies = _load_json(AGENCIES_JSON)
    crm = _load_crm()
    coords_cache = _load_coords_cache()

    agency = None
    for ag in agencies:
        if ag.get("slug") == slug:
            agency = ag
            break

    if not agency:
        raise HTTPException(status_code=404, detail="Agence introuvable")

    coords = _get_coords(agency, coords_cache)
    _save_coords_cache(coords_cache)

    crm_data = crm.get(slug, {
        "status": "not_contacted",
        "last_contact_date": "",
        "message_sent": "",
        "notes": "",
        "history": [],
    })

    # Load generated emails for this agency
    emails = _load_json(EMAILS_JSON) if EMAILS_JSON.exists() else []
    agency_emails = [e for e in emails if e.get("agency_slug") == slug or e.get("agency_name") == agency.get("name")]

    # Compute suggested offers
    details = agency.get("lead_score_details", {})
    try:
        agency_obj = Agency(**agency)
        offers = suggest_offers(agency_obj, details)
    except Exception:
        offers = []
    offer_labels = [OFFER_LABELS.get(o, o) for o in offers]

    return {**agency, "lat": coords[0] if coords else None,
            "lng": coords[1] if coords else None, "crm": crm_data,
            "generated_emails": agency_emails, "suggested_offers": offer_labels}


class ContactUpdate(BaseModel):
    status: str
    last_contact_date: Optional[str] = None
    message_sent: Optional[str] = None
    notes: Optional[str] = None


@app.put("/api/agencies/{slug}/contact")
async def update_contact(slug: str, payload: ContactUpdate):
    # Verify agency exists
    agencies = _load_json(AGENCIES_JSON)
    found = any(ag.get("slug") == slug for ag in agencies)
    if not found:
        raise HTTPException(status_code=404, detail="Agence introuvable")

    crm = _load_crm()

    existing = crm.get(slug, {
        "status": "not_contacted",
        "last_contact_date": "",
        "message_sent": "",
        "notes": "",
        "history": [],
    })

    # Build history entry if status changed
    history = existing.get("history", [])
    if payload.status != existing.get("status", "not_contacted"):
        history.append({
            "date": str(date.today()),
            "action": f"Statut changé → {payload.status}",
            "details": payload.message_sent or "",
        })

    crm[slug] = {
        "status": payload.status,
        "last_contact_date": payload.last_contact_date or str(date.today()),
        "message_sent": payload.message_sent or existing.get("message_sent", ""),
        "notes": payload.notes or existing.get("notes", ""),
        "history": history,
    }

    _save_crm(crm)
    return {"ok": True, "crm": crm[slug]}


@app.get("/api/stats")
async def get_stats():
    agencies = _load_json(AGENCIES_JSON)
    crm = _load_crm()

    total = len(agencies)
    scores = [ag.get("lead_score", 0) or 0 for ag in agencies]
    avg_score = round(sum(scores) / total, 1) if total else 0

    status_counts = {
        "not_contacted": 0,
        "contacted": 0,
        "waiting": 0,
        "responded": 0,
        "converted": 0,
        "not_interested": 0,
    }

    for ag in agencies:
        slug = ag.get("slug", "")
        status = crm.get(slug, {}).get("status", "not_contacted")
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts["not_contacted"] += 1

    networks: dict[str, int] = {}
    for ag in agencies:
        net = ag.get("network_affiliation", "indépendant") or "indépendant"
        networks[net] = networks.get(net, 0) + 1

    return {
        "total": total,
        "avg_lead_score": avg_score,
        "status_counts": status_counts,
        "top_networks": dict(sorted(networks.items(), key=lambda x: -x[1])[:10]),
    }


# ---------------------------------------------------------------------------
# Entry point: python -m crm.app
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("crm.app:app", host="0.0.0.0", port=8000, reload=True)
