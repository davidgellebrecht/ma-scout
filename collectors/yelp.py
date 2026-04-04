"""
collectors/yelp.py — Yelp Fusion API Collector

Searches for landscaping companies on Yelp in Orange County and collects
review data.  The Yelp Fusion API is Yelp's official way to access
business listings — it returns ratings, review counts, categories,
and the 3 most recent reviews.

Data flow:
    Yelp Fusion API → Business listings → Company models → SQLite

Requires: YELP_API_KEY in config.py or .streamlit/secrets.toml
Free tier: 5,000 API calls/day — more than enough for our needs.
"""

from __future__ import annotations

import time
from datetime import date, datetime

import requests

import config
from models import Company


def collect_yelp(conn) -> int:
    """
    Search Yelp for landscaping companies in Orange County target cities,
    fetch review data, and upsert into the database.

    Returns the number of companies ingested.
    """
    from db import upsert_company

    if not config.YELP_API_KEY:
        print("  ⚠  YELP_API_KEY not set — loading demo Yelp data")
        companies = _demo_data()
        for c in companies:
            c.generate_id()
            upsert_company(conn, c)
        return len(companies)

    headers = {"Authorization": f"Bearer {config.YELP_API_KEY}"}
    count = 0

    for city in config.TARGET_CITIES:
        businesses = _search_businesses(city, headers)
        print(f"    {city}: {len(businesses)} Yelp results")

        for biz in businesses:
            company = _biz_to_company(biz, city)
            if company:
                # Fetch reviews for recency data
                reviews = _get_reviews(biz["id"], headers)
                if reviews:
                    _enrich_with_reviews(company, reviews)
                company.generate_id()
                upsert_company(conn, company)
                count += 1

            time.sleep(0.1)  # be polite to the API

    return count


def _search_businesses(city: str, headers: dict) -> list[dict]:
    """Search Yelp for landscaping businesses in a specific city."""
    url = "https://api.yelp.com/v3/businesses/search"
    params = {
        "term": "landscaping",
        "location": f"{city}, CA",
        "categories": "landscaping",
        "limit": 50,
        "sort_by": "review_count",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("businesses", [])
    except Exception as e:
        print(f"  ⚠  Yelp search error for {city}: {e}")
        return []


def _get_reviews(business_id: str, headers: dict) -> list[dict]:
    """Fetch the 3 most recent reviews for a Yelp business."""
    url = f"https://api.yelp.com/v3/businesses/{business_id}/reviews"
    params = {"limit": 3, "sort_by": "newest"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("reviews", [])
    except Exception as e:
        print(f"  ⚠  Yelp reviews error for {business_id}: {e}")
        return []


def _biz_to_company(biz: dict, city: str) -> Company | None:
    """Convert a Yelp business result to a Company model."""
    try:
        coords = biz.get("coordinates", {})
        location = biz.get("location", {})
        return Company(
            business_name=biz.get("name", "Unknown"),
            address=" ".join(location.get("display_address", [])),
            city=city,
            county="Orange",
            lat=coords.get("latitude"),
            lon=coords.get("longitude"),
            phone=biz.get("phone"),
            yelp_business_id=biz.get("id"),
            yelp_rating=biz.get("rating"),
            yelp_review_count=biz.get("review_count", 0),
            source="yelp",
        )
    except Exception as e:
        print(f"  ⚠  Skipping Yelp business: {e}")
        return None


def _enrich_with_reviews(company: Company, reviews: list[dict]):
    """Extract the most recent review date from Yelp reviews."""
    dates = []
    for review in reviews:
        time_created = review.get("time_created", "")
        if time_created:
            try:
                dt = datetime.fromisoformat(time_created.replace("Z", "+00:00"))
                dates.append(dt.date())
            except ValueError:
                pass

    if dates:
        company.yelp_last_review_date = max(dates)


def _demo_data() -> list[Company]:
    """Demo Yelp data for testing without API credentials."""
    return [
        Company(
            business_name="Pacific Landscape Maintenance",
            city="Costa Mesa",
            county="Orange",
            lat=33.6461,
            lon=-117.9187,
            yelp_business_id="demo_yelp_001",
            yelp_rating=4.5,
            yelp_review_count=38,
            yelp_last_review_date=date(2023, 6, 20),
            source="yelp",
        ),
        Company(
            business_name="Sunrise Garden Care",
            city="Rancho Santa Margarita",
            county="Orange",
            lat=33.6409,
            lon=-117.6031,
            yelp_business_id="demo_yelp_003",
            yelp_rating=4.5,
            yelp_review_count=15,
            yelp_last_review_date=date(2022, 1, 8),
            source="yelp",
        ),
        Company(
            business_name="Hernandez Yard Service",
            city="Garden Grove",
            county="Orange",
            lat=33.7743,
            lon=-117.9379,
            yelp_business_id="demo_yelp_005",
            yelp_rating=4.0,
            yelp_review_count=9,
            yelp_last_review_date=date(2021, 9, 3),
            source="yelp",
        ),
        Company(
            business_name="South County Grounds",
            city="Mission Viejo",
            county="Orange",
            lat=33.5965,
            lon=-117.6590,
            yelp_business_id="demo_yelp_011",
            yelp_rating=3.5,
            yelp_review_count=5,
            yelp_last_review_date=date(2019, 12, 15),
            source="yelp",
        ),
    ]
