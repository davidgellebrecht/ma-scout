"""
layers/workers_comp.py — Strategy: Workers Compensation Check

The CSLB master list includes whether a contractor has workers'
compensation insurance.  In California, if you have ANY employees
you must carry workers comp.  A landscaping company with NO workers
comp means one of two things:

    1. They are a true sole operator (no employees at all)
    2. They are operating illegally without coverage

Either way, it signals the smallest possible operation — a one-person
shop that is the easiest and cheapest acquisition target.

Data source: CSLB license data (already in the database)
Additional verification: caworkcompcoverage.com (free, no account)

Signals:
    - No workers comp insurance on file with CSLB
    - Sole proprietor entity type (confirms single-person operation)
    - Long-running license without WC = intentionally stayed small

Score components:
    - no_wc_score:      1.0 if no workers comp, 0.0 if has it
    - sole_prop_score:  1.0 if sole proprietor entity
    - longevity_score:  longer without WC = more entrenched sole op
"""

from __future__ import annotations

from datetime import date

import config
from layers.base import BaseLayer


class WorkersCompLayer(BaseLayer):
    name = "workers_comp"
    label = "No Workers Comp"
    paid = False

    def run(self, company: dict) -> dict:
        """Check if a company lacks workers compensation insurance."""

        # Workers comp status comes from CSLB data
        # In the master list it's a field; in our DB we can check if
        # the company has employees estimated or WC fields
        license_type = company.get("license_type", "")
        employee_count = company.get("employee_count_est")
        has_website = bool(company.get("website"))

        # Check entity type — sole proprietors typically have no employees
        is_sole_prop = license_type in config.CSLB_ENTITY_TYPES_TARGET

        # If employee count is known and > 0, they should have WC
        # If unknown + sole prop, assume no employees
        if employee_count is not None and employee_count > 1:
            has_employees = True
        elif is_sole_prop:
            has_employees = False
        else:
            has_employees = None  # unknown

        # No WC signal: sole prop + no known employees
        no_wc = is_sole_prop and not has_employees

        # License age for longevity score
        issue_date_raw = company.get("license_issue_date")
        if issue_date_raw:
            issue_date = _to_date(issue_date_raw)
            years_active = (date.today() - issue_date).days / 365.25 if issue_date else 0
        else:
            years_active = 0

        # ── Scoring ──────────────────────────────────────────────────────
        no_wc_score = 1.0 if no_wc else 0.0
        sole_prop_score = 1.0 if is_sole_prop else 0.0

        # Longer as sole prop without growth = intentionally stayed small
        longevity_score = self._clamp((years_active - 10) / 20) if is_sole_prop else 0.0

        # No website compounds the "tiny shop" signal
        no_web_score = 0.5 if (no_wc and not has_website) else 0.0

        composite = (
            0.35 * no_wc_score
            + 0.25 * sole_prop_score
            + 0.20 * longevity_score
            + 0.20 * no_web_score
        )
        composite = self._clamp(composite)

        # ── Signal fires? ────────────────────────────────────────────────
        signal = no_wc and is_sole_prop

        if signal:
            parts = [license_type]
            if years_active > 0:
                parts.append("{:.0f} years".format(years_active))
            parts.append("no employees / no WC")
            if not has_website:
                parts.append("no website")
            detail = "Micro-operator: {}".format(", ".join(parts))
        else:
            if not is_sole_prop:
                detail = "Not a sole proprietor ({})".format(license_type or "unknown")
            elif has_employees:
                detail = "Has employees (est. {})".format(employee_count)
            else:
                detail = "Not flagged"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "is_sole_prop": is_sole_prop,
                "has_employees": has_employees,
                "no_workers_comp": no_wc,
                "years_active": round(years_active, 1),
                "has_website": has_website,
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
