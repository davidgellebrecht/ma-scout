#!/usr/bin/env python3
"""
scout.py — Stage 1: Data Collection Orchestrator

Runs all enabled collectors in sequence, pulling data from CSLB, Yelp,
FBN filings, Google Maps distress signals, and Nextdoor referrals into
the SQLite database.

Usage:
    python3 scout.py
    python3 scout.py --market "Los Angeles County"

Output:
    Populates data/mascout.db with company and permit records.
"""

import sys
import time
from datetime import datetime

import config
from db import get_connection, get_company_count


def main():
    """Run all enabled data collectors for the active market."""

    # Allow market override from CLI
    for i, arg in enumerate(sys.argv):
        if arg == "--market" and i + 1 < len(sys.argv):
            market_name = sys.argv[i + 1]
            if market_name in config.MARKETS:
                config.ACTIVE_MARKET = market_name

    region = config.get_region()
    total_steps = 8

    print()
    print("=" * 60)
    print("  M&A Scout  .  Data Collection")
    print("  {}".format(region))
    print("  {}".format(datetime.now().strftime("%Y-%m-%d  %H:%M:%S")))
    print("=" * 60)
    print()

    conn = get_connection()
    start_count = get_company_count(conn)
    start_time = time.time()

    # ── FREE Collectors ──────────────────────────────────────────────────

    # 1. CSLB licenses
    print("  [1/{}] CSLB C-27 License Scrape".format(total_steps))
    from collectors.cslb import collect_cslb
    cslb_count = collect_cslb(conn)
    print("         -> {} license records ingested\n".format(cslb_count))

    # 2. Yelp Fusion
    print("  [2/{}] Yelp Fusion API".format(total_steps))
    from collectors.yelp import collect_yelp
    yelp_count = collect_yelp(conn)
    print("         -> {} Yelp business records\n".format(yelp_count))

    # 3. FBN Sweep (County Clerk filings)
    if config.LAYERS.get("fbn_sweep"):
        print("  [3/{}] FBN Sweep ({} County Clerk)".format(
            total_steps, config.get_county()))
        from collectors.fbn import collect_fbn
        fbn_count = collect_fbn(conn)
        print("         -> {} FBN records\n".format(fbn_count))
    else:
        print("  [3/{}] FBN Sweep -- SKIPPED\n".format(total_steps))

    # 4. Digital Distress (Google Maps low-rated)
    if config.LAYERS.get("digital_distress"):
        print("  [4/{}] Digital Distress (Google Maps)".format(total_steps))
        from collectors.google_distress import collect_google_distress
        distress_count = collect_google_distress(conn)
        print("         -> {} distressed businesses\n".format(distress_count))
    else:
        print("  [4/{}] Digital Distress -- SKIPPED\n".format(total_steps))

    # 5. Nextdoor Referrals
    if config.LAYERS.get("nextdoor_referral"):
        print("  [5/{}] Nextdoor Referral Reverse-Search".format(total_steps))
        from collectors.nextdoor import collect_nextdoor
        nextdoor_count = collect_nextdoor(conn)
        print("         -> {} referral records\n".format(nextdoor_count))
    else:
        print("  [5/{}] Nextdoor Referrals -- SKIPPED\n".format(total_steps))

    # ── PREMIUM Collectors ───────────────────────────────────────────────

    # 6. Google Places (PREMIUM)
    if config.GOOGLE_MAPS_API_KEY:
        print("  [6/{}] Google Maps Places API (PREMIUM)".format(total_steps))
        from collectors.google_places import collect_google_places
        google_count = collect_google_places(conn)
        print("         -> {} Google business records\n".format(google_count))
    else:
        print("  [6/{}] Google Places -- SKIPPED (no API key)\n".format(total_steps))

    # 7. Building Permits (PREMIUM)
    if config.LAYERS.get("permit_pipeline"):
        print("  [7/{}] City Building Permits".format(total_steps))
        from collectors.permits import collect_permits
        permit_count = collect_permits(conn)
        print("         -> {} permit records\n".format(permit_count))
    else:
        print("  [7/{}] Building Permits -- SKIPPED\n".format(total_steps))

    # 8. Street View (PREMIUM)
    if config.LAYERS.get("fleet_aging"):
        print("  [8/{}] Google Street View Capture".format(total_steps))
        from collectors.street_view import collect_street_view
        sv_count = collect_street_view(conn)
        print("         -> {} Street View images\n".format(sv_count))
    else:
        print("  [8/{}] Street View -- SKIPPED\n".format(total_steps))

    # ── Summary ──────────────────────────────────────────────────────────
    end_count = get_company_count(conn)
    elapsed = time.time() - start_time

    print("-" * 60)
    print("  Collection complete in {:.1f}s".format(elapsed))
    print("  Market: {}".format(region))
    print("  Companies: {} -> {} (+{} new)".format(
        start_count, end_count, end_count - start_count))
    print("  Database: {}".format(config.DB_PATH))
    print()

    conn.close()


if __name__ == "__main__":
    main()
