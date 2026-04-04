"""
collectors/fbn.py — Fictitious Business Name (FBN) Sweep Collector

In California, when someone starts a business under a name other than
their own legal name (like "John Doe Landscaping"), they must file a
Fictitious Business Name Statement with the County Clerk.  These filings
are public records.

The acquisition thesis: if someone filed an FBN 15-20+ years ago and is
still operating as a sole proprietor, they are likely approaching
retirement age and haven't modernized their corporate structure.  They
have a valuable aged client list but no succession plan.

Data flow:
    County Clerk FBN search → Filing records → Company models → SQLite

Each county has a different online portal:
    - Orange County: https://cr.ocgov.com/recorderworks/
    - LA County: https://www.lavote.gov/
    - San Diego: https://arcc.sdcounty.ca.gov/

Status: Demo data for now.  Real scraping requires Apify or Selenium
because these county portals use JavaScript-heavy search forms.
"""

from __future__ import annotations

from datetime import date, datetime

import config
from models import Company


def collect_fbn(conn) -> int:
    """
    Search county clerk FBN filings for old landscaping businesses
    and upsert into the database.

    Returns the number of records ingested.
    """
    from db import upsert_company

    market = config.get_market()
    county = market["county"]

    print("    County: {} — FBN portal: {}".format(county, market["fbn_clerk_url"]))

    # TODO: implement real FBN scraping per county portal
    companies = _demo_data(county)

    count = 0
    for company in companies:
        company.generate_id()
        upsert_company(conn, company)
        count += 1

    return count


def _demo_data(county: str) -> list:
    """Return realistic FBN demo data for each supported county."""

    if county == "Orange":
        return [
            Company(
                business_name="Rodriguez Landscape & Garden",
                owner_name="Manuel Rodriguez",
                city="Santa Ana",
                county="Orange",
                zip_code="92707",
                lat=33.7455, lon=-117.8677,
                source="fbn",
            ),
            Company(
                business_name="Dave's Complete Yard Care",
                owner_name="David Kowalski",
                city="Tustin",
                county="Orange",
                zip_code="92780",
                lat=33.7458, lon=-117.8263,
                source="fbn",
            ),
            Company(
                business_name="Golden State Gardening",
                owner_name="James Pham",
                city="Westminster",
                county="Orange",
                zip_code="92683",
                lat=33.7592, lon=-117.9940,
                source="fbn",
            ),
            Company(
                business_name="Precision Lawn Service",
                owner_name="Robert Mitchell",
                city="Laguna Hills",
                county="Orange",
                zip_code="92653",
                lat=33.5969, lon=-117.7070,
                source="fbn",
            ),
        ]

    elif county == "Los Angeles":
        return [
            Company(
                business_name="Valley Green Landscaping",
                owner_name="Carlos Mendez",
                city="Pasadena",
                county="Los Angeles",
                zip_code="91101",
                lat=34.1478, lon=-118.1445,
                source="fbn",
            ),
            Company(
                business_name="Westside Yard Masters",
                owner_name="Frank DeLuca",
                city="Santa Monica",
                county="Los Angeles",
                zip_code="90403",
                lat=34.0259, lon=-118.4965,
                source="fbn",
            ),
            Company(
                business_name="Pacific Palisades Garden Co",
                owner_name="Thomas Nakamura",
                city="Pacific Palisades",
                county="Los Angeles",
                zip_code="90272",
                lat=34.0360, lon=-118.5310,
                source="fbn",
            ),
        ]

    elif county == "San Diego":
        return [
            Company(
                business_name="Coastal Landscape Pros",
                owner_name="Miguel Santos",
                city="Encinitas",
                county="San Diego",
                zip_code="92024",
                lat=33.0370, lon=-117.2920,
                source="fbn",
            ),
            Company(
                business_name="Del Mar Garden Service",
                owner_name="William Chen",
                city="Del Mar",
                county="San Diego",
                zip_code="92014",
                lat=32.9595, lon=-117.2653,
                source="fbn",
            ),
            Company(
                business_name="Rancho Lawn & Tree",
                owner_name="Joe Ramirez",
                city="Rancho Santa Fe",
                county="San Diego",
                zip_code="92067",
                lat=33.0203, lon=-117.2028,
                source="fbn",
            ),
        ]

    return []
