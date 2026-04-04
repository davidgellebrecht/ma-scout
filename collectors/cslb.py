"""
collectors/cslb.py — CSLB License Data Collector

Pulls C-27 (Landscaping) license data from the California Contractors
State License Board.  Three data paths, tried in order:

    1. CSLB Data Portal (free, no account needed)
       Downloads an Excel file filtered by county + C-27 classification
       from cslb.ca.gov/onlineservices/dataportal/ListByCounty

    2. Apify cloud scraper (free tier, needs account)
       Runs an existing Apify actor to scrape CSLB search results.
       Set APIFY_API_TOKEN + APIFY_CSLB_ACTOR_ID in config.

    3. Demo data (always works)
       Realistic fake data so the pipeline can be tested end-to-end.

The CSLB Data Portal is the preferred path because it provides the
official dataset directly — no scraping, no rate limits, no accounts.
"""

from __future__ import annotations

import io
import sys
from datetime import date, datetime

import requests

import config
from models import Company


# ── County codes used by the CSLB Data Portal form ──────────────────────────
# These are the option values in the County dropdown on ListByCounty.aspx
COUNTY_CODES = {
    "Orange": "30",
    "Los Angeles": "19",
    "San Diego": "37",
}


def collect_cslb(conn) -> int:
    """
    Pull CSLB C-27 license data and upsert into the database.
    Tries the Data Portal first, then Apify, then demo data.
    Returns the number of companies ingested.
    """
    from db import upsert_company

    county = config.get_county()

    # Path 1: CSLB Data Portal (free, no account)
    companies = _fetch_from_portal(county)

    # Path 2: Apify (free tier)
    if not companies and config.APIFY_API_TOKEN and config.APIFY_CSLB_ACTOR_ID:
        print("    Portal unavailable, trying Apify...")
        companies = _fetch_from_apify()

    # Path 3: Demo data
    if not companies:
        print("    Using demo CSLB data")
        companies = _demo_data(county)

    count = 0
    for company in companies:
        company.generate_id()
        upsert_company(conn, company)
        count += 1

    return count


def _fetch_from_portal(county: str) -> list:
    """
    Download C-27 contractor data from the CSLB Data Portal.

    The portal at cslb.ca.gov/onlineservices/dataportal/ListByCounty
    provides filtered Excel downloads by county + classification.
    It uses ASP.NET ViewState, so we need a session to maintain state.
    """
    county_code = COUNTY_CODES.get(county)
    if not county_code:
        print("    County '{}' not mapped to CSLB code".format(county))
        return []

    url = "https://www.cslb.ca.gov/onlineservices/dataportal/ListByCounty.aspx"

    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })

        # Step 1: GET the page to obtain ViewState and form tokens
        print("    Fetching CSLB Data Portal form...")
        resp = session.get(url, timeout=30)
        resp.raise_for_status()

        # Extract ASP.NET hidden fields
        from html.parser import HTMLParser

        class HiddenFieldParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.fields = {}
            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "input" and attrs_dict.get("type") == "hidden":
                    name = attrs_dict.get("name", "")
                    value = attrs_dict.get("value", "")
                    if name:
                        self.fields[name] = value

        parser = HiddenFieldParser()
        parser.feed(resp.text)

        if "__VIEWSTATE" not in parser.fields:
            print("    Could not extract ViewState from CSLB portal")
            return []

        # Step 2: POST to select C-27 classification and county, request download
        print("    Requesting C-27 data for {} County...".format(county))

        form_data = {
            "__VIEWSTATE": parser.fields.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": parser.fields.get("__VIEWSTATEGENERATOR", ""),
            "__EVENTVALIDATION": parser.fields.get("__EVENTVALIDATION", ""),
            # These field names may vary — CSLB uses ASP.NET WebForms
            # which auto-generates control IDs. Common patterns:
            "ctl00$MainContent$ClassificationList": "C27",
            "ctl00$MainContent$CountyList": county_code,
            "ctl00$MainContent$btnGetList": "Get List",
        }

        resp2 = session.post(url, data=form_data, timeout=60)

        # Check if we got an Excel file back
        content_type = resp2.headers.get("Content-Type", "")
        if "excel" in content_type or "spreadsheet" in content_type or "octet-stream" in content_type:
            return _parse_excel(resp2.content, county)
        elif resp2.status_code == 200:
            # Might have returned an HTML page with results or errors
            # Try to find a download link in the response
            if "No records found" in resp2.text:
                print("    No C-27 records found for {} County".format(county))
                return []
            print("    Portal returned HTML (may need different form field names)")
            return []

    except requests.RequestException as e:
        print("    CSLB Portal request failed: {}".format(e))
    except Exception as e:
        print("    CSLB Portal error: {}".format(e))

    return []


