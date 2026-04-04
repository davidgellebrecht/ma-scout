# ─── M&A Scout — Configuration ───────────────────────────────────────────────
# Toggle each layer True (active) or False (skip).
# API credentials can be set here or overridden via .streamlit/secrets.toml.

# ─── Markets ─────────────────────────────────────────────────────────────────
# Each market is a California county with its own cities, bounding box, and
# county clerk URL for FBN (Fictitious Business Name) lookups.
#
# The active market is set by ACTIVE_MARKET below, or selected in the UI dropdown.

MARKETS = {
    "Orange County": {
        "label": "Orange County, CA",
        "county": "Orange",
        "bbox": (33.38, -118.12, 33.95, -117.41),
        "fbn_clerk_url": "https://cr.ocgov.com/recorderworks/",
        "cities": [
            "Irvine", "Newport Beach", "Laguna Beach", "Huntington Beach",
            "Mission Viejo", "San Clemente", "Dana Point", "Laguna Niguel",
            "Costa Mesa", "Anaheim", "Fullerton", "Orange", "Tustin",
            "Lake Forest", "Rancho Santa Margarita", "Garden Grove",
        ],
        "wealthy_zips": [
            "92657", "92660", "92661", "92662", "92651", "92625",  # Newport / Laguna
            "92603", "92604",  # Irvine (Shady Canyon, Turtle Rock)
            "92629",  # Dana Point
        ],
    },
    "Los Angeles County": {
        "label": "Los Angeles County, CA",
        "county": "Los Angeles",
        "bbox": (33.70, -118.67, 34.34, -117.65),
        "fbn_clerk_url": "https://www.lavote.gov/home/county-clerk/fictitious-business-names",
        "cities": [
            "Beverly Hills", "Santa Monica", "Pasadena", "Glendale",
            "Burbank", "Calabasas", "Malibu", "Manhattan Beach",
            "Redondo Beach", "Torrance", "Long Beach", "Whittier",
            "West Hollywood", "La Canada Flintridge", "San Marino",
            "Arcadia", "Palos Verdes Estates", "Rolling Hills",
        ],
        "wealthy_zips": [
            "90210", "90212",  # Beverly Hills
            "90049", "90077",  # Bel Air / Brentwood
            "90272",  # Pacific Palisades
            "90265",  # Malibu
            "91011",  # La Canada Flintridge
            "90274",  # Palos Verdes
            "91108",  # San Marino
        ],
    },
    "San Diego County": {
        "label": "San Diego County, CA",
        "county": "San Diego",
        "bbox": (32.53, -117.60, 33.51, -116.08),
        "fbn_clerk_url": "https://arcc.sdcounty.ca.gov/Pages/FBN-702.aspx",
        "cities": [
            "La Jolla", "Del Mar", "Rancho Santa Fe", "Encinitas",
            "Carlsbad", "Solana Beach", "Coronado", "Point Loma",
            "Poway", "Escondido", "San Marcos", "Vista",
            "Oceanside", "Chula Vista", "El Cajon", "Santee",
        ],
        "wealthy_zips": [
            "92037",  # La Jolla
            "92014",  # Del Mar
            "92067",  # Rancho Santa Fe
            "92024",  # Encinitas
            "92118",  # Coronado
            "92009",  # Carlsbad (La Costa)
        ],
    },
}

# Default active market (can be changed via the UI dropdown)
ACTIVE_MARKET = "Orange County"

# ─── Convenience accessors (derived from ACTIVE_MARKET) ──────────────────────
# These are set at the bottom of this file after Streamlit secrets override,
# so they reflect the UI selection when running inside the app.

def get_market():
    """Return the active market dict."""
    return MARKETS[ACTIVE_MARKET]

def get_region():
    return get_market()["label"]

def get_county():
    return get_market()["county"]

def get_bbox():
    return get_market()["bbox"]

def get_cities():
    return get_market()["cities"]

def get_wealthy_zips():
    return get_market()["wealthy_zips"]

def get_fbn_url():
    return get_market()["fbn_clerk_url"]

# Legacy aliases (used throughout the codebase)
REGION = get_region()
REGION_BBOX = get_bbox()
TARGET_CITIES = get_cities()

# ─── Layer Toggles ───────────────────────────────────────────────────────────
# Layers are split into FREE and PREMIUM tiers.
# FREE layers run with no cost — public data or free-tier APIs.
# PREMIUM layers require paid API subscriptions (Google Maps, Claude API).

# ── FREE LAYERS (no cost, always available) ──────────────────────────────────
LAYERS = {
    "cslb_lifecycle":    True,    # FREE — CSLB public license data
    "fbn_sweep":         True,    # FREE — County Clerk FBN filings (public record)
    "digital_distress":  True,    # FREE — Google Maps unclaimed/low-rated profiles
    "nextdoor_referral": True,    # FREE — Nextdoor referral mentions (manual + AI)
    "workers_comp":      True,    # FREE — CSLB workers comp data (no WC = tiny shop)
    "website_decay":     True,    # FREE — WHOIS + Wayback Machine domain age/decay
}

# ── PREMIUM LAYERS (require paid API keys) ───────────────────────────────────
PREMIUM_LAYERS = {
    "digital_ghost":    False,   # PREMIUM — Yelp Fusion API ($229+/month)
    "permit_pipeline":  False,   # PREMIUM — needs city permit portal scrapers
    "fleet_aging":      False,   # PREMIUM — needs Google Street View + Claude Vision API
}

