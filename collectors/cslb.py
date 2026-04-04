"""
collectors/cslb.py — CSLB License Data Collector

Scrapes the California Contractors State License Board (CSLB) for C-27
(Landscaping) licenses in Orange County using Apify, a cloud scraping
platform.  Apify runs a "web scraper actor" on their servers, which is
more reliable than scraping from our machine because CSLB rate-limits
direct requests.

Data flow:
    Apify actor → CSLB website → JSON results → Company models → SQLite

The CSLB public search is at:
    https://www.cslb.ca.gov/OnlineServices/CheckLicenseII/CheckLicense.aspx

Free tier: 30 Apify compute units/month — enough for ~500 license lookups.
"""

from __future__ import annotations

import sys
from datetime import date, datetime

import config
from models import Company


def collect_cslb(conn) -> int:
    """
    Run the Apify CSLB scraper and upsert results into the database.

    Returns the number of companies ingested.

    If the Apify API token or actor ID is not configured, falls back to
    a demo dataset so the pipeline can still be tested end-to-end.
    """
    from db import upsert_company

    if not config.APIFY_API_TOKEN or not config.APIFY_CSLB_ACTOR_ID:
        print("  ⚠  APIFY credentials not set — loading demo CSLB data")
        companies = _demo_data()
    else:
        companies = _fetch_from_apify()

    count = 0
    for company in companies:
        company.generate_id()
        upsert_company(conn, company)
        count += 1

    return count


def _fetch_from_apify() -> list[Company]:
    """
    Call the Apify actor to scrape CSLB C-27 licenses in Orange County.

    The actor is expected to return JSON items with fields like:
        license_number, business_name, owner_name, license_type,
        license_status, issue_date, expiry_date, address, city, zip, etc.

    You'll need to create or find an Apify actor that scrapes the CSLB
    search page.  Set APIFY_CSLB_ACTOR_ID in config.py to the actor's ID.
    """
    try:
        from apify_client import ApifyClient
    except ImportError:
        print("  ⚠  apify-client not installed — run: pip install apify-client")
        return _demo_data()

    client = ApifyClient(config.APIFY_API_TOKEN)

    run_input = {
        "licenseClass": config.CSLB_LICENSE_CLASS,
        "county": config.get_county(),
        "status": "Active",
    }

    print(f"  Starting Apify actor {config.APIFY_CSLB_ACTOR_ID}...")
    run = client.actor(config.APIFY_CSLB_ACTOR_ID).call(run_input=run_input)

    companies = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        company = _parse_apify_item(item)
        if company:
            companies.append(company)

    print(f"  Apify returned {len(companies)} C-27 licenses")
    return companies


def _parse_apify_item(item: dict) -> Company | None:
    """Convert a raw Apify result item into a Company model."""
    try:
        return Company(
            business_name=item.get("businessName", item.get("business_name", "Unknown")),
            dba_name=item.get("dbaName", item.get("dba_name")),
            owner_name=item.get("ownerName", item.get("owner_name")),
            license_number=item.get("licenseNumber", item.get("license_number")),
            license_type=item.get("licenseType", item.get("license_type")),
            license_status=item.get("licenseStatus", item.get("license_status", "Active")),
            license_issue_date=_parse_date(item.get("issueDate", item.get("issue_date"))),
            license_expiry_date=_parse_date(item.get("expiryDate", item.get("expiry_date"))),
            license_class=config.CSLB_LICENSE_CLASS,
            address=item.get("address"),
            city=item.get("city"),
            zip_code=item.get("zip", item.get("zipCode", item.get("zip_code"))),
            county=config.get_county(),
            phone=item.get("phone"),
            source="cslb",
        )
    except Exception as e:
        print(f"  ⚠  Skipping malformed CSLB record: {e}")
        return None


def _parse_date(val) -> date | None:
    """Parse various date formats from scraped data."""
    if not val:
        return None
    if isinstance(val, date):
        return val
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(val), fmt).date()
        except ValueError:
            continue
    return None


# ─── Demo Data ───────────────────────────────────────────────────────────────
# Realistic fake companies so the pipeline works without Apify credentials.
# These demonstrate the range of signals the CSLB lifecycle layer detects.