def _parse_excel(content: bytes, county: str) -> list:
    """Parse an Excel file from the CSLB Data Portal into Company models."""
    try:
        import pandas as pd
        df = pd.read_excel(io.BytesIO(content))
        print("    Downloaded {} records from CSLB portal".format(len(df)))

        companies = []
        for _, row in df.iterrows():
            try:
                company = Company(
                    business_name=str(row.get("Business Name", row.get("BUSINESS NAME", "Unknown"))),
                    license_number=str(row.get("License Number", row.get("LICENSE NUMBER", ""))),
                    license_type=str(row.get("Entity Type", row.get("ENTITY TYPE", ""))),
                    license_status=str(row.get("Status", row.get("LICENSE STATUS", "Active"))),
                    license_issue_date=_parse_date(row.get("Issue Date", row.get("ISSUE DATE"))),
                    license_expiry_date=_parse_date(row.get("Expire Date", row.get("EXPIRATION DATE"))),
                    license_class="C-27",
                    address=str(row.get("Address", row.get("ADDRESS", ""))),
                    city=str(row.get("City", row.get("CITY", ""))),
                    zip_code=str(row.get("Zip", row.get("ZIP", ""))),
                    county=county,
                    phone=str(row.get("Phone", row.get("PHONE NUMBER", ""))),
                    source="cslb",
                )
                companies.append(company)
            except Exception:
                continue

        return companies

    except ImportError:
        print("    openpyxl not installed — can't parse Excel. pip install openpyxl")
        return []
    except Exception as e:
        print("    Error parsing Excel: {}".format(e))
        return []


def _fetch_from_apify() -> list:
    """
    Call an Apify actor to scrape CSLB search results.
    Fallback when the Data Portal form submission doesn't work.
    """
    try:
        from apify_client import ApifyClient
    except ImportError:
        print("    apify-client not installed")
        return []

    client = ApifyClient(config.APIFY_API_TOKEN)

    run_input = {
        "licenseClass": config.CSLB_LICENSE_CLASS,
        "county": config.get_county(),
        "status": "Active",
    }

    print("    Starting Apify actor {}...".format(config.APIFY_CSLB_ACTOR_ID))
    run = client.actor(config.APIFY_CSLB_ACTOR_ID).call(run_input=run_input)

    companies = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        company = _parse_apify_item(item)
        if company:
            companies.append(company)

    print("    Apify returned {} C-27 licenses".format(len(companies)))
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
        print("    Skipping malformed CSLB record: {}".format(e))
        return None


def _parse_date(val) -> date | None:
    """Parse various date formats from scraped data."""
    if not val:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(val), fmt).date()
        except ValueError:
            continue
    return None


# ─── Demo Data ───────────────────────────────────────────────────────────────

