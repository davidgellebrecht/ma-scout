"""
models.py — Pydantic Data Models

These models define the exact shape of every piece of data flowing through
M&A Scout.  Think of them as strict forms — if a field is the wrong type
or missing, Pydantic rejects it immediately rather than letting bad data
sneak through the pipeline.

Three core models:

    Company          — a landscaping business (the thing we're evaluating)
    Signal           — one acquisition signal detected by a layer
    CompanyWithSignals — a company bundled with all its signals + composite score
"""

import hashlib
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Company ─────────────────────────────────────────────────────────────────

class Company(BaseModel):
    """
    Core entity — a landscaping business identified as a potential
    acquisition target.  Stored in the SQLite `companies` table.
    """

    id: str = ""  # deterministic hash — set by generate_id() below

    # Business identity
    business_name: str
    dba_name: Optional[str] = None
    owner_name: Optional[str] = None

    # CSLB license data
    license_number: Optional[str] = None
    license_type: Optional[str] = None      # "Sole Ownership", "Corporation", "LLC", etc.
    license_status: Optional[str] = None    # "Active", "Expired", "Suspended"
    license_issue_date: Optional[date] = None
    license_expiry_date: Optional[date] = None
    license_class: Optional[str] = None     # "C-27", etc.

    # Location
    address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    phone: Optional[str] = None
    website: Optional[str] = None

    # Cross-references to review platforms
    google_place_id: Optional[str] = None
    yelp_business_id: Optional[str] = None

    # Business size estimate
    employee_count_est: Optional[int] = None

    # Review data (populated by Google/Yelp collectors)
    google_rating: Optional[float] = None
    google_review_count: Optional[int] = None
    google_last_review_date: Optional[date] = None
    yelp_rating: Optional[float] = None
    yelp_review_count: Optional[int] = None
    yelp_last_review_date: Optional[date] = None
    owner_response_rate: Optional[float] = None  # 0.0 - 1.0

    # Metadata
    first_seen: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)
    source: str = "cslb"  # "cslb", "google_places", "yelp", "permit"

    def generate_id(self) -> str:
        """
        Create a deterministic ID from the most stable identifier available.
        Priority: license_number > (business_name + city).
        """
        if self.license_number:
            seed = "cslb:{}".format(self.license_number)
        else:
            seed = "name:{}:{}".format(self.business_name, self.city or "")
        self.id = hashlib.sha256(seed.encode()).hexdigest()[:16]
        return self.id


# ─── Signal ──────────────────────────────────────────────────────────────────

class Signal(BaseModel):
    """
    A single acquisition signal detected by a layer.
    One company can have multiple signals (one per layer).
    """

    company_id: str
    layer_name: str        # "cslb_lifecycle", "digital_ghost", etc.
    signal: bool           # True = the layer fired (opportunity detected)
    score: Optional[float] = None    # 0.0 – 1.0 confidence / strength
    detail: str            # one-line human-readable explanation
    data: Dict[str, Any] = Field(default_factory=dict)  # layer-specific raw values
    created_at: datetime = Field(default_factory=datetime.now)


# ─── CompanyWithSignals ──────────────────────────────────────────────────────

class CompanyWithSignals(BaseModel):
    """
    A company bundled with all its signals and a composite opportunity score.
    Used for display in the Streamlit UI and for ranked export.
    """

    company: Company
    signals: List[Signal] = Field(default_factory=list)
    opportunity_score: float = 0.0     # 0 – 100
    signals_fired: int = 0
    signals_total: int = 4             # we have 4 layers
