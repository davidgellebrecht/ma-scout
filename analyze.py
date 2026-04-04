#!/usr/bin/env python3
"""
analyze.py — Stage 2: Signal Analysis Orchestrator

Takes the companies collected by scout.py and runs each of the 4
acquisition signal layers against them.  Each layer independently
evaluates whether a company shows signs of being a good acquisition
target, and produces a standardised result dict.

Think of this step as running each company through 4 different
"diagnostic tests" — each test checks for a different symptom of
acquisition readiness.

Usage:
    python3 analyze.py

Output:
    Writes Signal records to the signals table in data/mascout.db.
"""

import sys
import time
from datetime import datetime

import config
from db import (
    get_connection,
    get_companies,
    get_permits_for_company,
    get_street_view_analysis,
    insert_signal,
)
from models import Signal

# ── Import all layer classes ──────────────────────────────────────────────────
from layers.cslb_lifecycle import CSLBLifecycleLayer
from layers.digital_ghost import DigitalGhostLayer
from layers.fbn_sweep import FBNSweepLayer
from layers.digital_distress import DigitalDistressLayer
from layers.nextdoor_referral import NextdoorReferralLayer
from layers.permit_pipeline import PermitPipelineLayer
from layers.fleet_aging import FleetAgingLayer

# ── Layer registry ───────────────────────────────────────────────────────────
# Order: free/fast layers first, paid layers last.
ALL_LAYERS = [
    # Free layers
    CSLBLifecycleLayer(),        # free — CSLB public data
    DigitalGhostLayer(),         # free — review data already in DB
    FBNSweepLayer(),             # free — County Clerk FBN filings
    DigitalDistressLayer(),      # free — Google Maps low-rated businesses
    NextdoorReferralLayer(),     # free — Nextdoor referral mentions
    PermitPipelineLayer(),    # free — permit data already in DB
    FleetAgingLayer(),        # paid — Claude Vision API
]


def run_analysis(conn=None) -> int:
    """
    Run all enabled layers against all companies.
    Returns the total number of signals generated.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    companies = get_companies(conn)
    if not companies:
        print("  No companies in database. Run scout.py first.")
        return 0

    enabled = [
        layer for layer in ALL_LAYERS
        if config.LAYERS.get(layer.name, False)
    ]

    print(f"  Running {len(enabled)} layer(s) against {len(companies)} companies...\n")

    total_signals = 0

    for i, company in enumerate(companies, 1):
        # Convert Company model to dict for layer consumption
        company_dict = company.model_dump()

        # Attach permit records (needed by permit_pipeline layer)
        if config.LAYERS.get("permit_pipeline"):
            company_dict["_permits"] = get_permits_for_company(conn, company.id)

        # Attach street view analysis (needed by fleet_aging layer)
        if config.LAYERS.get("fleet_aging"):
            company_dict["_street_view_analysis"] = get_street_view_analysis(
                conn, company.id
            )

        for layer in enabled:
            result = layer.run(company_dict)

            # Persist the signal
            signal = Signal(
                company_id=company.id,
                layer_name=result["layer"],
                signal=result["signal"],
                score=result["score"],
                detail=result["detail"],
                data=result.get("data", {}),
            )
            insert_signal(conn, signal)
            total_signals += 1

        # Progress indicator
        if i % 5 == 0 or i == len(companies):
            sys.stdout.write(
                f"\r  Analysed {i}/{len(companies)} companies "
                f"({total_signals} signals generated)"
            )
            sys.stdout.flush()

    print("\n")

    if close_conn:
        conn.close()

    return total_signals


def main():
    """Run the full analysis pipeline."""
    print()
    print("═" * 60)
    print("  M&A Scout  ·  Signal Analysis")
    print(f"  {config.REGION}")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print("═" * 60)
    print()

    # Show which layers are enabled
    for layer in ALL_LAYERS:
        status = "ON" if config.LAYERS.get(layer.name, False) else "OFF"
        paid_tag = " (PAID)" if layer.paid else ""
        print(f"  [{status}]  {layer.label}{paid_tag}")
    print()

    start_time = time.time()
    total_signals = run_analysis()
    elapsed = time.time() - start_time

    print("─" * 60)
    print(f"  Analysis complete in {elapsed:.1f}s")
    print(f"  {total_signals} signal records written to database")
    print()


if __name__ == "__main__":
    main()
