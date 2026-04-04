"""
collectors/google_distress.py — Digital Distress Google Maps Collector

Searches Google Maps for landscaping businesses showing signs of
operational distress: low ratings, unclaimed profiles, or reviews
mentioning declining service quality.

No paid API needed — this collector uses either:
    1. Manual CSV import (user exports from Instant Data Scraper browser extension)
    2. Direct scraping of public Google Maps search results (TODO)

The key insight: a business with 3.5 stars or lower, no "Claimed" profile,
and reviews saying "they used to be great but lately..." is an owner who
is stressed and might jump at an offer.

Data flow:
    Google Maps search results → CSV/scrape → Company models → SQLite
"""

from __future__ import annotations

from datetime import date, datetime

import config
from models import Company


def collect_google_distress(conn) -> int:
    """
    Collect distressed landscaping businesses from Google Maps.

    Returns the number of records ingested.
    """
    from db import upsert_company

    county = config.get_county()
    cities = config.get_cities()

    # TODO: implement real Google Maps scraping or CSV import
    # For now, use demo data
    companies = _demo_data(county)

    count = 0
    for company in companies:
        company.generate_id()
        upsert_company(conn, company)
        count += 1

    return count


def _demo_data(county: str) -> list:
    """Demo distressed businesses for each county."""

    if county == "Orange":
        return [
            Company(
                business_name="Quick Cut Landscaping",
                owner_name="Steve Barker",
                city="Anaheim",
                county="Orange",
                zip_code="92801",
                lat=33.8366, lon=-117.9143,
                google_rating=2.8,
                google_review_count=14,
                google_last_review_date=date(2025, 11, 3),
                source="google_distress",
            ),
            Company(
                business_name="OC Yard Guys",
                city="Fountain Valley",
                county="Orange",
                zip_code="92708",
                lat=33.7092, lon=-117.9536,
                google_rating=3.2,
                google_review_count=7,
                google_last_review_date=date(2025, 8, 15),
                source="google_distress",
            ),
            Company(
                business_name="A-1 Lawn Maintenance",
                owner_name="Dennis Park",
                city="Buena Park",
                county="Orange",
                zip_code="90620",
                lat=33.8675, lon=-117.9981,
                google_rating=3.0,
                google_review_count=22,
                google_last_review_date=date(2026, 1, 10),
                source="google_distress",
            ),
        ]

    elif county == "Los Angeles":
        return [
            Company(
                business_name="LA Budget Landscaping",
                city="Glendale",
                county="Los Angeles",
                zip_code="91201",
                lat=34.1425, lon=-118.2551,
                google_rating=2.5,
                google_review_count=18,
                google_last_review_date=date(2025, 10, 22),
                source="google_distress",
            ),
            Company(
                business_name="Reliable Yard Care",
                owner_name="Eddie Ruiz",
                city="Torrance",
                county="Los Angeles",
                zip_code="90501",
                lat=33.8358, lon=-118.3406,
                google_rating=3.1,
                google_review_count=9,
                google_last_review_date=date(2025, 6, 5),
                source="google_distress",
            ),
        ]

    elif county == "San Diego":
        return [
            Company(
                business_name="SoCal Quick Lawn",
                city="Escondido",
                county="San Diego",
                zip_code="92025",
                lat=33.1192, lon=-117.0864,
                google_rating=2.9,
                google_review_count=11,
                google_last_review_date=date(2025, 9, 18),
                source="google_distress",
            ),
            Company(
                business_name="Vista Landscape & Haul",
                owner_name="Richard Gomez",
                city="Vista",
                county="San Diego",
                zip_code="92083",
                lat=33.2000, lon=-117.2426,
                google_rating=3.3,
                google_review_count=6,
                google_last_review_date=date(2025, 12, 1),
                source="google_distress",
            ),
        ]

    return []
