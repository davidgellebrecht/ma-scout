"""
layers/fleet_aging.py — Strategy 4: Fleet Aging Vision Engine

This layer uses Vision AI to analyse Street View imagery of a company's
business address.  You can literally "see" the health of a landscaping
company through their equipment — aging, mismatched, or unbranded trucks
signal a "mom and pop" shop that might prefer a cash buyout over spending
$100K on new equipment.

Why this matters:
    Landscaping companies with "Capex debt" (capital expenditure they've
    been deferring) are caught in a bind: they need new trucks and
    equipment to stay competitive, but can't afford it.  A cash acquisition
    offer solves their problem cleanly.

Analysis targets (from Street View):
    - Vehicle count and estimated age
    - Vehicle condition (new / good / fair / poor)
    - Branding quality (professional wraps vs plain / no branding)
    - Equipment visible and its condition
    - Overall professionalism impression (1–10 scale)

Requires:
    - GOOGLE_MAPS_API_KEY for Street View imagery (collector)
    - ANTHROPIC_API_KEY for Claude Vision analysis (this layer)
"""

from __future__ import annotations

import base64
import json
import os

import config
from layers.base import BaseLayer


class FleetAgingLayer(BaseLayer):
    name = "fleet_aging"
    label = "Fleet Aging"
    paid = True  # requires both Street View + Claude Vision API credits

    def run(self, company: dict) -> dict:
        """Analyse Street View imagery for fleet/equipment condition."""

        # Check for required credentials
        if not config.ANTHROPIC_API_KEY:
            return self._paid_stub()

        # Check for a Street View image
        image_path = company.get("_street_view_image")
        analysis = company.get("_street_view_analysis")

        # If we already have a cached analysis, use it
        if analysis:
            return self._score_analysis(analysis)

        # If we have an image but no analysis, run Vision AI
        if image_path and os.path.exists(image_path):
            analysis = self._analyse_image(image_path)
            if analysis:
                return self._score_analysis(analysis)

        return self._empty_result("No Street View imagery available")

    def _analyse_image(self, image_path: str) -> dict | None:
        """
        Send a Street View image to Claude Vision for fleet analysis.
        Returns a structured analysis dict, or None on failure.
        """
        try:
            import anthropic
        except ImportError:
            print("  ⚠  anthropic package not installed")
            return None

        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Analyze this Google Street View image of a landscaping "
                                "company's business address. Look for:\n"
                                "1. Trucks/vehicles: count, estimated age, condition "
                                "(new/good/fair/poor)\n"
                                "2. Branding: are vehicles branded with company name/logo, "
                                "or plain/unmarked?\n"
                                "3. Equipment visible: condition, type, storage quality\n"
                                "4. Overall impression: professional operation vs mom-and-pop\n\n"
                                "Return ONLY valid JSON with these exact keys:\n"
                                "{\n"
                                '  "vehicles_count": <int>,\n'
                                '  "avg_vehicle_age_est": <int years>,\n'
                                '  "vehicle_condition": "<new|good|fair|poor>",\n'
                                '  "branding_quality": "<professional|basic|none>",\n'
                                '  "equipment_visible": <bool>,\n'
                                '  "equipment_condition": "<good|fair|poor|none_visible>",\n'
                                '  "professionalism_score": <int 1-10>,\n'
                                '  "notes": "<brief observation>"\n'
                                "}"
                            ),
                        },
                    ],
                }],
            )

            # Parse the JSON response
            response_text = message.content[0].text
            # Extract JSON from possible markdown code block
            if "```" in response_text:
                json_str = response_text.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                json_str = json_str.strip()
            else:
                json_str = response_text.strip()

            return json.loads(json_str)

        except Exception as e:
            print(f"  ⚠  Vision analysis error: {e}")
            return None

    def _score_analysis(self, analysis: dict) -> dict:
        """Convert a vision analysis dict into a scored layer result."""

        prof_score = analysis.get("professionalism_score", 5)
        vehicle_condition = analysis.get("vehicle_condition", "fair")
        branding = analysis.get("branding_quality", "basic")
        vehicles = analysis.get("vehicles_count", 0)
        vehicle_age = analysis.get("avg_vehicle_age_est", 5)

        # ── Scoring ──────────────────────────────────────────────────────────
        # Professionalism: lower = better acquisition target
        # Scale: score 1 → 1.0, score 10 → 0.0
        prof_component = self._clamp(1.0 - (prof_score - 1) / 9)

        # Vehicle condition: poor → 1.0, new → 0.0
        condition_map = {"poor": 1.0, "fair": 0.6, "good": 0.3, "new": 0.0}
        condition_component = condition_map.get(vehicle_condition, 0.5)

        # Branding: none → 1.0, professional → 0.0
        branding_map = {"none": 1.0, "basic": 0.5, "professional": 0.0}
        branding_component = branding_map.get(branding, 0.5)

        # Vehicle age: older = more capex debt
        age_component = self._clamp((vehicle_age - 3) / 12)  # 3yr → 0.0, 15yr → 1.0

        composite = (
            0.30 * prof_component
            + 0.25 * condition_component
            + 0.25 * branding_component
            + 0.20 * age_component
        )
        composite = self._clamp(composite)

        # ── Signal fires? ────────────────────────────────────────────────────
        signal = (
            prof_score <= config.FLEET_PROFESSIONALISM_THRESHOLD
            or (vehicle_condition == "poor" and branding == "none")
        )

        if signal:
            detail = (
                f"Fleet aging detected: {vehicles} vehicle(s), "
                f"condition={vehicle_condition}, branding={branding}, "
                f"professionalism={prof_score}/10"
            )
        else:
            detail = (
                f"Fleet appears maintained: {vehicles} vehicle(s), "
                f"condition={vehicle_condition}, "
                f"professionalism={prof_score}/10"
            )

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": analysis,
            "paid": self.paid,
        }
