"""
collectors/google_places.py — Google Maps Places API Collector

Searches for landscaping companies in Orange County using the Google Maps
Places API, then fetches detailed review data for each result.  The Places
API is Google's way of exposing business listing data — ratings, reviews,
photos, hours — for any business that appears on Google Maps.

Data flow:
    Google Places API → Business listings → Company models → SQLite

Requires: GOOGLE_MAPS_API_KEY in config.py or .streamlit/secrets.toml
Cost: Pay-as-you-go (~$17 per 1,000 Place Details requests)
"""

from __future__ import annotations

import time
from datetime import date, datetime

import requests

import config
from models import Company


def collect_google_places(conn) -> int:
    """
    Search Google Maps for landscaping companies in each target city,
    fetch review details, and upsert into the database.

    Returns the number of companies ingested.
    """
    from db import upsert_company

    if not config.GOOGLE_MAPS_API_KEY:
        print("  ⚠  GOOGLE_MAPS_API_KEY not set — loading demo Google data")
        companies = _demo_data()
        for c in companies:
            c.generate_id()
            upsert_company(conn, c)
        return len(companies)

    count = 0
    for city in config.TARGET_CITIES:
        query = f"landscaping company in {city}, CA"
        places = _text_search(query)
        print(f"    {city}: {len(places)} results")

        for place in places:
            company = _place_to_company(place, city)
            if company:
                # Fetch detailed review info
                details = _get_place_details(place["place_id"])
                if details:
                    _enrich_with_details(company, details)
                company.generate_id()
                upsert_company(conn, company)
                count += 1

            time.sleep(0.2)  # respect rate limits

    return count


def _text_search(query: str) -> list[dict]:
    """
    Use Google Places Text Search to find businesses matching a query.
    Returns a list of place dicts with place_id, name, address, etc.
    """
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": query,
        "key": config.GOOGLE_MAPS_API_KEY,
        "type": "establishment",
    }

    results = []
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])

        # Follow next_page_token for more results (max 60 total)
        while data.get("next_page_token") and len(results) < 60:
            time.sleep(2)  # Google requires a short delay before using the token
            params["pagetoken"] = data["next_page_token"]
            params.pop("query", None)
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            results.extend(data.get("results", []))

    except Exception as e:
        print(f"  ⚠  Google Places search error: {e}")

    return results


def _get_place_details(place_id: str) -> dict | None:
    """
    Fetch detailed info for a single place, including reviews.
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "key": config.GOOGLE_MAPS_API_KEY,
        "fields": "name,rating,user_ratings_total,reviews,website,formatted_phone_number,url",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("result", {})
    except Exception as e:
        print(f"  ⚠  Place details error for {place_id}: {e}")
        return None


def _place_to_company(place: dict, city: str) -> Company | None:
    """Convert a Google Places search result to a Company model."""
    try:
        location = place.get("geometry", {}).get("location", {})
        return Company(
            business_name=place.get("name", "Unknown"),
            address=place.get("formatted_address", ""),
            city=city,
            county="Orange",
            lat=location.get("lat"),
            lon=location.get("lng"),
            google_place_id=place.get("place_id"),
            google_rating=place.get("rating"),
            google_review_count=place.get("user_ratings_total", 0),
            source="google_places",
        )
    except Exception as e:
        print(f"  ⚠  Skipping place: {e}")
        return None


def _enrich_with_details(company: Company, details: dict):
    """Add review details to a Company model from Place Details response."""
    company.website = details.get("website", company.website)
    company.phone = details.get("formatted_phone_number", company.phone)
    company.google_rating = details.get("rating", company.google_rating)
    company.google_review_count = details.get("user_ratings_total", company.google_review_count)

    # Find the most recent review date
    reviews = details.get("reviews", [])
    if reviews:
        latest_time = max(r.get("time", 0) for r in reviews)
        if latest_time:
            company.google_last_review_date = date.fromtimestamp(latest_time)

        # Calculate owner response rate (reviews where owner replied)
        owner_responses = sum(
            1 for r in reviews
            if r.get("author_url", "").endswith("/reviews")  # proxy for owner reply
        )
        # Note: Google Places API doesn't directly expose owner responses in v1.
        # This is a placeholder — real implementation would use the v2 API or
        # scrape the business profile page.


def _demo_data() -> list[Company]:
    """Demo Google Places data for testing without API credentials."""
    return [
        Company(
            business_name="Pacific Landscape Maintenance",
            city="Costa Mesa",
            county="Orange",
            lat=33.6461,
            lon=-117.9187,
            google_place_id="demo_gp_001",
            google_rating=4.6,
            google_review_count=47,
            google_last_review_date=date(2023, 8, 15),
            source="google_places",
        ),
        Company(
            business_name="Sunrise Garden Care",
            city="Rancho Santa Margarita",
            county="Orange",
            lat=33.6409,
            lon=-117.6031,
            google_place_id="demo_gp_003",
            google_rating=4.8,
            google_review_count=23,
            google_last_review_date=date(2022, 3, 10),
            source="google_places",
        ),
        Company(
            business_name="Hernandez Yard Service",
            city="Garden Grove",
            county="Orange",
            lat=33.7743,
            lon=-117.9379,
            google_place_id="demo_gp_005",
            google_rating=4.2,
            google_review_count=12,
            google_last_review_date=date(2021, 11, 5),
            source="google_places",
        ),
        Company(
            business_name="Tony's Lawn & Garden",
            city="Orange",
            county="Orange",
            lat=33.7879,
            lon=-117.8531,
            google_place_id="demo_gp_008",
            google_rating=4.5,
            google_review_count=31,
            google_last_review_date=date(2023, 1, 20),
            source="google_places",
        ),
        Company(
            business_name="South County Grounds",
            city="Mission Viejo",
            county="Orange",
            lat=33.5965,
            lon=-117.6590,
            google_place_id="demo_gp_011",
            google_rating=3.9,
            google_review_count=8,
            google_last_review_date=date(2020, 6, 12),
            source="google_places",
        ),
    ]
