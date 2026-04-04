"""
layers/digital_distress.py — Strategy: Digital Distress via Google Maps

Identifies landscaping businesses showing active signs of operational
distress: low Google ratings (3.5 or below), unclaimed profiles, and
reviews that specifically mention declining service quality.

This is different from the "Digital Ghost" layer:
    - Digital Ghost = good reputation, owner stopped engaging (coasting)
    - Digital Distress = reputation is actively declining (struggling)

Why distressed businesses are acquisition targets:
    The owners are often stressed and overwhelmed.  They might jump at an
    offer that "takes the headache away" while keeping their crew employed.
    The outreach angle is "Problem-Solver" rather than "Retirement."

Signals:
    - Google rating at or below 3.5 stars
    - Profile not claimed by the owner
    - Recent reviews mention declining quality or no-shows
    - Still has enough review volume to suggest an established business

Score components:
    - rating_distress_score:  how far below 3.5 the rating is
    - review_keyword_score:   presence of burnout keywords in reviews
    - unclaimed_score:        1.0 if profile is unclaimed
    - volume_score:           enough reviews to be an established business
"""

from __future__ import annotations

from datetime import date

import config
from layers.base import BaseLayer


class DigitalDistressLayer(BaseLayer):
    name = "digital_distress"
    label = "Digital Distress"
    paid = False

    def run(self, company: dict) -> dict:
        """Analyse a company for signs of operational distress."""

        google_rating = company.get("google_rating")
        google_count = company.get("google_review_count", 0) or 0
        yelp_rating = company.get("yelp_rating")
        yelp_count = company.get("yelp_review_count", 0) or 0

        best_rating = google_rating or yelp_rating
        total_reviews = google_count + yelp_count

        if best_rating is None:
            return self._empty_result("No rating data available")

        # ── Sub-signal 1: Rating distress ────────────────────────────────────
        # Lower rating = more distressed.  Scale: 3.5 → 0.0, 1.0 → 1.0
        is_low_rated = best_rating <= config.DISTRESS_MAX_RATING
        if is_low_rated:
            rating_distress_score = self._clamp(
                (config.DISTRESS_MAX_RATING - best_rating) / 2.5
            )
        else:
            rating_distress_score = 0.0

        # ── Sub-signal 2: Review volume ──────────────────────────────────────
        # Need enough reviews to indicate an established business (not just
        # a startup with one bad review).  5+ reviews = established.
        has_volume = total_reviews >= 5
        volume_score = self._clamp(total_reviews / 15) if has_volume else 0.0

        # ── Sub-signal 3: Distress keywords in reviews ───────────────────────
        # In production, we'd check actual review text.  For demo, we use
        # the source field as a proxy — companies from google_distress
        # collector were pre-filtered for these signals.
        source = company.get("source", "")
        has_distress_keywords = source == "google_distress"
        keyword_score = 0.8 if has_distress_keywords else 0.0

        # ── Sub-signal 4: Unclaimed profile ──────────────────────────────────
        # An unclaimed Google profile means the owner hasn't bothered to
        # verify their business — a strong signal of disengagement.
        # We approximate this: no website + low rating = likely unclaimed
        has_website = bool(company.get("website"))
        likely_unclaimed = not has_website and is_low_rated
        unclaimed_score = 1.0 if likely_unclaimed else 0.0

        # ── Composite ────────────────────────────────────────────────────────
        composite = (
            0.35 * rating_distress_score
            + 0.25 * keyword_score
            + 0.20 * unclaimed_score
            + 0.20 * volume_score
        )
        composite = self._clamp(composite)

        # ── Signal fires? ────────────────────────────────────────────────────
        signal = is_low_rated and has_volume

        # ── Detail ───────────────────────────────────────────────────────────
        if signal:
            parts = ["{:.1f}★ rating".format(best_rating)]
            parts.append("{} reviews".format(total_reviews))
            if likely_unclaimed:
                parts.append("likely unclaimed")
            if has_distress_keywords:
                parts.append("distress keywords detected")
            detail = "Digital distress: {}".format(", ".join(parts))
        else:
            if not is_low_rated:
                detail = "Rating above threshold ({:.1f}★ > {:.1f}★)".format(
                    best_rating, config.DISTRESS_MAX_RATING)
            elif not has_volume:
                detail = "Too few reviews ({}) to assess".format(total_reviews)
            else:
                detail = "Not flagged"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "best_rating": best_rating,
                "total_reviews": total_reviews,
                "is_low_rated": is_low_rated,
                "has_volume": has_volume,
                "has_distress_keywords": has_distress_keywords,
                "likely_unclaimed": likely_unclaimed,
                "rating_distress_score": round(rating_distress_score, 3),
                "keyword_score": round(keyword_score, 3),
                "unclaimed_score": round(unclaimed_score, 3),
                "volume_score": round(volume_score, 3),
            },
            "paid": self.paid,
        }
