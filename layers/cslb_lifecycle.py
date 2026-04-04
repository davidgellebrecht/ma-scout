"""
layers/cslb_lifecycle.py — Strategy 1: CSLB License Lifecycle Tracker

This layer analyses CSLB license data to identify "retirement candidates."
The core thesis: a landscaping contractor who has been a sole proprietor
for 25+ years without ever incorporating (forming a Corp or LLC) is very
likely an owner-operator approaching retirement age.

Signals that fire:
    - Sole proprietor / individual entity type (never incorporated)
    - License active for 25+ years
    - License renewal coming up within 180 days
    - Estimated owner age in the 60+ range (based on license start date)

Score components (each 0.0 – 1.0, averaged):
    - years_score:     how long the license has been active (25–40 years → 0.0–1.0)
    - renewal_score:   how soon the license expires (180 → 0 days → 0.0–1.0)
    - entity_score:    1.0 if sole proprietor, 0.0 otherwise
    - age_score:       estimated owner age scaled (55–75 → 0.0–1.0)
"""

from __future__ import annotations

from datetime import date

import config
from layers.base import BaseLayer


class CSLBLifecycleLayer(BaseLayer):
    name = "cslb_lifecycle"
    label = "License Lifecycle"
    paid = False  # CSLB data is public; Apify free tier is sufficient

    def run(self, company: dict) -> dict:
        """Analyse a company's CSLB license for retirement signals."""

        license_type = company.get("license_type", "")
        issue_date_raw = company.get("license_issue_date")
        expiry_date_raw = company.get("license_expiry_date")

        # Parse dates if they're strings (from SQLite)
        issue_date = _to_date(issue_date_raw)
        expiry_date = _to_date(expiry_date_raw)

        if not issue_date:
            return self._empty_result("No license issue date available")

        today = date.today()

        # ── Sub-signal 1: Years active ───────────────────────────────────────
        years_active = (today - issue_date).days / 365.25
        long_running = years_active >= config.CSLB_MIN_YEARS_ACTIVE
        # Scale: 25 years → 0.0, 40+ years → 1.0
        years_score = self._clamp((years_active - 25) / 15) if long_running else 0.0

        # ── Sub-signal 2: Entity type (sole proprietor = never incorporated) ─
        is_target_entity = license_type in config.CSLB_ENTITY_TYPES_TARGET
        entity_score = 1.0 if is_target_entity else 0.0

        # ── Sub-signal 3: Renewal proximity ──────────────────────────────────
        days_to_expiry = (expiry_date - today).days if expiry_date else 999
        renewal_imminent = 0 < days_to_expiry <= config.CSLB_RENEWAL_WARNING_DAYS
        # Scale: 180 days → 0.0, 0 days → 1.0
        if renewal_imminent:
            renewal_score = self._clamp(1.0 - (days_to_expiry / config.CSLB_RENEWAL_WARNING_DAYS))
        else:
            renewal_score = 0.0

        # ── Sub-signal 4: Estimated owner age ────────────────────────────────
        # Heuristic: most landscape contractors start their business between
        # ages 25–35.  We estimate using 30 as the midpoint.
        est_age_at_start = 30
        est_current_age = est_age_at_start + years_active
        # Scale: 55 → 0.0, 75+ → 1.0
        age_score = self._clamp((est_current_age - 55) / 20)

        # ── Composite score ──────────────────────────────────────────────────
        # Weight entity type and years most heavily
        weights = {
            "years": 0.30,
            "entity": 0.30,
            "renewal": 0.20,
            "age": 0.20,
        }
        composite = (
            weights["years"]   * years_score
            + weights["entity"]  * entity_score
            + weights["renewal"] * renewal_score
            + weights["age"]     * age_score
        )
        composite = self._clamp(composite)

        # ── Signal fires? ────────────────────────────────────────────────────
        # Primary signal: sole proprietor with 25+ years
        # Bonus: renewal imminent makes it even stronger
        signal = is_target_entity and long_running

        # ── Build detail string ──────────────────────────────────────────────
        parts = []
        if is_target_entity:
            parts.append(f"{license_type}")
        if long_running:
            parts.append(f"{years_active:.0f} years active")
        if renewal_imminent:
            parts.append(f"renews in {days_to_expiry} days")
        parts.append(f"est. age ~{est_current_age:.0f}")

        if signal:
            detail = f"Retirement candidate: {', '.join(parts)}"
        else:
            detail = f"Not flagged: {', '.join(parts)}"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "license_type": license_type,
                "years_active": round(years_active, 1),
                "is_sole_proprietor": is_target_entity,
                "days_to_expiry": days_to_expiry,
                "renewal_imminent": renewal_imminent,
                "est_current_age": round(est_current_age),
                "years_score": round(years_score, 3),
                "entity_score": round(entity_score, 3),
                "renewal_score": round(renewal_score, 3),
                "age_score": round(age_score, 3),
            },
            "paid": self.paid,
        }


def _to_date(val) -> date | None:
    """Convert various date representations to a date object."""
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val:
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None
