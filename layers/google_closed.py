"""
layers/google_closed.py — Strategy: Google "Permanently Closed" Check

Google Maps sometimes marks businesses as "Permanently closed" or
"Temporarily closed" based on user reports.  But the business might
still hold an active CSLB license.

The acquisition thesis: a company marked "closed" on Google but with
an active contractor license is in limbo.  The owner probably stopped
their storefront/office but still does jobs through word-of-mouth.
They're sitting on active license + client relationships (a Route)
but have effectively "retired in place."  A cash offer to buy their
license and remaining client list is extremely attractive to them.

Data source: Google Maps public data (no API key needed for status)
Cross-reference: Active CSLB license

Signals:
    - Google Maps shows "Permanently closed" or "Temporarily closed"
    - CSLB license is still Active
    - Combined with no website = retired-in-place operator
"""

from __future__ import annotations

import config
from layers.base import BaseLayer


class GoogleClosedLayer(BaseLayer):
    name = "google_closed"
    label = "Google Closed"
    paid = False

    def run(self, company: dict) -> dict:
        """Check if a company is marked closed on Google but still licensed."""

        # Google closed status would come from Google Maps scraping
        google_status = company.get("google_business_status")
        license_status = company.get("license_status", "")
        license_type = company.get("license_type", "")
        has_website = bool(company.get("website"))
        is_sole_prop = license_type in config.CSLB_ENTITY_TYPES_TARGET

        has_active_license = (license_status or "").lower() in ("active", "")

        if google_status:
            is_closed = google_status.lower() in (
                "permanently closed", "closed_permanently",
                "temporarily closed", "closed_temporarily",
            )

            if is_closed and has_active_license:
                signal = True
                composite = 0.9
                parts = ["Google: \"{}\"".format(google_status),
                         "CSLB license still Active"]
                if not has_website:
                    parts.append("no website")
                if is_sole_prop:
                    parts.append(license_type)
                detail = "Retired-in-place: {}".format(", ".join(parts))
            elif is_closed:
                signal = True
                composite = 0.6
                detail = "Google closed, license status: {}".format(license_status)
            else:
                signal = False
                composite = 0.0
                detail = "Google status: {} — business appears operational".format(google_status)
        else:
            # No Google status data — use proxy signals
            # A sole prop with active license but no website and no Google
            # presence at all is likely operating informally
            if is_sole_prop and not has_website and has_active_license:
                # Check if there's any Google data at all
                has_google = bool(company.get("google_place_id") or
                                  company.get("google_rating"))
                if not has_google:
                    signal = True
                    composite = 0.3
                    detail = "No Google presence at all — operating entirely by word-of-mouth"
                else:
                    signal = False
                    composite = 0.0
                    detail = "Has Google presence, not marked closed"
            else:
                signal = False
                composite = 0.0
                detail = "Google status not available"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "google_status": google_status,
                "license_status": license_status,
                "has_active_license": has_active_license,
                "is_sole_prop": is_sole_prop,
                "has_website": has_website,
            },
            "paid": self.paid,
        }
