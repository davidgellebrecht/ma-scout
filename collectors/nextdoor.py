"""
collectors/nextdoor.py — Nextdoor Referral Reverse-Search Collector

Nextdoor is where high-ticket landscaping clients in wealthy neighborhoods
post "Who does your yard?" and "Landscaper recommendation" threads.  The
names that come up repeatedly — often just first names like "Manuel" or
"Dave" — represent valuable Routes (recurring client relationships).

In landscaping, the Route is the asset.  A sole proprietor who is
mentioned 20 times in a wealthy zip code but has no website owns a
Route worth acquiring.

Data collection approach:
    - Manual: User joins local Nextdoor groups, exports referral data to CSV
    - The collector ingests that CSV and normalises it into Company records
    - AI can later analyse mention frequency and cross-reference with CSLB

For now: demo data representing typical referral patterns per county.

Data flow:
    Nextdoor referral threads → CSV import → Company models → SQLite
"""

from __future__ import annotations

from datetime import date, datetime

import config
from models import Company


def collect_nextdoor(conn) -> int:
    """
    Ingest Nextdoor referral data (manual CSV or demo data).

    Returns the number of records ingested.
    """
    from db import upsert_company

    county = config.get_county()

    # TODO: implement CSV import for manual Nextdoor exports
    companies = _demo_data(county)

    count = 0
    for company in companies:
        company.generate_id()
        upsert_company(conn, company)
        count += 1

    return count


def _demo_data(county: str) -> list:
    """Demo Nextdoor referral data — names that appear frequently in
    local recommendation threads but have no formal web presence."""

    if county == "Orange":
        return [
            Company(
                business_name="Manuel's Gardening",
                owner_name="Manuel Gutierrez",
                city="Newport Beach",
                county="Orange",
                zip_code="92660",
                lat=33.6189, lon=-117.9298,
                source="nextdoor",
            ),
            Company(
                business_name="Dave's Weekly Lawn",
                owner_name="Dave Morrison",
                city="Laguna Beach",
                county="Orange",
                zip_code="92651",
                lat=33.5427, lon=-117.7854,
                source="nextdoor",
            ),
            Company(
                business_name="Jorge Yard Service",
                owner_name="Jorge Castillo",
                city="Dana Point",
                county="Orange",
                zip_code="92629",
                lat=33.4672, lon=-117.6981,
                source="nextdoor",
            ),
        ]

    elif county == "Los Angeles":
        return [
            Company(
                business_name="Hector's Garden Care",
                owner_name="Hector Villanueva",
                city="Beverly Hills",
                county="Los Angeles",
                zip_code="90210",
                lat=34.0901, lon=-118.4065,
                source="nextdoor",
            ),
            Company(
                business_name="Ken's Lawn Service",
                owner_name="Ken Tanaka",
                city="Palos Verdes Estates",
                county="Los Angeles",
                zip_code="90274",
                lat=33.7866, lon=-118.3915,
                source="nextdoor",
            ),
        ]

    elif county == "San Diego":
        return [
            Company(
                business_name="Arturo's Landscaping",
                owner_name="Arturo Flores",
                city="La Jolla",
                county="San Diego",
                zip_code="92037",
                lat=32.8473, lon=-117.2742,
                source="nextdoor",
            ),
            Company(
                business_name="Tim's Yard Crew",
                owner_name="Tim O'Brien",
                city="Coronado",
                county="San Diego",
                zip_code="92118",
                lat=32.6859, lon=-117.1831,
                source="nextdoor",
            ),
        ]

    return []