# Merge for internal use — layers that are ON run in the pipeline
LAYERS.update(PREMIUM_LAYERS)

# ─── Strategy 1: CSLB License Lifecycle (FREE) ──────────────────────────────
CSLB_LICENSE_CLASS      = "C-27"       # Landscaping contractor classification
CSLB_MIN_YEARS_ACTIVE   = 25           # minimum years active to flag as retirement candidate
CSLB_RENEWAL_WARNING_DAYS = 180        # flag if license expires within this many days
CSLB_ENTITY_TYPES_TARGET  = [          # entity types most likely to be acquisition targets
    "Sole Ownership",
    "Individual",
]

# ─── Strategy 2: Digital Ghost (FREE) ────────────────────────────────────────
REVIEW_STALE_DAYS       = 730          # 2 years — flag if last review older than this
MIN_RATING_FOR_GHOST    = 3.5          # minimum Google/Yelp rating to qualify as a "ghost"
MIN_REVIEWS_FOR_GHOST   = 5            # need at least this many reviews to count
OWNER_RESPONSE_LOOKBACK_DAYS = 730     # 2 years — check if owner stopped responding

# ─── Strategy 3: FBN Sweep (FREE) ───────────────────────────────────────────
FBN_MIN_FILING_AGE_YEARS = 15          # minimum years since FBN filing
FBN_MAX_FILING_AGE_YEARS = 25          # maximum years (older = stronger signal)
FBN_SEARCH_TERMS = [                   # search terms for County Clerk FBN lookup
    "Landscaping", "Landscape", "Gardening", "Garden", "Lawn",
    "Tree Service", "Yard", "Grounds", "Irrigation",
]

# ─── Strategy 4: Digital Distress (FREE) ─────────────────────────────────────
DISTRESS_MAX_RATING       = 3.5        # flag businesses rated at or below this
DISTRESS_UNCLAIMED_FLAG   = True       # flag unclaimed Google profiles
DISTRESS_REVIEW_KEYWORDS  = [          # keywords in reviews suggesting owner burnout
    "used to be great", "lately", "no-show", "stopped showing up",
    "doesn't return calls", "went downhill", "not the same",
    "hard to reach", "unreliable now", "used them for years",
]

# ─── Strategy 5: Nextdoor Referral (FREE) ────────────────────────────────────
NEXTDOOR_MIN_MENTIONS     = 3          # minimum times a name appears in referral threads
NEXTDOOR_NO_WEBSITE_BONUS = True       # boost signal if the referral has no web presence
NEXTDOOR_SEARCH_TERMS = [              # search Nextdoor for these phrases
    "landscaper recommendation", "gardener recommendation",
    "lawn care recommendation", "who does your yard",
    "looking for a gardener", "need a landscaper",
]

# ─── Strategy 6: Workers Comp Check (FREE) ──────────────────────────────────
# The CSLB master list includes workers comp insurance status.  A landscaping
# company with NO workers comp = very small (sole prop, no employees).
# These are the smallest shops — easiest to acquire.
WORKERS_COMP_FLAG_MISSING = True   # flag companies with no workers comp

# ─── Strategy 7: Website Decay (FREE) ───────────────────────────────────────
# Check if a company's website domain is expired, parked, or hasn't been
# updated in years using WHOIS + Wayback Machine CDX API (both free).
WEBSITE_DECAY_MIN_YEARS = 2        # domain not updated in 2+ years
WEBSITE_DECAY_CHECK_WHOIS = True   # check WHOIS for domain expiry

# ─── Strategy 8: Permit Pipeline (PREMIUM) ──────────────────────────────────
SMALL_CREW_MAX          = 5
LARGE_PERMIT_VALUE      = 50_000
PERMIT_LOOKBACK_MONTHS  = 12
OVEREXTENDED_PERMIT_COUNT = 2

# ─── Strategy 7: Fleet Aging Vision (PREMIUM) ───────────────────────────────
STREET_VIEW_IMAGE_SIZE  = "640x480"
FLEET_PROFESSIONALISM_THRESHOLD = 4

# ─── FREE API Credentials ────────────────────────────────────────────────────
APIFY_API_TOKEN = ""
APIFY_CSLB_ACTOR_ID = ""
YELP_API_KEY = ""

# ─── PREMIUM API Credentials ─────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY = ""
ANTHROPIC_API_KEY = ""

# ─── Database ────────────────────────────────────────────────────────────────
import os as _os
DB_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "mascout.db")

# ─── Streamlit secrets override ──────────────────────────────────────────────
try:
    import streamlit as st
    _secrets = st.secrets
    APIFY_API_TOKEN     = _secrets.get("APIFY_API_TOKEN",     APIFY_API_TOKEN)
    APIFY_CSLB_ACTOR_ID = _secrets.get("APIFY_CSLB_ACTOR_ID", APIFY_CSLB_ACTOR_ID)
    GOOGLE_MAPS_API_KEY = _secrets.get("GOOGLE_MAPS_API_KEY", GOOGLE_MAPS_API_KEY)
    YELP_API_KEY        = _secrets.get("YELP_API_KEY",        YELP_API_KEY)
    ANTHROPIC_API_KEY   = _secrets.get("ANTHROPIC_API_KEY",   ANTHROPIC_API_KEY)
except Exception:
    pass
