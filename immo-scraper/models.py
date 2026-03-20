from __future__ import annotations
import re
import unicodedata
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class EnrichmentStatus(str, Enum):
    SCRAPED = "scraped"
    ENRICHED = "enriched"
    SCREENSHOT_DONE = "screenshot_done"
    READY_FOR_EMAIL = "ready_for_email"


def _slugify(text: str) -> str:
    """Convert text to URL-safe slug (strips accents, lowercase, hyphens)."""
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug


class Agency(BaseModel):
    # Identity
    name: str
    slug: str = Field(default="")
    address: str
    source: str  # "google_maps" | "pages_jaunes" | "sirene"
    siret: Optional[str] = None

    # Contact
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    # Google Maps
    google_maps_url: Optional[str] = None
    google_rating: Optional[float] = None
    google_review_count: Optional[int] = None
    gbp_link: Optional[str] = None
    opening_hours: Optional[dict[str, str]] = None

    # Network
    network_affiliation: Optional[str] = None  # "Century 21", "Orpi", etc. or "indépendant"

    # Enrichment
    agents_names: list[str] = Field(default_factory=list)
    has_blog: Optional[bool] = None
    site_quality: Optional[str] = None  # "modern" | "dated" | "outdated" | "none"
    is_mobile_friendly: Optional[bool] = None
    gbp_photo_count: Optional[int] = None
    gbp_last_photo_date: Optional[str] = None
    gbp_has_posts: Optional[bool] = None
    gbp_category: Optional[str] = None

    # Linkup enrichment
    director_name: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    website_tech: Optional[str] = None  # "WordPress" | "Wix" | "Squarespace" | "custom" etc.
    year_founded: Optional[int] = None
    linkup_description: Optional[str] = None

    # Lead scoring
    lead_score: Optional[float] = None
    lead_score_details: Optional[dict] = None

    # Pipeline state
    screenshot_path: Optional[str] = None
    enrichment_status: EnrichmentStatus = EnrichmentStatus.SCRAPED

    @model_validator(mode="after")
    def _generate_slug(self) -> "Agency":
        if not self.slug:
            self.slug = _slugify(self.name)
        return self
