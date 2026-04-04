"""
collectors/street_view.py — Google Street View Image Collector

Captures Street View imagery at each company's registered business
address.  These images are later analysed by the Fleet Aging layer
(Strategy 4) using Vision AI to assess equipment condition, branding
quality, and overall professionalism.

Think of Street View as a "drive-by" — Google's camera cars have already
photographed most business addresses in OC, so we can "look at" the
business without physically visiting.

Data flow:
    Company addresses → Street View API → JPG images → data/street_view/

Cost: $7 per 1,000 images on the standard Google Maps plan.
"""

import os
from pathlib import Path

import requests

import config


STREET_VIEW_DIR = os.path.join(os.path.dirname(config.DB_PATH), "street_view")


def collect_street_view(conn) -> int:
    """
    Capture Street View images for companies that don't have one yet.

    Returns the number of images captured.
    """
    from db import get_companies, insert_street_view_image

    if not config.GOOGLE_MAPS_API_KEY:
        print("  ⚠  GOOGLE_MAPS_API_KEY not set — skipping Street View capture")
        return 0

    os.makedirs(STREET_VIEW_DIR, exist_ok=True)

    companies = get_companies(conn)
    count = 0

    for company in companies:
        address = company.address
        if not address:
            continue

        image_path = os.path.join(STREET_VIEW_DIR, f"{company.id}.jpg")

        # Skip if we already have an image
        if os.path.exists(image_path):
            continue

        success = _capture_image(address, image_path)
        if success:
            insert_street_view_image(conn, company.id, image_path)
            count += 1
            print(f"    Captured: {company.business_name}")

    return count


def _capture_image(address: str, save_path: str) -> bool:
    """
    Download a Street View image for a given address.
    Returns True if successful, False otherwise.
    """
    url = "https://maps.googleapis.com/maps/api/streetview"
    params = {
        "size": config.STREET_VIEW_IMAGE_SIZE,
        "location": address,
        "key": config.GOOGLE_MAPS_API_KEY,
        "source": "outdoor",  # prefer outdoor imagery (trucks in driveways)
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()

        # Check if Google returned an actual image (not a "no imagery" placeholder)
        content_type = resp.headers.get("Content-Type", "")
        if "image" not in content_type:
            return False

        with open(save_path, "wb") as f:
            f.write(resp.content)
        return True

    except Exception as e:
        print(f"  ⚠  Street View error for {address}: {e}")
        return False
