"""
layers/fbn_sweep.py — Strategy: FBN Sweep (Fictitious Business Name)

Analyses companies sourced from County Clerk FBN filings to identify
owner-operators who filed a DBA name 15-25 years ago and never
modernised their business structure.

The acquisition thesis: an FBN filing from 2004 + no website + no
social media + still operating as a sole proprietor = a "ghost" with
a valuable, aged client list and no succession plan.

Signals:
    - FBN filed 15+ years ago
    - No website detected
    - No corporate entity transition (still sole prop via CSLB cross-ref)
    - Operating in a wealthy zip code (high-value routes)

Score components:
    - filing_age_score:    how old the FBN filing is (15-25 yrs → 0.0-1.0)
    - no_web_score:        1.0 if no website, 0.0 if has one
    - wealthy_zip_score:   1.0 if in a high-value zip, 0.3 otherwise
"""

from __future__ import annotations

from datetime import date

import config
from layers.base import BaseLayer


class FBNSweepLayer(BaseLayer):
    name = "fbn_sweep"
    label = "FBN Sweep"
    paid = False

    def run(self, company: dict) -> dict:
        """Analyse an FBN-sourced company for acquisition signals."""

        source = company.get("source", "")
        has_website = bool(company.get("website"))
        zip_code = company.get("zip_code", "")
        license_type = company.get("license_type", "")

        # FBN filing age — if we have a license issue date, use that as proxy
        # for how long the business has been operating.  Otherwise, assume
        # the FBN source means it's an old filing.
        issue_date_raw = company.get("license_issue_date")
        if issue_date_raw:
            issue_date = _to_date(issue_date_raw)
            if issue_date:
                years_operating = (date.today() - issue_date).days / 365.25
            else:
                years_operating = 18  # assume mid-range for FBN source
        elif source == "fbn":
            years_operating = 18  # FBN filings are pre-filtered to 15-25 years
        else:
            years_operating = 0

        is_old_filing = years_operating >= config.FBN_MIN_FILING_AGE_YEARS

        # ── Sub-signals ──────────────────────────────────────────────────────
        # Filing age: 15 years → 0.0, 25+ years → 1.0
        if is_old_filing:
            filing_age_score = self._clamp(
                (years_operating - config.FBN_MIN_FILING_AGE_YEARS)
                / (config.FBN_MAX_FILING_AGE_YEARS - config.FBN_MIN_FILING_AGE_YEARS)
            )
        else:
            filing_age_score = 0.0

        # No website = digital ghost with aged client list
        no_web_score = 1.0 if not has_website else 0.0

        # Wealthy zip code = high-value route
        wealthy_zips = config.get_wealthy_zips()
        in_wealthy_zip = zip_code in wealthy_zips
        wealthy_zip_score = 1.0 if in_wealthy_zip else 0.3

        # Still sole proprietor (never incorporated)
        is_sole_prop = license_type in config.CSLB_ENTITY_TYPES_TARGET
        sole_prop_score = 1.0 if is_sole_prop else 0.5

        # ── Composite ────────────────────────────────────────────────────────
        composite = (
            0.30 * filing_age_score
            + 0.30 * no_web_score
            + 0.20 * wealthy_zip_score
            + 0.20 * sole_prop_score
        )
        composite = self._clamp(composite)

        # ── Signal fires? ────────────────────────────────────────────────────
        # Core signal: old FBN filing + no website
        signal = is_old_filing and not has_website

        # For non-FBN-sourced companies, only fire if they also have
        # CSLB data confirming sole proprietorship
        if source != "fbn" and not is_sole_prop:
            signal = False

        # ── Detail ───────────────────────────────────────────────────────────
        if signal:
            parts = ["{:.0f} years operating".format(years_operating)]
            if not has_website:
                parts.append("no website")
            if in_wealthy_zip:
                parts.append("wealthy zip ({})".format(zip_code))
            detail = "FBN ghost: {}".format(", ".join(parts))
        else:
            parts = []
            if not is_old_filing:
                parts.append("filing too recent ({:.0f}yr)".format(years_operating))
            if has_website:
                parts.append("has website")
            detail = "Not flagged: {}".format(", ".join(parts) or "insufficient data")

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "years_operating": round(years_operating, 1),
                "has_website": has_website,
                "in_wealthy_zip": in_wealthy_zip,
                "zip_code": zip_code,
                "source": source,
                "filing_age_score": round(filing_age_score, 3),
                "no_web_score": round(no_web_score, 3),
                "wealthy_zip_score": round(wealthy_zip_score, 3),
            },
            "paid": self.paid,
        }


def _to_date(val) -> date | None:
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val:
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None
