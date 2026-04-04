"""
layers/nextdoor_referral.py — Strategy: Nextdoor Referral Reverse-Search

Analyses companies identified through Nextdoor recommendation threads.
The key insight: a sole proprietor mentioned 20+ times in wealthy zip
codes but with no website owns a Route — recurring client relationships
that are the most valuable asset in the landscaping business.

"Manuel" or "Dave" might not have a corporation, a website, or even a
truck with their name on it — but they have 50 loyal clients in Newport
Beach who pay them $200/week.  That's a $500K/year route worth acquiring.

Signals:
    - Referenced multiple times in Nextdoor recommendations
    - Operates in wealthy zip codes (high-value routes)
    - No website or formal business presence
    - Not found in CSLB records (informal operator)

Score components:
    - mention_frequency_score:  how often referenced (3+ mentions → signal)
    - wealthy_area_score:       operating in high-value neighborhoods
    - informality_score:        no website, no CSLB license = informal route
    - route_value_score:        estimated route value based on area + frequency
"""

from __future__ import annotations

import config
from layers.base import BaseLayer


class NextdoorReferralLayer(BaseLayer):
    name = "nextdoor_referral"
    label = "Nextdoor Referral"
    paid = False

    def run(self, company: dict) -> dict:
        """Analyse a Nextdoor-sourced company for route acquisition signals."""

        source = company.get("source", "")
        has_website = bool(company.get("website"))
        has_license = bool(company.get("license_number"))
        zip_code = company.get("zip_code", "")
        city = company.get("city", "")

        # Mention count — in production, this comes from counting Nextdoor
        # thread appearances.  For demo, Nextdoor-sourced companies get
        # a default count; non-Nextdoor companies get 0.
        mention_count = company.get("nextdoor_mentions", 0)
        if source == "nextdoor" and mention_count == 0:
            mention_count = 8  # default demo: mentioned ~8 times

        has_mentions = mention_count >= config.NEXTDOOR_MIN_MENTIONS

        # ── Sub-signals ──────────────────────────────────────────────────────

        # Mention frequency: 3 → 0.0, 20+ → 1.0
        mention_score = self._clamp((mention_count - 3) / 17) if has_mentions else 0.0

        # Wealthy area: operating in high-value zip codes
        wealthy_zips = config.get_wealthy_zips()
        in_wealthy_area = zip_code in wealthy_zips
        wealthy_area_score = 1.0 if in_wealthy_area else 0.3

        # Informality: no website + no CSLB license = informal route owner
        is_informal = not has_website and not has_license
        informality_score = 1.0 if is_informal else (0.5 if not has_website else 0.0)

        # Route value estimate based on area and mentions
        # Wealthy area + frequent mentions = high-value route
        route_value_score = (mention_score * 0.6 + wealthy_area_score * 0.4)

        # ── Composite ────────────────────────────────────────────────────────
        composite = (
            0.30 * mention_score
            + 0.25 * wealthy_area_score
            + 0.25 * informality_score
            + 0.20 * route_value_score
        )
        composite = self._clamp(composite)

        # ── Signal fires? ────────────────────────────────────────────────────
        signal = has_mentions and not has_website

        # ── Detail ───────────────────────────────────────────────────────────
        if signal:
            parts = ["{} Nextdoor mentions".format(mention_count)]
            if in_wealthy_area:
                parts.append("wealthy area ({})".format(zip_code))
            if is_informal:
                parts.append("no website or license")
            detail = "Route acquisition target: {}".format(", ".join(parts))
        else:
            parts = []
            if not has_mentions:
                parts.append("too few mentions ({})".format(mention_count))
            if has_website:
                parts.append("has formal web presence")
            detail = "Not flagged: {}".format(
                ", ".join(parts) or "not from Nextdoor source")

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "mention_count": mention_count,
                "has_website": has_website,
                "has_license": has_license,
                "in_wealthy_area": in_wealthy_area,
                "zip_code": zip_code,
                "city": city,
                "source": source,
                "mention_score": round(mention_score, 3),
                "wealthy_area_score": round(wealthy_area_score, 3),
                "informality_score": round(informality_score, 3),
                "route_value_score": round(route_value_score, 3),
            },
            "paid": self.paid,
        }