def _demo_data() -> list[Company]:
    """Return a set of realistic demo companies for testing."""
    return [
        Company(
            business_name="Pacific Landscape Maintenance",
            owner_name="Robert J. Chen",
            license_number="548721",
            license_type="Sole Ownership",
            license_status="Active",
            license_issue_date=date(1991, 3, 15),
            license_expiry_date=date(2026, 3, 31),
            license_class="C-27",
            address="1842 Monrovia Ave",
            city="Costa Mesa",
            zip_code="92627",
            county="Orange",
            phone="(714) 555-0142",
            source="cslb",
        ),
        Company(
            business_name="Green Valley Landscaping Inc",
            owner_name="Michael Torres",
            license_number="632154",
            license_type="Corporation",
            license_status="Active",
            license_issue_date=date(1998, 7, 22),
            license_expiry_date=date(2027, 7, 31),
            license_class="C-27",
            address="3501 Jamboree Rd Ste 200",
            city="Newport Beach",
            zip_code="92660",
            county="Orange",
            phone="(949) 555-0287",
            website="www.greenvalleylandscaping.com",
            source="cslb",
        ),
        Company(
            business_name="Sunrise Garden Care",
            owner_name="David Park",
            license_number="487293",
            license_type="Sole Ownership",
            license_status="Active",
            license_issue_date=date(1987, 11, 3),
            license_expiry_date=date(2026, 6, 15),
            license_class="C-27",
            address="22461 Antonio Pkwy",
            city="Rancho Santa Margarita",
            zip_code="92688",
            county="Orange",
            phone="(949) 555-0193",
            source="cslb",
        ),
        Company(
            business_name="OC Premier Landscapes",
            owner_name="Sarah Martinez",
            license_number="891234",
            license_type="LLC",
            license_status="Active",
            license_issue_date=date(2015, 2, 10),
            license_expiry_date=date(2027, 2, 28),
            license_class="C-27",
            address="18012 Sky Park Circle",
            city="Irvine",
            zip_code="92614",
            county="Orange",
            phone="(949) 555-0341",
            website="www.ocpremierlandscapes.com",
            source="cslb",
        ),
        Company(
            business_name="Hernandez Yard Service",
            owner_name="Carlos Hernandez",
            license_number="512847",
            license_type="Sole Ownership",
            license_status="Active",
            license_issue_date=date(1989, 5, 20),
            license_expiry_date=date(2026, 5, 31),
            license_class="C-27",
            address="8742 Garden Grove Blvd",
            city="Garden Grove",
            zip_code="92844",
            county="Orange",
            phone="(714) 555-0456",
            source="cslb",
        ),
        Company(
            business_name="Laguna Coast Landscapes",
            owner_name="William Nguyen",
            license_number="723456",
            license_type="Sole Ownership",
            license_status="Active",
            license_issue_date=date(1995, 9, 8),
            license_expiry_date=date(2026, 9, 30),
            license_class="C-27",
            address="30012 Crown Valley Pkwy",
            city="Laguna Niguel",
            zip_code="92677",
            county="Orange",
            phone="(949) 555-0578",
            source="cslb",
        ),
        Company(
            business_name="All Seasons Landscaping Corp",
            owner_name="James Wilson",
            license_number="834567",
            license_type="Corporation",
            license_status="Active",
            license_issue_date=date(2005, 4, 1),
            license_expiry_date=date(2027, 3, 31),
            license_class="C-27",
            address="2600 Michelson Dr Ste 1600",
            city="Irvine",
            zip_code="92612",
            county="Orange",
            phone="(949) 555-0692",
            website="www.allseasonslandscaping.com",
            employee_count_est=25,
            source="cslb",
        ),
        Company(
            business_name="Tony's Lawn & Garden",
            owner_name="Antonio Rossi",
            license_number="456123",
            license_type="Individual",
            license_status="Active",
            license_issue_date=date(1984, 2, 14),
            license_expiry_date=date(2026, 8, 15),
            license_class="C-27",
            address="1105 N Tustin St",
            city="Orange",
            zip_code="92867",
            county="Orange",
            phone="(714) 555-0823",
            source="cslb",
        ),
        Company(
            business_name="Dana Point Garden Design",
            owner_name="Jennifer Liu",
            license_number="945678",
            license_type="Sole Ownership",
            license_status="Active",
            license_issue_date=date(2018, 6, 15),
            license_expiry_date=date(2028, 6, 30),
            license_class="C-27",
            address="34052 Del Obispo St",
            city="Dana Point",
            zip_code="92629",
            county="Orange",
            phone="(949) 555-0934",
            website="www.danapointgardens.com",
            source="cslb",
        ),
        Company(
            business_name="Mission Landscape Services",
            owner_name="Richard Kim",
            license_number="567890",
            license_type="Sole Ownership",
            license_status="Active",
            license_issue_date=date(1993, 1, 10),
            license_expiry_date=date(2026, 7, 31),
            license_class="C-27",
            address="26701 Quail Creek",
            city="Laguna Hills",
            zip_code="92656",
            county="Orange",
            phone="(949) 555-0145",
            source="cslb",
        ),
        Company(
            business_name="South County Grounds",
            owner_name="George Thompson",
            license_number="498321",
            license_type="Sole Ownership",
            license_status="Active",
            license_issue_date=date(1986, 8, 22),
            license_expiry_date=date(2026, 4, 30),
            license_class="C-27",
            address="27742 Vista Del Lago",
            city="Mission Viejo",
            zip_code="92692",
            county="Orange",
            phone="(949) 555-0267",
            source="cslb",
        ),
        Company(
            business_name="Newport Hardscape & Design",
            owner_name="Brian Foster",
            license_number="756234",
            license_type="Corporation",
            license_status="Active",
            license_issue_date=date(2002, 11, 5),
            license_expiry_date=date(2027, 11, 30),
            license_class="C-27",
            address="1600 Dove St Ste 300",
            city="Newport Beach",
            zip_code="92660",
            county="Orange",
            phone="(949) 555-0389",
            website="www.newporthardscape.com",
            employee_count_est=15,
            source="cslb",
        ),
    ]
