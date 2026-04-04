"""
layers/sba_loan.py — Strategy: SBA Loan Delinquency

During COVID, many small landscaping companies took PPP (Paycheck
Protection Program) and EIDL (Economic Injury Disaster Loan) money.
The SBA publishes this data publicly.

The acquisition thesis: a landscaping company that took PPP/EIDL but
never grew afterward is likely in one of two situations:
    1. Used the money to survive, not invest — still treading water
    2. Took the money and is now winding down — approaching retirement

A company with an SBA loan + sole proprietor + no growth signals is
a prime "soft landing" acquisition target.

Data source: SBA Open Data Portal (data.sba.gov) — completely free,
no account needed. PPP loan data is public by law.

Signals:
    - Took PPP/EIDL loan during COVID
    - Still operating as sole proprietor (didn't use the capital to grow)
    - Loan amount suggests very small operation ($10K-$50K range)
"""

from __future__ import annotations

import config
from layers.base import BaseLayer


class SBALoanLayer(BaseLayer):
    name = "sba_loan"
    label = "SBA Loan Flag"
    paid = False

    def run(self, company: dict) -> dict:
        """Check if company took SBA pandemic loans but didn't grow."""

        # SBA loan data would be cross-referenced by business name + zip
        # from the SBA PPP dataset. For now, we use CSLB data proxies.
        sba_loan_amount = company.get("sba_loan_amount")
        sba_loan_type = company.get("sba_loan_type")

        license_type = company.get("license_type", "")
        is_sole_prop = license_type in config.CSLB_ENTITY_TYPES_TARGET
        employee_count = company.get("employee_count_est")
        has_website = bool(company.get("website"))

        # If we have actual SBA data, use it directly
        if sba_loan_amount is not None:
            took_loan = True
            small_loan = sba_loan_amount < 50000
            still_small = is_sole_prop and not has_website
        else:
            # Proxy: sole prop that's been around since before COVID
            # but still hasn't grown = likely took survival money
            issue_date_raw = company.get("license_issue_date")
            if issue_date_raw:
                from datetime import date
                issue = _to_date(issue_date_raw)
                pre_covid = issue and issue.year <= 2019
            else:
                pre_covid = False

            took_loan = False  # can't confirm without SBA data
            small_loan = False
            still_small = is_sole_prop and pre_covid and not has_website

        # ── Scoring ──────────────────────────────────────────────────────
        if took_loan and small_loan and still_small:
            composite = 0.8
            signal = True
            detail = "SBA loan ${:,.0f} ({}) — still sole prop, no growth".format(
                sba_loan_amount, sba_loan_type or "PPP")
        elif took_loan and still_small:
            composite = 0.5
            signal = True
            detail = "SBA loan recipient — still operating as small sole prop"
        elif still_small and not took_loan:
            # Proxy signal: pre-COVID sole prop that never modernised
            composite = 0.3
            signal = True
            detail = "Pre-COVID sole prop, never grew — likely survival-mode operator"
        else:
            composite = 0.0
            signal = False
            if not is_sole_prop:
                detail = "Not a sole proprietor"
            else:
                detail = "No SBA loan indicators detected"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "took_sba_loan": took_loan,
                "sba_loan_amount": sba_loan_amount,
                "sba_loan_type": sba_loan_type,
                "is_sole_prop": is_sole_prop,
                "still_small": still_small,
                "has_website": has_website,
            },
            "paid": self.paid,
        }


def _to_date(val):
    from datetime import date
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val:
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None
