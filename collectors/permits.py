"""
collectors/permits.py — OC City Building Permit Collector

Scrapes building permit data from Orange County city portals to identify
landscaping contractors working on large residential projects.  Each city
has a different permit portal, so this module implements per-city scrapers.

Currently supported cities:
    - Demo mode (all cities) — returns realistic sample data
    - Irvine, Newport Beach — placeholder for real scrapers (TODO)

Building permits are public records that municipalities must make
available.  They list the contractor name, project address, scope of work,
and estimated value — everything we need to identify small shops taking on
big projects.

Data flow:
    City permit portals → Permit records → SQLite (permit_records table)
    Then: Fuzzy-match contractor names to Company records in the companies table
"""

from datetime import date, datetime

from thefuzz import fuzz

import config
from models import Company


def collect_permits(conn) -> int:
    """
    Scrape permits from configured cities and store in the database.
    Then fuzzy-match contractor names to existing companies.

    Returns the number of permit records ingested.
    """
    from db import get_companies, insert_permit

    print("  Collecting permit records...")
    permits = _demo_permits()  # TODO: implement real scrapers per city

    count = 0
    for permit in permits:
        insert_permit(conn, permit)
        count += 1

    # ── Fuzzy-match contractors to known companies ───────────────────────
    print("  Matching contractors to companies...")
    companies = get_companies(conn)
    _match_permits_to_companies(conn, permits, companies)

    return count


def _match_permits_to_companies(conn, permits: list[dict], companies: list[Company]):
    """
    Use fuzzy string matching to link permit contractor names to Company
    records.  'Fuzzy matching' means it can handle slight variations in
    spelling — e.g. "Tony's Lawn & Garden" vs "Tonys Lawn and Garden".
    """
    for permit in permits:
        contractor = permit.get("contractor_name", "")
        if not contractor:
            continue

        best_match = None
        best_score = 0

        for company in companies:
            score = fuzz.token_sort_ratio(contractor, company.business_name)
            if score > best_score and score >= 75:  # 75% similarity threshold
                best_score = score
                best_match = company

        if best_match:
            conn.execute(
                "UPDATE permit_records SET company_id = ? WHERE contractor_name = ? AND company_id IS NULL",
                (best_match.id, contractor)
            )
            conn.commit()


def _demo_permits() -> list[dict]:
    """Demo permit data for testing without real scrapers."""
    return [
        {
            "permit_number": "BLD-2025-04521",
            "city": "Newport Beach",
            "project_address": "1 Crystal Cove, Newport Coast, CA 92657",
            "project_description": "Complete landscape renovation: hardscape, pool deck, "
                                   "retaining walls, irrigation, drought-tolerant planting",
            "contractor_name": "Laguna Coast Landscapes",
            "permit_date": "2025-09-15",
            "estimated_value": 185000.0,
            "status": "Active",
            "source_url": "https://www.newportbeachca.gov/permits",
        },
        {
            "permit_number": "BLD-2025-03892",
            "city": "Newport Beach",
            "project_address": "22 Harbor Island Dr, Newport Beach, CA 92660",
            "project_description": "Front and rear yard redesign, new walkways, "
                                   "outdoor kitchen, landscape lighting",
            "contractor_name": "Pacific Landscape Maintenance",
            "permit_date": "2025-08-01",
            "estimated_value": 95000.0,
            "status": "Active",
            "source_url": "https://www.newportbeachca.gov/permits",
        },
        {
            "permit_number": "GRD-2025-02145",
            "city": "Irvine",
            "project_address": "55 Waterford, Irvine, CA 92618",
            "project_description": "Backyard renovation: paver patio, fire pit, "
                                   "raised planter beds, turf conversion",
            "contractor_name": "Hernandez Yard Service",
            "permit_date": "2025-11-01",
            "estimated_value": 72000.0,
            "status": "Active",
            "source_url": "https://www.cityofirvine.org/permits",
        },
        {
            "permit_number": "GRD-2025-02389",
            "city": "Irvine",
            "project_address": "112 Shady Canyon Dr, Irvine, CA 92603",
            "project_description": "Full estate landscaping: 2.5 acre property, "
                                   "Mediterranean garden, water features, specimen trees",
            "contractor_name": "Tony's Lawn & Garden",
            "permit_date": "2025-10-15",
            "estimated_value": 245000.0,
            "status": "Active",
            "source_url": "https://www.cityofirvine.org/permits",
        },
        {
            "permit_number": "BLD-2025-01567",
            "city": "Laguna Beach",
            "project_address": "401 Cliff Dr, Laguna Beach, CA 92651",
            "project_description": "Hillside erosion control, retaining walls, "
                                   "native plant restoration",
            "contractor_name": "Sunrise Garden Care",
            "permit_date": "2025-07-20",
            "estimated_value": 128000.0,
            "status": "Active",
            "source_url": "https://www.lagunabeachcity.net/permits",
        },
        {
            "permit_number": "GRD-2026-00234",
            "city": "Mission Viejo",
            "project_address": "28100 La Paz Rd, Mission Viejo, CA 92692",
            "project_description": "HOA common area landscape upgrade, Phase 1 of 3",
            "contractor_name": "South County Grounds",
            "permit_date": "2026-01-10",
            "estimated_value": 310000.0,
            "status": "Active",
            "source_url": "https://www.cityofmissionviejo.org/permits",
        },
        {
            "permit_number": "BLD-2025-05123",
            "city": "Dana Point",
            "project_address": "25 Monarch Bay Dr, Dana Point, CA 92629",
            "project_description": "Residential front yard: new driveway, walkway, low-water garden",
            "contractor_name": "Dana Point Garden Design",
            "permit_date": "2025-12-05",
            "estimated_value": 38000.0,
            "status": "Completed",
            "source_url": "https://www.danapoint.org/permits",
        },
    ]