def _demo_data(county: str) -> list:
    """Return realistic demo companies per county for testing."""

    if county == "Orange":
        return [
            Company(business_name="Pacific Landscape Maintenance", owner_name="Robert J. Chen",
                    license_number="548721", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(1991, 3, 15), license_expiry_date=date(2026, 3, 31),
                    license_class="C-27", address="1842 Monrovia Ave", city="Costa Mesa",
                    zip_code="92627", county="Orange", phone="(714) 555-0142", source="cslb"),
            Company(business_name="Green Valley Landscaping Inc", owner_name="Michael Torres",
                    license_number="632154", license_type="Corporation", license_status="Active",
                    license_issue_date=date(1998, 7, 22), license_expiry_date=date(2027, 7, 31),
                    license_class="C-27", city="Newport Beach", zip_code="92660", county="Orange",
                    website="www.greenvalleylandscaping.com", source="cslb"),
            Company(business_name="Sunrise Garden Care", owner_name="David Park",
                    license_number="487293", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(1987, 11, 3), license_expiry_date=date(2026, 6, 15),
                    license_class="C-27", city="Rancho Santa Margarita", zip_code="92688",
                    county="Orange", source="cslb"),
            Company(business_name="OC Premier Landscapes", owner_name="Sarah Martinez",
                    license_number="891234", license_type="LLC", license_status="Active",
                    license_issue_date=date(2015, 2, 10), license_expiry_date=date(2027, 2, 28),
                    license_class="C-27", city="Irvine", zip_code="92614", county="Orange",
                    website="www.ocpremierlandscapes.com", source="cslb"),
            Company(business_name="Hernandez Yard Service", owner_name="Carlos Hernandez",
                    license_number="512847", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(1989, 5, 20), license_expiry_date=date(2026, 5, 31),
                    license_class="C-27", city="Garden Grove", zip_code="92844", county="Orange",
                    source="cslb"),
            Company(business_name="Laguna Coast Landscapes", owner_name="William Nguyen",
                    license_number="723456", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(1995, 9, 8), license_expiry_date=date(2026, 9, 30),
                    license_class="C-27", city="Laguna Niguel", zip_code="92677", county="Orange",
                    source="cslb"),
            Company(business_name="All Seasons Landscaping Corp", owner_name="James Wilson",
                    license_number="834567", license_type="Corporation", license_status="Active",
                    license_issue_date=date(2005, 4, 1), license_expiry_date=date(2027, 3, 31),
                    license_class="C-27", city="Irvine", zip_code="92612", county="Orange",
                    employee_count_est=25, website="www.allseasonslandscaping.com", source="cslb"),
            Company(business_name="Tony's Lawn & Garden", owner_name="Antonio Rossi",
                    license_number="456123", license_type="Individual", license_status="Active",
                    license_issue_date=date(1984, 2, 14), license_expiry_date=date(2026, 8, 15),
                    license_class="C-27", city="Orange", zip_code="92867", county="Orange",
                    source="cslb"),
            Company(business_name="Dana Point Garden Design", owner_name="Jennifer Liu",
                    license_number="945678", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(2018, 6, 15), license_expiry_date=date(2028, 6, 30),
                    license_class="C-27", city="Dana Point", zip_code="92629", county="Orange",
                    website="www.danapointgardens.com", source="cslb"),
            Company(business_name="Mission Landscape Services", owner_name="Richard Kim",
                    license_number="567890", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(1993, 1, 10), license_expiry_date=date(2026, 7, 31),
                    license_class="C-27", city="Laguna Hills", zip_code="92656", county="Orange",
                    source="cslb"),
            Company(business_name="South County Grounds", owner_name="George Thompson",
                    license_number="498321", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(1986, 8, 22), license_expiry_date=date(2026, 4, 30),
                    license_class="C-27", city="Mission Viejo", zip_code="92692", county="Orange",
                    source="cslb"),
            Company(business_name="Newport Hardscape & Design", owner_name="Brian Foster",
                    license_number="756234", license_type="Corporation", license_status="Active",
                    license_issue_date=date(2002, 11, 5), license_expiry_date=date(2027, 11, 30),
                    license_class="C-27", city="Newport Beach", zip_code="92660", county="Orange",
                    employee_count_est=15, website="www.newporthardscape.com", source="cslb"),
        ]

    elif county == "Los Angeles":
        return [
            Company(business_name="Sunset Landscape Group", owner_name="Ricardo Perez",
                    license_number="534891", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(1990, 6, 12), license_expiry_date=date(2026, 6, 30),
                    license_class="C-27", city="Pasadena", zip_code="91101", county="Los Angeles",
                    source="cslb"),
            Company(business_name="Beverly Hills Grounds", owner_name="Alan Westbrook",
                    license_number="612345", license_type="Corporation", license_status="Active",
                    license_issue_date=date(2001, 3, 1), license_expiry_date=date(2027, 2, 28),
                    license_class="C-27", city="Beverly Hills", zip_code="90210", county="Los Angeles",
                    website="www.bhgrounds.com", employee_count_est=20, source="cslb"),
            Company(business_name="Malibu Garden Masters", owner_name="Steven Cho",
                    license_number="478923", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(1988, 9, 20), license_expiry_date=date(2026, 9, 30),
                    license_class="C-27", city="Malibu", zip_code="90265", county="Los Angeles",
                    source="cslb"),
        ]

    elif county == "San Diego":
        return [
            Company(business_name="La Jolla Landscape Design", owner_name="Patrick Sullivan",
                    license_number="567234", license_type="Sole Ownership", license_status="Active",
                    license_issue_date=date(1992, 4, 15), license_expiry_date=date(2026, 4, 30),
                    license_class="C-27", city="La Jolla", zip_code="92037", county="San Diego",
                    source="cslb"),
            Company(business_name="North County Landscape Inc", owner_name="Maria Gonzalez",
                    license_number="689012", license_type="Corporation", license_status="Active",
                    license_issue_date=date(2003, 8, 1), license_expiry_date=date(2027, 7, 31),
                    license_class="C-27", city="Carlsbad", zip_code="92009", county="San Diego",
                    website="www.northcountylandscape.com", employee_count_est=12, source="cslb"),
            Company(business_name="Coronado Yard Care", owner_name="Dennis Webb",
                    license_number="445678", license_type="Individual", license_status="Active",
                    license_issue_date=date(1985, 11, 10), license_expiry_date=date(2026, 11, 30),
                    license_class="C-27", city="Coronado", zip_code="92118", county="San Diego",
                    source="cslb"),
        ]

    return []
