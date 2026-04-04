"""
layers/sos_status.py — Strategy: Secretary of State Entity Status

The California Secretary of State tracks the status of every
Corporation and LLC. Companies can be:
    - Active
    - Suspended (usually for not filing annual reports)
    - FTB Suspended (Franchise Tax Board — didn't pay taxes)
    - Dissolved / Cancelled

Note: Sole proprietors and general partnerships are NOT registered
with the Secretary of State — they only file with the County Clerk.

The acquisition thesis: a company with a "Suspended" status at the
SoS but an active CSLB license is in corporate limbo. They're still
doing the work but their business entity is falling apart. This is a
company whose owner has mentally checked out of the admin side.

Data source: bizfileonline.sos.ca.gov (free search, no account)

Signals:
    - Entity status is Suspended or FTB Suspended
    - Active CSLB license but dormant corporate filings
    - Never registered with SoS (sole prop that never incorporated)
"""

from __future__ import annotations

import config
from layers.base import BaseLayer


class SOSStatusLayer(BaseLayer):
    name = "sos_status"
    label = "Entity Status"
    paid = False

    def run(self, company: dict) -> dict:
        """Check company's Secretary of State entity status."""

        license_type = company.get("license_type", "")
        license_status = company.get("license_status", "")
        is_sole_prop = license_type in config.CSLB_ENTITY_TYPES_TARGET

        # SoS status would come from bizfileonline.sos.ca.gov search
        sos_status = company.get("sos_entity_status")

        # Corporations/LLCs should be registered with SoS
        is_corporate = license_type in ("Corporation", "LLC", "Partnership")

        if sos_status:
            # Direct SoS data available
            is_suspended = sos_status.lower() in ("suspended", "ftb suspended",
                                                    "ftb/sos suspended")
            is_dissolved = sos_status.lower() in ("dissolved", "cancelled",
                                                   "surrendered")

            if is_suspended:
                signal = True
                composite = 0.8
                detail = "SoS status: {} — corporate entity in trouble".format(sos_status)
            elif is_dissolved:
                signal = True
                composite = 0.6
                detail = "SoS status: {} — entity wound down but may still operate".format(sos_status)
            else:
                signal = False
                composite = 0.0
                detail = "SoS status: {} — entity in good standing".format(sos_status)
        elif is_sole_prop:
            # Sole props aren't on SoS — this IS the signal
            # They never incorporated = never planned for growth/succession
            has_long_history = False
            issue_date_raw = company.get("license_issue_date")
            if issue_date_raw:
                from datetime import date
                issue = _to_date(issue_date_raw)
                if issue:
                    years = (date.today() - issue).days / 365.25
                    has_long_history = years >= 15

            if has_long_history:
                signal = True
                composite = 0.5
                detail = "Never incorporated — sole prop for {:.0f} years with no SoS entity".format(years)
            else:
                signal = False
                composite = 0.0
                detail = "Sole proprietor (not registered with Secretary of State)"
        elif is_corporate:
            # Corporate entity but we don't have SoS data yet
            signal = False
            composite = 0.0
            detail = "{} — SoS status not yet checked".format(license_type)
        else:
            signal = False
            composite = 0.0
            detail = "Entity type unknown"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "license_type": license_type,
                "is_sole_prop": is_sole_prop,
                "is_corporate": is_corporate,
                "sos_status": sos_status,
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
