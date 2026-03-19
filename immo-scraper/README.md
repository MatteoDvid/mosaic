# Immo Scraper — Mosaic Prospecting Pipeline

Scrape real estate agencies from SIRENE (official French business registry) + Google Maps,
enrich each with website/email/screenshot, then generate hyper-personalized cold emails via Claude Vision.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

## Pipeline (run in order)

```bash
# 1. Scrape SIRENE API (no browser needed, fast, exhaustive)
python -m scraper.sirene_scraper [--zones paris-13,paris-14]

# 2. Scrape Google Maps (adds phone/website/ratings)
python -m scraper.google_maps_scraper [--headed] [--zones paris-13]

# 3. Deduplicate & export CSV
python -m scraper.dedup

# 4. Enrich websites + take screenshots
python -m scraper.enricher [--headed] [--limit 20]

# 5. Generate personalized cold emails via Claude Vision
python -m emails.generate_emails [--dry-run] [--limit 5]
```

## Outputs

| File | Description |
|------|-------------|
| `data/agences_immo.json` | All agencies — source of truth |
| `data/agences_immo.csv` | Same data in CSV |
| `data/emails_generated.json` | Generated cold emails |
| `screenshots/{slug}.png` | Homepage screenshots |
| `data/state.json` | Resumability checkpoint |

## Resumability

Every stage reads `data/state.json` before starting and checkpoints after each zone.
If a run crashes mid-zone, re-run the same command — it picks up from where it left off.

## Adding Zones

Edit `config.py` — add entries to `ZONES` as `("Label", "slug", "postal_code")` tuples.

## Running Tests

```bash
pytest tests/ -v
```
