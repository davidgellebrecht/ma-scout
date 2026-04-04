"""
layers/property_change.py — Strategy: Property Change / Grant Deed Monitor

When a commercial property changes hands (new owner via Grant Deed),
the new owner typically fires the old landscaping/cleaning crew within
90 days and brings in their own vendor.  This creates two opportunities:

    1. The FIRED vendor is now losing revenue — open to acquisition
    2. The NEW OWNER needs a vendor — send a portering pitch

Data sources:
    - County Recorder Grant Deed filings (public record)
    - Commercial real estate feeds (RSS/API)
    - Property management company vendor lists

For now: this layer flags companies operating in areas with high
commercial property turnover.  In production, it would cross-reference
actual Grant Deed filings with contractor vendor lists.

Signals:
    - Company operates in a high-turnover commercial zone
    - Company's primary clients are commercial properties
    - Recent property sales in the company's service area
"""

from __future__ import annotations

import config
from layers.base import BaseLayer


class PropertyChangeLayer(BaseLayer):
    name = "property_change"
    label = "Property Turnover"
    paid = False

    def run(self, company: dict) -> dict:
        """Flag companies in high-turnover commercial property areas."""

        city = company.get("city", "")
        zip_code = company.get("zip_code", "")
        source = company.get("source", "")
        license_type = company.get("license_type", "")

        # High-value commercial areas where property changes create
        # vendor displacement opportunities
        market = config.get_market()
        wealthy_zips = market.get("wealthy_zips", [])

        # Commercial hubs in each county
        commercial_hubs = {
            "Orange": ["Irvine", "Newport Beach", "Costa Mesa",
                       "Anaheim", "Huntington Beach"],
            "Los Angeles": ["Beverly Hills", "Santa Monica", "Glendale",
                           "Pasadena", "Torrance", "Long Beach"],
            "San Diego": ["La Jolla", "Del Mar", "Carlsbad",
                          "Encinitas", "Coronado"],
        }

        county = config.get_county()
        hubs = commercial_hubs.get(county, [])
        in_commercial_hub = city in hubs
        in_wealthy_zip = zip_code in wealthy_zips

        # Property change data would come from Grant Deed RSS feeds
        # or county recorder searches. For now, use location proxy.
        recent_property_changes = company.get("nearby_property_changes", 0)

        if recent_property_changes > 0:
            signal = True
            composite = self._clamp(recent_property_changes / 5)
            detail = "{} recent property sales nearby — vendor displacement likely".format(
                recent_property_changes)
        elif in_commercial_hub and in_wealthy_zip:
            signal = True
            composite = 0.4
            detail = "High-turnover commercial zone: {}, {}".format(city, zip_code)
        elif in_commercial_hub:
            signal = True
            composite = 0.2
            detail = "Commercial hub area: {} — monitor for property changes".format(city)
        else:
            signal = False
            composite = 0.0
            detail = "Not in a high-turnover commercial zone"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "city": city,
                "in_commercial_hub": in_commercial_hub,
                "in_wealthy_zip": in_wealthy_zip,
                "nearby_property_changes": recent_property_changes,
            },
            "paid": self.paid,
        }
