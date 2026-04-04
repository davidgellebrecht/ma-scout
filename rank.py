#!/usr/bin/env python3
"""
rank.py — Stage 3: Scoring & Ranking + Full Pipeline Runner

This can run in two modes:

  1. Standalone: Score and rank companies already in the database
     (after scout.py + analyze.py have run).

  2. Full pipeline: Run all three stages end-to-end (scout → analyze → rank)
     with the --full flag.

The Opportunity Score is computed identically to Parcel Scout's approach:
equal-weighted across all 4 signals (25 points each, 100 total).
A company with no signals scores 0; all 4 signals = 100.

Usage:
    python3 rank.py           # rank existing data
    python3 rank.py --full    # run complete pipeline

Output:
    ranked_<timestamp>.csv
    ranked_<timestamp>.json
"""

import csv
import json
import sys
import time
from datetime import datetime

import config
from db import get_connection, get_ranked_companies
from models import CompanyWithSignals


# ── Signal labels (human-readable names for each layer) ──────────────────────
SIGNAL_LABELS = {
    # Free layers
    "cslb_lifecycle":    "License Lifecycle",
    "fbn_sweep":         "FBN Sweep",
    "digital_distress":  "Digital Distress",
    "nextdoor_referral": "Nextdoor Referral",
    "workers_comp":      "No Workers Comp",
    "website_decay":     "Website Decay",
    "sba_loan":          "SBA Loan Flag",
    "sos_status":        "Entity Status",
    "bbb_complaints":    "BBB Complaints",
    "bond_amount":       "Min Bond",
    "google_closed":     "Google Closed",
    "review_fatigue":    "Owner Fatigue",
    "property_change":   "Property Turnover",
    # Premium layers
    "digital_ghost":     "Digital Ghost",
    "permit_pipeline":   "Permit Stress",
    "fleet_aging":       "Fleet Aging",
}


# ─── Console Output ─────────────────────────────────────────────────────────

def print_ranked(results: list[CompanyWithSignals]):
    """Print every company ranked by Opportunity Score, highest first."""
    total_signals = sum(1 for v in config.LAYERS.values() if v)
    total_signals = max(total_signals, 1)

    print(f"\n{'═' * 78}")
    print(f"  M&A Scout  ·  Opportunity Rankings  ·  {config.REGION}")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}  "
          f"·  {len(results)} compan{'y' if len(results) == 1 else 'ies'}")
    print(f"  Score = signals fired / {total_signals} possible  "
          f"(equal weight, {100/total_signals:.0f} pts each)")
    print(f"{'═' * 78}\n")

    header = (f"  {'Rank':>4}  {'Score':>8}  {'Sigs':>5}  "
              f"{'Business':^30}  {'City':^16}  {'Entity':^14}")
    divider = (f"  {'─'*4}  {'─'*8}  {'─'*5}  "
               f"{'─'*30}  {'─'*16}  {'─'*14}")
    print(header)
    print(divider)

    for rank, r in enumerate(results, 1):
        c = r.company
        score = r.opportunity_score
        fired = r.signals_fired
        name = (c.business_name or "")[:30]
        city = (c.city or "")[:16]
        entity = (c.license_type or "")[:14]

        # Visual score bar
        bar_len = 12
        filled = round(score / 100 * bar_len)
        score_bar = "█" * filled + "░" * (bar_len - filled)
        score_str = f"{score:>5.1f}/100"

        print(f"  {rank:>4}  {score_str}  {fired:>2}/{total_signals}  "
              f"{name:^30}  {city:^16}  {entity:^14}")

        # Show which signals fired
        fired_labels = [
            SIGNAL_LABELS.get(s.layer_name, s.layer_name)
            for s in r.signals if s.signal
        ]
        if fired_labels:
            tags = "  ".join(f"[✓] {lbl}" for lbl in fired_labels)
            print(f"        {score_bar}  {tags}")
        else:
            print(f"        {score_bar}  (no signals fired)")
        print()

    # Summary footer
    scores = [r.opportunity_score for r in results]
    with_hits = sum(1 for s in scores if s > 0)
    print(f"{'─' * 78}")
    if scores:
        print(f"  {with_hits}/{len(results)} companies have at least one signal  ·  "
              f"Top score: {max(scores):.1f}/100  ·  "
              f"Avg: {sum(scores)/len(scores):.1f}/100\n")
    else:
        print("  No companies to rank.\n")


# ─── Export ──────────────────────────────────────────────────────────────────

def to_flat_dicts(results: list[CompanyWithSignals]) -> list[dict]:
    """Flatten CompanyWithSignals into flat dicts for CSV/JSON export."""
    flat = []
    for r in results:
        row = r.company.model_dump()
        # Convert dates to strings for serialization
        for key, val in row.items():
            if hasattr(val, "isoformat"):
                row[key] = val.isoformat()

        row["opportunity_score"] = r.opportunity_score
        row["signals_fired"] = r.signals_fired
        row["signals_total"] = r.signals_total

        # Add per-layer signal details
        for signal in r.signals:
            prefix = f"layer_{signal.layer_name}"
            row[f"{prefix}_signal"] = signal.signal
            row[f"{prefix}_score"] = signal.score
            row[f"{prefix}_detail"] = signal.detail
            for k, v in signal.data.items():
                row[f"{prefix}_{k}"] = v

        flat.append(row)
    return flat


def export_csv(flat: list[dict], path: str):
    """Export flat dicts to CSV."""
    if not flat:
        return
    all_keys = list(dict.fromkeys(k for row in flat for k in row.keys()))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, restval="")
        writer.writeheader()
        writer.writerows(flat)


def export_json(flat: list[dict], path: str):
    """Export flat dicts to JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(flat, f, indent=2, ensure_ascii=False, default=str)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    full_pipeline = "--full" in sys.argv

    if full_pipeline:
        print()
        print("═" * 60)
        print("  M&A Scout  ·  Full Pipeline Run")
        print(f"  {config.REGION}")
        print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
        print("═" * 60)
        print()

        # Stage 1: Data Collection
        print("  ── Stage 1: Data Collection ────────────────────────────\n")
        from scout import main as scout_main
        scout_main()

        # Stage 2: Signal Analysis
        print("  ── Stage 2: Signal Analysis ────────────────────────────\n")
        from analyze import main as analyze_main
        analyze_main()

        print("  ── Stage 3: Scoring & Ranking ──────────────────────────\n")

    # ── Load and rank ────────────────────────────────────────────────────
    conn = get_connection()
    results = get_ranked_companies(conn)
    conn.close()

    if not results:
        print("  No companies in database. Run: python3 rank.py --full\n")
        return

    # ── Print rankings ───────────────────────────────────────────────────
    print_ranked(results)

    # ── Export ────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"ranked_{ts}.csv"
    json_path = f"ranked_{ts}.json"

    flat = to_flat_dicts(results)
    export_csv(flat, csv_path)
    export_json(flat, json_path)

    print(f"  Saved → {csv_path}")
    print(f"  Saved → {json_path}\n")


if __name__ == "__main__":
    main()
