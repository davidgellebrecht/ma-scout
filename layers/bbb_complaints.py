"""
layers/bbb_complaints.py — Strategy: BBB Complaint Tracker

The Better Business Bureau (BBB) maintains public profiles for
businesses, including complaint history and response patterns.
BBB profiles are freely accessible at bbb.org.

The acquisition thesis: a landscaping company with BBB complaints
that the owner never responded to is a sign of disengagement. The
owner has stopped caring about their reputation — they're mentally
checked out and may welcome a buyer.

Conversely, a company with NO BBB profile at all after 20+ years
suggests a very small, informal operation.

Data source: bbb.org public profiles (free, no account)

Signals:
    - BBB complaints with no owner response
    - Low BBB rating (C or below) after years of operation
    - No BBB profile despite being in business 15+ years
    - Recent spike in complaints (service declining)
"""

from __future__ import annotations

import config
from layers.base import BaseLayer


class BBBComplaintsLayer(BaseLayer):
    name = "bbb_complaints"
    label = "BBB Complaints"
    paid = False

    def run(self, company: dict) -> dict:
        """Check BBB profile for complaint patterns."""

        # BBB data would come from scraping bbb.org public profiles
        bbb_rating = company.get("bbb_rating")  # "A+", "A", "B", etc.
        bbb_complaints = company.get("bbb_complaint_count", 0)
        bbb_responded = company.get("bbb_complaints_responded", 0)
        has_bbb_profile = company.get("has_bbb_profile")

        license_type = company.get("license_type", "")
        is_sole_prop = license_type in config.CSLB_ENTITY_TYPES_TARGET

        # License age for context
        issue_date_raw = company.get("license_issue_date")
        years_active = 0
        if issue_date_raw:
            from datetime import date
            issue = _to_date(issue_date_raw)
            if issue:
                years_active = (date.today() - issue).days / 365.25

        if has_bbb_profile is not None:
            # We have BBB data
            if bbb_complaints > 0 and bbb_responded == 0:
                signal = True
                composite = 0.7
                detail = "BBB: {} complaint(s), ZERO responses — owner disengaged".format(
                    bbb_complaints)
            elif bbb_rating and bbb_rating.upper() in ("C", "C-", "D", "D-", "F"):
                signal = True
                composite = 0.5
                detail = "BBB rating: {} — reputation declining".format(bbb_rating)
            elif bbb_complaints > 3:
                signal = True
                composite = 0.4
                detail = "BBB: {} complaints (responded to {})".format(
                    bbb_complaints, bbb_responded)
            else:
                signal = False
                composite = 0.0
                detail = "BBB profile in good standing"
        elif is_sole_prop and years_active >= 15:
            # No BBB profile after 15+ years = very informal operation
            signal = True
            composite = 0.3
            detail = "No BBB profile after {:.0f} years — very informal operation".format(
                years_active)
        else:
            signal = False
            composite = 0.0
            detail = "BBB data not available"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "has_bbb_profile": has_bbb_profile,
                "bbb_rating": bbb_rating,
                "bbb_complaints": bbb_complaints,
                "bbb_responded": bbb_responded,
                "years_active": round(years_active, 1),
                "is_sole_prop": is_sole_prop,
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
