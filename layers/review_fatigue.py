"""
layers/review_fatigue.py — Strategy: Review Fatigue / Owner Burnout Score

Analyses review text (from any source — Nextdoor, Google, Yelp, manual
CSV import) for signs that the owner is burning out or winding down.

Key phrases that signal burnout:
    - "used to be great but lately..."
    - "stopped returning calls"
    - "quality has gone downhill"
    - "I think he's retiring"
    - "they don't show up anymore"

Without an LLM, we use keyword matching on review text.
With an LLM (ANTHROPIC_API_KEY), we run a proper sentiment analysis.

The acquisition thesis: if multiple customers independently mention
declining quality, the owner is burned out.  Approach them with
empathy: "I know how hard it is to find good labor — what if we
merged operations so you can step back?"

Data source: Review text from any platform (manual CSV import)
LLM enhancement: Claude analyses reviews for burnout signals
"""

from __future__ import annotations

import config
from layers.base import BaseLayer

# Keywords that suggest owner burnout in reviews
BURNOUT_KEYWORDS = [
    "used to be great", "used to be good", "used to be reliable",
    "lately", "recently", "not the same", "gone downhill",
    "doesn't return calls", "doesn't answer", "hard to reach",
    "stopped showing up", "no-show", "no show", "didn't show",
    "unreliable now", "not reliable anymore",
    "retiring", "retirement", "winding down", "closing",
    "I think he", "I think she", "getting older",
    "dropped the ball", "forgot", "missed",
    "used them for years but", "been using them for",
    "looking for a new", "need a replacement",
    "overwhelmed", "too busy", "overbooked",
]


class ReviewFatigueLayer(BaseLayer):
    name = "review_fatigue"
    label = "Owner Fatigue"
    paid = False

    def run(self, company: dict) -> dict:
        """Score a company for signs of owner burnout from review text."""

        # Review text can come from:
        # 1. company["_review_texts"] — list of review strings
        # 2. company["source"] == "google_distress" — pre-flagged
        review_texts = company.get("_review_texts", [])
        source = company.get("source", "")

        if review_texts:
            # Keyword scan
            burnout_hits = 0
            total_reviews = len(review_texts)
            matched_keywords = []

            for text in review_texts:
                text_lower = text.lower()
                for keyword in BURNOUT_KEYWORDS:
                    if keyword in text_lower:
                        burnout_hits += 1
                        matched_keywords.append(keyword)
                        break  # one match per review is enough

            if total_reviews > 0:
                fatigue_ratio = burnout_hits / total_reviews
            else:
                fatigue_ratio = 0

            if fatigue_ratio >= 0.3:
                signal = True
                composite = self._clamp(fatigue_ratio)
                detail = "Owner fatigue: {}/{} reviews mention burnout ({})".format(
                    burnout_hits, total_reviews,
                    ", ".join(set(matched_keywords[:3])))
            else:
                signal = False
                composite = fatigue_ratio
                detail = "Low fatigue signal ({}/{} reviews)".format(
                    burnout_hits, total_reviews)
        elif source == "google_distress":
            # Pre-flagged by the distress collector
            signal = True
            composite = 0.5
            detail = "Flagged via Digital Distress (likely burnout reviews)"
        else:
            signal = False
            composite = 0.0
            detail = "No review text available for fatigue analysis"

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "review_count": len(review_texts),
                "burnout_hits": burnout_hits if review_texts else 0,
                "source": source,
            },
            "paid": self.paid,
        }
