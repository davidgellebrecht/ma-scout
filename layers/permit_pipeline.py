"""
layers/permit_pipeline.py — Strategy 3: Permit-to-Acquisition Pipeline

This layer identifies small landscaping companies that are potentially
overwhelmed by large projects.  When a 3-person crew takes on a $200K
backyard remodel in Newport Coast, they're likely stressed — and that
stress makes them receptive to acquisition or partnership offers.

Why this matters:
    Small shops often take on "monster" projects to keep the lights on,
    but these jobs can break their operations.  A buyer can approach not
    just to acquire, but to offer subcontracting help as a foot in the
    door for a future buyout.

Signals:
    - Small crew (1-5 people) on large ($50K+) permits
    - Multiple concurrent large permits = severely overextended
    - Total permit value significantly exceeds estimated annual revenue

Score components:
    - permit_scale_score:  total permit value vs company size
    - concurrency_score:   number of simultaneous large permits
    - crew_stress_score:   crew size vs permit complexity
"""

from __future__ import annotations

from datetime import date, datetime

import config
from layers.base import BaseLayer


class PermitPipelineLayer(BaseLayer):
    name = "permit_pipeline"
    label = "Permit Stress"
    paid = False  # permit data is public record

    def run(self, company: dict) -> dict:
        """Analyse a company's permit load vs their capacity."""

        # ── Gather permit data ───────────────────────────────────────────────
        # Permits are pre-loaded from the permit_records table and attached
        # to the company dict by analyze.py before this layer runs.
        permits = company.get("_permits", [])

        if not permits:
            return self._empty_result("No permit records found")

        today = date.today()
        lookback_date = date(
            today.year,
            max(1, today.month - config.PERMIT_LOOKBACK_MONTHS),
            1
        )

        # Filter to recent permits
        recent_permits = []
        for p in permits:
            permit_date = _to_date(p.get("permit_date"))
            if permit_date and permit_date >= lookback_date:
                recent_permits.append(p)

        if not recent_permits:
            return self._empty_result("No recent permits in lookback window")

        # ── Sub-signal 1: Large permits ──────────────────────────────────────
        large_permits = [
            p for p in recent_permits
            if (p.get("estimated_value") or 0) >= config.LARGE_PERMIT_VALUE
        ]
        large_count = len(large_permits)
        total_value = sum(p.get("estimated_value", 0) for p in large_permits)

        # ── Sub-signal 2: Crew size estimate ─────────────────────────────────
        crew_size = company.get("employee_count_est")
        if not crew_size:
            # Heuristic: sole proprietors typically have 1-3 crew
            license_type = company.get("license_type", "")
            if license_type in config.CSLB_ENTITY_TYPES_TARGET:
                crew_size = 2  # assume small
            else:
                crew_size = 8  # assume moderate

        is_small_crew = crew_size <= config.SMALL_CREW_MAX

        # ── Sub-signal 3: Overextended? ──────────────────────────────────────
        overextended = (
            is_small_crew
            and large_count >= config.OVEREXTENDED_PERMIT_COUNT
        )

        # ── Scoring ──────────────────────────────────────────────────────────
        # Permit scale: $100K → 0.3, $250K → 0.7, $500K+ → 1.0
        permit_scale_score = self._clamp(total_value / 500_000)

        # Concurrency: 1 large permit → 0.3, 2 → 0.7, 3+ → 1.0
        concurrency_score = self._clamp((large_count - 0.5) / 2.5)

        # Crew stress: smaller crew + bigger permits = more stress
        if is_small_crew and large_count > 0:
            crew_stress_score = self._clamp(1.0 - (crew_size / 10))
        else:
            crew_stress_score = 0.0

        # ── Composite ────────────────────────────────────────────────────────
        composite = (
            0.35 * permit_scale_score
            + 0.35 * concurrency_score
            + 0.30 * crew_stress_score
        )
        composite = self._clamp(composite)

        # ── Signal fires? ────────────────────────────────────────────────────
        signal = is_small_crew and large_count >= 1 and total_value >= 100_000

        # ── Detail string ────────────────────────────────────────────────────
        if signal:
            detail = (
                f"Overextended: {crew_size}-person crew, "
                f"{large_count} large permit(s) totaling ${total_value:,.0f}"
            )
        else:
            parts = []
            if not is_small_crew:
                parts.append(f"larger crew ({crew_size})")
            if large_count == 0:
                parts.append("no large permits")
            elif total_value < 100_000:
                parts.append(f"permit value below threshold (${total_value:,.0f})")
            detail = f"Not flagged: {', '.join(parts) or 'insufficient data'}"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "recent_permit_count": len(recent_permits),
                "large_permit_count": large_count,
                "total_permit_value": total_value,
                "crew_size_est": crew_size,
                "is_small_crew": is_small_crew,
                "overextended": overextended,
                "permit_scale_score": round(permit_scale_score, 3),
                "concurrency_score": round(concurrency_score, 3),
                "crew_stress_score": round(crew_stress_score, 3),
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
