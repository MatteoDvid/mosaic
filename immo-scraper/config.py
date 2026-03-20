from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
LINKUP_API_KEY: str = os.getenv("LINKUP_API_KEY", "")
CLAUDE_MODEL: str = "claude-sonnet-4-6"

# Geographic bounding boxes for grid-based Google Maps scraping
# (label, slug, postal_code, lat_min, lat_max, lng_min, lng_max)
# Boxes are approximate — cover the arrondissement with some margin.
ZONES_GEO: list[tuple[str, str, str, float, float, float, float]] = [
    ("Paris 1er",  "paris-01", "75001", 48.854, 48.865, 2.334, 2.356),
    ("Paris 2e",   "paris-02", "75002", 48.863, 48.870, 2.344, 2.358),
    ("Paris 3e",   "paris-03", "75003", 48.859, 48.867, 2.352, 2.366),
    ("Paris 4e",   "paris-04", "75004", 48.849, 48.860, 2.348, 2.362),
    ("Paris 5e",   "paris-05", "75005", 48.843, 48.854, 2.346, 2.362),
    ("Paris 6e",   "paris-06", "75006", 48.845, 48.857, 2.330, 2.348),
    ("Paris 7e",   "paris-07", "75007", 48.851, 48.865, 2.296, 2.322),
    ("Paris 8e",   "paris-08", "75008", 48.869, 48.882, 2.296, 2.323),
    ("Paris 9e",   "paris-09", "75009", 48.873, 48.884, 2.329, 2.350),
    ("Paris 10e",  "paris-10", "75010", 48.867, 48.882, 2.349, 2.372),
    ("Paris 11e",  "paris-11", "75011", 48.851, 48.870, 2.362, 2.392),
    ("Paris 12e",  "paris-12", "75012", 48.835, 48.858, 2.373, 2.410),
    ("Paris 13e",  "paris-13", "75013", 48.816, 48.839, 2.345, 2.378),
    ("Paris 14e",  "paris-14", "75014", 48.820, 48.840, 2.316, 2.346),
    ("Paris 15e",  "paris-15", "75015", 48.830, 48.857, 2.278, 2.318),
    ("Paris 16e",  "paris-16", "75016", 48.847, 48.877, 2.255, 2.296),
    ("Paris 17e",  "paris-17", "75017", 48.878, 48.897, 2.296, 2.334),
    ("Paris 18e",  "paris-18", "75018", 48.884, 48.903, 2.329, 2.369),
    ("Paris 19e",  "paris-19", "75019", 48.876, 48.898, 2.368, 2.402),
    ("Paris 20e",  "paris-20", "75020", 48.856, 48.878, 2.388, 2.416),
    ("Boulogne-Billancourt", "boulogne-billancourt", "92100", 48.827, 48.849, 2.228, 2.261),
    ("Neuilly-sur-Seine",    "neuilly-sur-seine",    "92200", 48.876, 48.893, 2.256, 2.281),
    ("Levallois-Perret",     "levallois-perret",     "92300", 48.893, 48.905, 2.278, 2.298),
    ("Issy-les-Moulineaux",  "issy-les-moulineaux",  "92130", 48.819, 48.833, 2.262, 2.285),
    ("Saint-Denis",          "saint-denis",          "93200", 48.930, 48.948, 2.344, 2.374),
    ("Montreuil",            "montreuil",            "93100", 48.856, 48.871, 2.434, 2.460),
    ("Vincennes",            "vincennes",            "94300", 48.844, 48.857, 2.428, 2.453),
    ("Saint-Mandé",          "saint-mande",          "94160", 48.843, 48.852, 2.415, 2.431),
]

# Zones to scrape — (label, slug, postal_code)
ZONES: list[tuple[str, str, str]] = [
    # Paris arrondissements
    ("Paris 1er", "paris-01", "75001"),
    ("Paris 2e", "paris-02", "75002"),
    ("Paris 3e", "paris-03", "75003"),
    ("Paris 4e", "paris-04", "75004"),
    ("Paris 5e", "paris-05", "75005"),
    ("Paris 6e", "paris-06", "75006"),
    ("Paris 7e", "paris-07", "75007"),
    ("Paris 8e", "paris-08", "75008"),
    ("Paris 9e", "paris-09", "75009"),
    ("Paris 10e", "paris-10", "75010"),
    ("Paris 11e", "paris-11", "75011"),
    ("Paris 12e", "paris-12", "75012"),
    ("Paris 13e", "paris-13", "75013"),
    ("Paris 14e", "paris-14", "75014"),
    ("Paris 15e", "paris-15", "75015"),
    ("Paris 16e", "paris-16", "75016"),
    ("Paris 17e", "paris-17", "75017"),
    ("Paris 18e", "paris-18", "75018"),
    ("Paris 19e", "paris-19", "75019"),
    ("Paris 20e", "paris-20", "75020"),
    # Inner suburbs
    ("Boulogne-Billancourt", "boulogne-billancourt", "92100"),
    ("Neuilly-sur-Seine", "neuilly-sur-seine", "92200"),
    ("Levallois-Perret", "levallois-perret", "92300"),
    ("Issy-les-Moulineaux", "issy-les-moulineaux", "92130"),
    ("Saint-Denis", "saint-denis", "93200"),
    ("Montreuil", "montreuil", "93100"),
    ("Vincennes", "vincennes", "94300"),
    ("Saint-Mandé", "saint-mande", "94160"),
]

# Playwright timing config (seconds)
NAV_DELAY_MIN: float = 2.0
NAV_DELAY_MAX: float = 5.0
SCROLL_DELAY_MIN: float = 0.5
SCROLL_DELAY_MAX: float = 1.5

# Paths
DATA_DIR: str = "data"
SCREENSHOTS_DIR: str = "screenshots"
AGENCIES_JSON: str = f"{DATA_DIR}/agences_immo.json"
AGENCIES_CSV: str = f"{DATA_DIR}/agences_immo.csv"
EMAILS_JSON: str = f"{DATA_DIR}/emails_generated.json"
STATE_JSON: str = f"{DATA_DIR}/state.json"

# User-agent pool
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]
