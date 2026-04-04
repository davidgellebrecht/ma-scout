"""
layers/bond_amount.py — Strategy: Contractor Bond Amount

California requires all licensed contractors to carry a contractor's
license bond.  The minimum is $25,000.  The CSLB master list includes
bond amounts.

The acquisition thesis: a contractor who has maintained the minimum
$25K bond for decades has intentionally stayed small.  Larger
contractors increase their bond as they take on bigger projects.
A minimum-bond shop that's been around for 25 years is a classic
"lifestyle business" — the owner makes a comfortable living but
has no growth ambition and no succession plan.

Data source: CSLB license data (public record, already in DB)

Signals:
    - Minimum bond amount ($25K) maintained for 15+ years
    - Sole proprietor with minimum bond = intentionally stayed micro
    - Bond + no workers comp + no website = complete lifestyle operator
"""

from __future__ import annotations

from datetime import date

import config
from layers.base import BaseLayer


class BondAmountLayer(BaseLayer):
    name = "bond_amount"
    label = "Min Bond"
    paid = False

    def run(self, company: dict) -> dict:
        """Analyse contractor bond amount for lifestyle-business signals."""

        license_type = company.get("license_type", "")
        is_sole_prop = license_type in config.CSLB_ENTITY_TYPES_TARGET
        has_website = bool(company.get("website"))
        employee_count = company.get("employee_count_est")

        # Bond amount from CSLB data
        bond_amount = company.get("bond_amount")

        # License age
        issue_date_raw = company.get("license_issue_date")
        years_active = 0
        if issue_date_raw:
            issue = _to_date(issue_date_raw)
            if issue:
                years_active = (date.today() - issue).days / 365.25

        if bond_amount is not None:
            # Direct bond data available
            is_minimum = bond_amount <= 25000
            long_running = years_active >= 15

            if is_minimum and long_running and is_sole_prop:
                signal = True
                composite = 0.7
                parts = ["${:,.0f} bond".format(bond_amount),
                         "{:.0f} years".format(years_active), license_type]
                if not has_website:
                    parts.append("no website")
                    composite = 0.8
                detail = "Lifestyle operator: {}".format(", ".join(parts))
            elif is_minimum and long_running:
                signal = True
                composite = 0.4
                detail = "Minimum bond for {:.0f} years — never scaled up".format(years_active)
            else:
                signal = False
                composite = 0.0
                detail = "Bond ${:,.0f} — appears to have scaled".format(bond_amount)
        elif is_sole_prop and years_active >= 20:
            # No bond data but strong sole prop indicators
            # Most long-running sole props carry minimum bond
            signal = True
            composite = 0.4
            detail = "Likely minimum bond — sole prop for {:.0f} years, never incorporated".format(
                years_active)
        else:
            signal = False
            composite = 0.0
            detail = "Bond data not available"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "bond_amount": bond_amount,
                "is_minimum_bond": bond_amount is not None and bond_amount <= 25000,
                "years_active": round(years_active, 1),
                "is_sole_prop": is_sole_prop,
                "has_website": has_website,
            },
            "paid": self.paid,
        }


def _to_date(val):
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val:
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None
