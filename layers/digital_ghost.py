"""
layers/digital_ghost.py — Strategy 2: Digital Ghost Sentiment Analysis

This layer detects "Digital Ghosts" — landscaping companies that have a
good reputation (high ratings, decent review count) but whose owner has
stopped actively managing their online presence.

Why this matters for acquisitions:
    A 4.5-star company with no reviews in 2+ years suggests an owner who
    is "coasting" — they still have clients and crew, but they've stopped
    trying to grow.  These businesses are prime for a roll-up because the
    hard part (building a reputation and client base) is already done.

Signals:
    - Last review is 2+ years old (Google or Yelp)
    - Owner stopped responding to reviews
    - High rating (>= 3.5) despite inactivity = "golden ghost"

Score components:
    - review_gap_score:    days since last review scaled (730–1825 → 0.0–1.0)
    - rating_score:        higher rating = more attractive target (3.5–5.0 → 0.0–1.0)
    - response_decay:      owner response rate drop-off (1.0 if fully stopped)
"""

from __future__ import annotations

from datetime import date

import config
from layers.base import BaseLayer


class DigitalGhostLayer(BaseLayer):
    name = "digital_ghost"
    label = "Digital Ghost"
    paid = False  # Google/Yelp data collected via respective collectors

    def run(self, company: dict) -> dict:
        """Analyse a company's digital presence for ghost signals."""

        # ── Gather review data ───────────────────────────────────────────────
        google_rating = company.get("google_rating")
        google_count = company.get("google_review_count", 0) or 0
        google_last = _to_date(company.get("google_last_review_date"))

        yelp_rating = company.get("yelp_rating")
        yelp_count = company.get("yelp_review_count", 0) or 0
        yelp_last = _to_date(company.get("yelp_last_review_date"))

        # Best available rating (prefer Google if both exist)
        best_rating = google_rating or yelp_rating
        total_reviews = google_count + yelp_count

        # Need some review history to analyse
        if not best_rating or total_reviews < config.MIN_REVIEWS_FOR_GHOST:
            return self._empty_result(
                f"Insufficient review data ({total_reviews} reviews)"
            )

        today = date.today()

        # ── Sub-signal 1: Review gap (staleness) ─────────────────────────────
        # How many days since the most recent review on any platform?
        last_review_dates = [d for d in [google_last, yelp_last] if d]
        if last_review_dates:
            most_recent = max(last_review_dates)
            days_since = (today - most_recent).days
        else:
            # No review dates available — assume moderately stale
            days_since = config.REVIEW_STALE_DAYS
            most_recent = None

        review_stale = days_since >= config.REVIEW_STALE_DAYS
        # Scale: 730 days (2yr) → 0.0, 1825 days (5yr) → 1.0
        review_gap_score = self._clamp((days_since - 730) / 1095) if review_stale else 0.0

        # ── Sub-signal 2: Rating quality ─────────────────────────────────────
        # Higher rating = more attractive ghost (they built something good)
        meets_min_rating = best_rating >= config.MIN_RATING_FOR_GHOST
        # Scale: 3.5 → 0.0, 5.0 → 1.0
        rating_score = self._clamp((best_rating - 3.5) / 1.5) if meets_min_rating else 0.0

        # ── Sub-signal 3: Owner response decay ──────────────────────────────
        owner_response_rate = company.get("owner_response_rate")
        if owner_response_rate is not None:
            # Lower response rate = more ghostly
            response_decay_score = self._clamp(1.0 - owner_response_rate)
        else:
            # Unknown — use a neutral value
            response_decay_score = 0.5 if review_stale else 0.0

        # ── Composite score ──────────────────────────────────────────────────
        weights = {
            "review_gap": 0.45,
            "rating": 0.30,
            "response_decay": 0.25,
        }
        composite = (
            weights["review_gap"]      * review_gap_score
            + weights["rating"]        * rating_score
            + weights["response_decay"] * response_decay_score
        )
        composite = self._clamp(composite)

        # ── Signal fires? ────────────────────────────────────────────────────
        # Ghost = stale reviews AND decent rating
        signal = review_stale and meets_min_rating

        # ── Build detail string ──────────────────────────────────────────────
        if signal:
            detail = (
                f"Digital Ghost: {best_rating:.1f}★ rating, "
                f"last review {days_since} days ago "
                f"({total_reviews} total reviews)"
            )
        else:
            parts = []
            if not review_stale:
                parts.append(f"reviews still active ({days_since}d ago)")
            if not meets_min_rating:
                parts.append(f"rating below threshold ({best_rating:.1f}★)")
            detail = f"Not a ghost: {', '.join(parts)}"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "best_rating": best_rating,
                "total_reviews": total_reviews,
                "days_since_last_review": days_since,
                "last_review_date": str(most_recent) if most_recent else None,
                "review_stale": review_stale,
                "meets_min_rating": meets_min_rating,
                "owner_response_rate": owner_response_rate,
                "review_gap_score": round(review_gap_score, 3),
                "rating_score": round(rating_score, 3),
                "response_decay_score": round(response_decay_score, 3),
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
