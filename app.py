#!/usr/bin/env python3
"""
app.py — M&A Scout Streamlit Web Portal

Redesigned to match Parcel Scout's layout and styling conventions:
    - Cormorant Garamond serif headings, Montserrat sans-serif body
    - Warm palette adapted for landscaping M&A (forest green + cream)
    - Layer selection panel on the main page with descriptions
    - Clean section flow: Header > Market > Layers > Scan > Results
"""

import json
import sys
import time
from datetime import datetime

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import config
from db import get_connection, get_company_count, get_ranked_companies
from models import CompanyWithSignals
from rank import to_flat_dicts, SIGNAL_LABELS

# ─── Layer metadata (descriptions, icons, why-it-matters) ───────────────────

LAYER_META = {
    # ── FREE LAYERS ──────────────────────────────────────────────────────
    "cslb_lifecycle": {
        "label": "License Lifecycle",
        "icon": "&#128203;",  # clipboard
        "desc": "CSLB C-27 license data: sole proprietors active 25+ years nearing renewal.",
        "why": "A sole proprietor who never incorporated after 25 years is likely approaching retirement with no succession plan.",
        "source": "CA Contractors State License Board (public record)",
        "cost": "Free",
        "tier": "free",
    },
    "fbn_sweep": {
        "label": "FBN Sweep",
        "icon": "&#128220;",  # scroll
        "desc": "County Clerk fictitious business name filings from 15-25 years ago.",
        "why": "An old DBA filing + no website = an owner with a valuable aged client list but no digital footprint or corporate structure.",
        "source": "County Clerk-Recorder (public record)",
        "cost": "Free",
        "tier": "free",
    },
    "digital_distress": {
        "label": "Digital Distress",
        "icon": "&#9888;",  # warning
        "desc": "Google Maps businesses rated 3.5 stars or below with signs of declining service.",
        "why": "Owners with tanking reviews are stressed and overwhelmed. They often jump at an offer that takes the headache away.",
        "source": "Google Maps (public profiles)",
        "cost": "Free (no API key needed)",
        "tier": "free",
    },
    "nextdoor_referral": {
        "label": "Nextdoor Referral",
        "icon": "&#127968;",  # house
        "desc": "First-name gardeners mentioned repeatedly in wealthy neighborhood recommendation threads.",
        "why": "\"Manuel\" mentioned 20 times in Newport Beach with no website owns a Route worth $500K/year. The route IS the asset.",
        "source": "Nextdoor recommendation threads",
        "cost": "Free (manual collection)",
        "tier": "free",
    },
    "workers_comp": {
        "label": "No Workers Comp",
        "icon": "&#128119;",  # construction worker
        "desc": "CSLB contractors with no workers comp insurance — signals a true one-person operation.",
        "why": "No WC = no employees. These are the smallest, cheapest shops to acquire. The owner IS the entire business.",
        "source": "CSLB license data (public record)",
        "cost": "Free",
        "tier": "free",
    },
    "website_decay": {
        "label": "Website Decay",
        "icon": "&#127760;",  # globe
        "desc": "Expired domains, parked pages, or websites not updated in 2+ years (WHOIS + Wayback Machine).",
        "why": "A company that had a website but let it die invested in growth once, then gave up. They're coasting toward an exit.",
        "source": "WHOIS + Wayback Machine CDX API (both free)",
        "cost": "Free",
        "tier": "free",
    },
    "sba_loan": {
        "label": "SBA Loan Flag",
        "icon": "&#128176;",  # money bag
        "desc": "PPP/EIDL loan recipients who never grew — still treading water post-COVID.",
        "why": "A company that took survival money but stayed a sole prop is mentally done growing. They want an exit, not another decade.",
        "source": "SBA Open Data Portal (data.sba.gov, public by law)",
        "cost": "Free",
        "tier": "free",
    },
    "sos_status": {
        "label": "Entity Status",
        "icon": "&#127963;",  # classical building
        "desc": "CA Secretary of State entity status — Suspended, FTB Suspended, or never incorporated.",
        "why": "A Corp/LLC suspended by the Franchise Tax Board = owner stopped paying taxes on the entity. They've mentally checked out.",
        "source": "bizfileonline.sos.ca.gov (free, no account)",
        "cost": "Free",
        "tier": "free",
    },
    "bbb_complaints": {
        "label": "BBB Complaints",
        "icon": "&#128172;",  # speech bubble
        "desc": "BBB complaints the owner never responded to — sign of total disengagement.",
        "why": "An owner who ignores BBB complaints has stopped caring about their reputation. They're ready to hand over the keys.",
        "source": "BBB public profiles (bbb.org)",
        "cost": "Free",
        "tier": "free",
    },
    "bond_amount": {
        "label": "Min Bond",
        "icon": "&#128274;",  # lock
        "desc": "Contractors maintaining the minimum $25K bond for 15+ years — never scaled up.",
        "why": "A minimum-bond shop for 20 years is a classic lifestyle business. The owner earns enough but has zero growth ambition or succession plan.",
        "source": "CSLB license data (public record)",
        "cost": "Free",
        "tier": "free",
    },
    "google_closed": {
        "label": "Google Closed",
        "icon": "&#128683;",  # no entry
        "desc": "Businesses marked 'Permanently Closed' on Google but still holding active CSLB licenses.",
        "why": "Closed on Google + active license = retired-in-place. They still do jobs by word-of-mouth. Buy their license and route.",
        "source": "Google Maps public data",
        "cost": "Free",
        "tier": "free",
    },
    "review_fatigue": {
        "label": "Owner Fatigue",
        "icon": "&#128548;",  # weary face
        "desc": "Reviews mentioning missed calls, no-shows, declining quality — signs the owner is burned out.",
        "why": "Multiple customers independently saying 'quality dropped' = the owner is done. Approach with empathy and a partnership offer.",
        "source": "Review text analysis (keyword matching, optional LLM)",
        "cost": "Free",
        "tier": "free",
    },
    "property_change": {
        "label": "Property Turnover",
        "icon": "&#127970;",  # office building
        "desc": "Commercial properties changing hands — new owners fire old vendors within 90 days.",
        "why": "Two plays: buy the fired vendor's contracts, OR pitch the new owner directly. Either way, property sales create deal flow.",
        "source": "County Recorder Grant Deeds (public record)",
        "cost": "Free",
        "tier": "free",
    },
    # ── PREMIUM LAYERS ───────────────────────────────────────────────────
    "digital_ghost": {
        "label": "Digital Ghost",
        "icon": "&#128123;",  # ghost
        "desc": "High-rated businesses whose owner stopped managing their online presence.",
        "why": "A 4.5-star company with no reviews in 2+ years has a great reputation but a burnt-out owner ready for a roll-up.",
        "source": "Yelp Fusion API (reviews + ratings)",
        "cost": "$229+/month (Yelp Places API)",
        "tier": "premium",
    },
    "permit_pipeline": {
        "label": "Permit Stress",
        "icon": "&#128679;",  # construction
        "desc": "Small crews taking on $100K+ residential permits they can't handle alone.",
        "why": "A 3-person crew on a $200K Newport Coast remodel is operationally stressed. Offer subcontracting help as a foot in the door.",
        "source": "City building permit portals (public record)",
        "cost": "Free (needs per-city scrapers)",
        "tier": "premium",
    },
    "fleet_aging": {
        "label": "Fleet Aging",
        "icon": "&#128665;",  # truck
        "desc": "Street View imagery analysed by AI for aging trucks, no branding, poor equipment.",
        "why": "Old unbranded trucks = capex debt. The owner can't afford $100K in new equipment and might prefer a cash buyout.",
        "source": "Google Street View + Claude Vision AI",
        "cost": "$7/1K images + ~$0.02/analysis",
        "tier": "premium",
    },
}


# ─── Page Config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="M&A Scout",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ─── CSS — Parcel Scout design system adapted for M&A ────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300;1,400&family=Montserrat:wght@300;400;500;600&display=swap');

    /* ── Global ────────────────────────────────────────────────── */
    html, body, [class*="css"] {
        font-family: 'Montserrat', sans-serif;
    }
    .main .block-container {
        padding: 3rem 5rem 4rem 5rem;
        max-width: 1100px;
        margin: 0 auto;
    }

    /* ── Typography ────────────────────────────────────────────── */
    h1 {
        font-family: 'Cormorant Garamond', serif !important;
        font-weight: 300 !important;
        letter-spacing: 0.06em !important;
        color: #1B4332 !important;
    }
    h2, h3 {
        font-family: 'Cormorant Garamond', serif !important;
        font-weight: 400 !important;
        letter-spacing: 0.04em !important;
        color: #1B4332 !important;
    }

    /* Section labels (like Parcel Scout's .gb-label) */
    .ms-label {
        font-family: 'Cormorant Garamond', serif;
        font-size: 1.1rem;
        font-style: italic;
        font-weight: 400;
        color: #2D6A4F;
        border-bottom: 1px solid #B7D4C0;
        padding-bottom: 0.3rem;
        margin-bottom: 1rem;
        display: block;
    }

    /* ── Metrics ───────────────────────────────────────────────── */
    [data-testid="metric-container"] {
        background: #FFFFFF;
        border: 1px solid #B7D4C0;
        padding: 1.1rem 1.3rem;
    }
    [data-testid="metric-container"] label {
        font-family: 'Montserrat', sans-serif !important;
        font-size: 0.58rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.18em !important;
        color: #2D6A4F !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 2rem !important;
        font-weight: 400 !important;
        color: #1B4332 !important;
    }

    /* ── Buttons ───────────────────────────────────────────────── */
    .stButton > button[kind="primary"] {
        background-color: #1B4332 !important;
        color: #F0F7F2 !important;
        font-family: 'Montserrat', sans-serif !important;
        font-size: 0.68rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.22em !important;
        text-transform: uppercase !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 1rem 2rem !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #2D6A4F !important;
    }
    .stDownloadButton > button {
        background: transparent !important;
        border: 1px solid #B7D4C0 !important;
        color: #1B4332 !important;
        font-size: 0.65rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.18em !important;
        text-transform: uppercase !important;
        border-radius: 0 !important;
    }
    .stDownloadButton > button:hover {
        background: #1B4332 !important;
        color: #F0F7F2 !important;
    }

    /* ── Tabs ──────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 1px solid #B7D4C0;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Montserrat', sans-serif;
        font-size: 0.62rem;
        font-weight: 500;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        padding: 0.8rem 1.6rem;
        color: #2D6A4F;
    }
    .stTabs [aria-selected="true"] {
        border-bottom: 2px solid #1B4332 !important;
        color: #1B4332 !important;
    }

    /* ── Expanders ─────────────────────────────────────────────── */
    [data-testid="stExpander"] summary p {
        font-family: 'Montserrat', sans-serif !important;
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        color: #1B4332 !important;
    }
    [data-testid="stExpander"] summary svg {
        color: #2D6A4F !important;
    }
    [data-testid="stExpander"] details > div {
        background-color: #F0F7F2 !important;
        border: 1px solid #B7D4C0 !important;
        padding: 1rem !important;
    }

    /* ── Checkboxes ────────────────────────────────────────────── */
    [data-testid="stCheckbox"] label span {
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: #1A2E22 !important;
    }

    /* ── Selectbox ─────────────────────────────────────────────── */
    [data-baseweb="select"] {
        border-radius: 0 !important;
    }

    /* ── Alerts ────────────────────────────────────────────────── */
    [data-testid="stAlert"][data-baseweb*="success"] {
        background: #E8F5E9 !important;
        border: 1.5px solid #4A6741 !important;
    }

    /* ── Hide branding ─────────────────────────────────────────── */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown('<span class="ms-label">Acquisition Intelligence</span>',
            unsafe_allow_html=True)
st.markdown("# M&A Scout")
st.markdown("*Landscaping acquisition sourcing engine — Southern California*")

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════════════
# MARKET SELECTOR
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown('<span class="ms-label">Target Market</span>',
            unsafe_allow_html=True)

market_options = list(config.MARKETS.keys())
selected_market = st.selectbox(
    "Market",
    options=market_options,
    index=market_options.index(config.ACTIVE_MARKET),
    key="market_selector",
    label_visibility="collapsed",
)
config.ACTIVE_MARKET = selected_market

# Define load_data early so it's available for the file uploader
@st.cache_data(ttl=60)
def load_data():
    conn = get_connection()
    results = get_ranked_companies(conn)
    conn.close()
    return results

market = config.get_market()
st.caption("{} — {} cities, {} wealthy zip codes tracked".format(
    market["label"], len(market["cities"]), len(market["wealthy_zips"])))

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER SELECTION PANEL
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown('<span class="ms-label">Acquisition Signal Layers</span>',
            unsafe_allow_html=True)
st.caption("Each layer is an independent intelligence source. "
           "Toggle layers on or off, then run a scan.")

layers_state = {}

# ── Free Layers (3-column grid with descriptions) ────────────────────────────

free_layer_keys = ["cslb_lifecycle", "fbn_sweep", "digital_distress",
                   "nextdoor_referral", "workers_comp", "website_decay",
                   "sba_loan", "sos_status", "bbb_complaints",
                   "bond_amount", "google_closed",
                   "review_fatigue", "property_change"]

c1, c2, c3 = st.columns(3)
for i, key in enumerate(free_layer_keys):
    meta = LAYER_META[key]
    col = [c1, c2, c3][i % 3]
    with col:
        layers_state[key] = st.checkbox(
            meta["label"],
            value=config.LAYERS.get(key, True),
            key="layer_" + key,
        )
        st.caption(meta["desc"])
        with st.expander("Why it matters"):
            st.markdown(meta["why"])
            st.markdown("**Source:** {}".format(meta["source"]))
            st.markdown("**Cost:** {}".format(meta["cost"]))

st.markdown("")  # spacing

# ── Premium Layers ───────────────────────────────────────────────────────────

with st.expander("Premium Layers (paid API keys required)"):
    pc1, pc2, pc3 = st.columns(3)
    for i, key in enumerate(["digital_ghost", "permit_pipeline", "fleet_aging"]):
        meta = LAYER_META[key]
        col = [pc1, pc2, pc3][i % 3]
        with col:
            layers_state[key] = st.checkbox(
                meta["label"],
                value=config.LAYERS.get(key, False),
                key="layer_" + key,
            )
            st.caption(meta["desc"])
            st.markdown("**Why:** {}".format(meta["why"]))
            st.markdown("**Source:** {}".format(meta["source"]))
            st.markdown("**Cost:** {}".format(meta["cost"]))

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════════════
# FILTERS + RUN SCAN
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown('<span class="ms-label">Filters &amp; Scan</span>',
            unsafe_allow_html=True)

fc1, fc2, fc3 = st.columns([2, 2, 1])
with fc1:
    city_filter = st.multiselect(
        "Filter by City",
        options=config.get_cities(),
        default=[],
    )
with fc2:
    min_score = st.slider("Minimum Score", 0, 100, 0, 5)
with fc3:
    st.markdown("")  # vertical alignment spacer
    st.markdown("")
    run_btn = st.button("Run Full Scan", type="primary", use_container_width=True)

if run_btn:
    st.session_state["run_scan"] = True


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING + SCAN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

def run_full_scan():
    from analyze import run_analysis

    with st.status("Scanning {} ...".format(config.get_region()), expanded=True) as status:
        conn = get_connection()

        # Free collectors
        st.write("Collecting CSLB license data...")
        from collectors.cslb import collect_cslb
        collect_cslb(conn)

        if layers_state.get("fbn_sweep"):
            st.write("Sweeping FBN filings...")
            from collectors.fbn import collect_fbn
            collect_fbn(conn)

        if layers_state.get("digital_distress"):
            st.write("Scanning Google Maps for distress signals...")
            from collectors.google_distress import collect_google_distress
            collect_google_distress(conn)

        if layers_state.get("nextdoor_referral"):
            st.write("Collecting Nextdoor referral data...")
            from collectors.nextdoor import collect_nextdoor
            collect_nextdoor(conn)

        # Premium collectors
        if config.YELP_API_KEY and layers_state.get("digital_ghost"):
            st.write("Collecting Yelp review data...")
            from collectors.yelp import collect_yelp
            collect_yelp(conn)

        if config.GOOGLE_MAPS_API_KEY:
            st.write("Enriching with Google Places data...")
            from collectors.google_places import collect_google_places
            collect_google_places(conn)

        if layers_state.get("permit_pipeline"):
            st.write("Scraping building permits...")
            from collectors.permits import collect_permits
            collect_permits(conn)

        st.write("Running signal analysis...")
        run_analysis(conn)
        conn.close()

        status.update(label="Scan complete", state="complete", expanded=False)

    load_data.clear()
    st.session_state["run_scan"] = False


if st.session_state.get("run_scan"):
    run_full_scan()
    st.rerun()

results = load_data()

# Apply filters
if min_score > 0:
    results = [r for r in results if r.opportunity_score >= min_score]
if city_filter:
    results = [r for r in results if r.company.city in city_filter]

enabled_count = sum(1 for v in config.LAYERS.values() if v)

# Check if signals have been generated (not just companies loaded)
has_signals = any(r.signals_fired > 0 for r in results) if results else False

if not results:
    st.markdown("---")
    st.info("No companies in database yet. Click **Run Full Scan** above to collect data.")
    st.stop()

if not has_signals:
    st.markdown("---")
    conn = get_connection()
    total = get_company_count(conn)
    conn.close()
    st.success("**{}** contractors loaded from CSLB data. Click **Run Full Scan** above to analyse them with all 13 signal layers.".format(total))
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown('<span class="ms-label">Results &mdash; {}</span>'.format(
    config.get_region()), unsafe_allow_html=True)

# ── Summary Metrics ──────────────────────────────────────────────────────────

scores = [r.opportunity_score for r in results]
with_signals = sum(1 for r in results if r.signals_fired > 0)
avg_score = sum(scores) / len(scores) if scores else 0
top_score = max(scores) if scores else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Companies Found", len(results))
m2.metric("Top Score", "{:.0f}%".format(top_score))
m3.metric("Average Score", "{:.0f}%".format(avg_score))
m4.metric("Signals Active", "{} of {}".format(
    sum(1 for v in layers_state.values() if v), len(LAYER_META)))

# ── Export buttons ───────────────────────────────────────────────────────────

flat = to_flat_dicts(results)
ec1, ec2, _ = st.columns([1, 1, 4])
with ec1:
    st.download_button(
        "Export CSV",
        data=pd.DataFrame(flat).to_csv(index=False),
        file_name="ma_scout_{}.csv".format(datetime.now().strftime("%Y%m%d")),
        mime="text/csv",
        use_container_width=True,
    )
with ec2:
    st.download_button(
        "Export JSON",
        data=json.dumps(flat, indent=2, default=str),
        file_name="ma_scout_{}.json".format(datetime.now().strftime("%Y%m%d")),
        mime="application/json",
        use_container_width=True,
    )

st.markdown("---")


# ═══════════════════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════════════════

tab_rank, tab_map, tab_cards, tab_outreach, tab_data = st.tabs([
    "Rankings", "Map", "Company Cards", "Outreach", "Raw Data"
])


# ─── TAB: Rankings ───────────────────────────────────────────────────────────

with tab_rank:
    rows = []
    for rank, r in enumerate(results, 1):
        c = r.company
        fired_names = [
            SIGNAL_LABELS.get(s.layer_name, s.layer_name)
            for s in r.signals if s.signal
        ]
        rows.append({
            "Rank": rank,
            "Score": r.opportunity_score,
            "Signals": "{}/{}".format(r.signals_fired, enabled_count),
            "Business": c.business_name,
            "City": c.city or "",
            "Entity": c.license_type or "",
            "Years": str(next(
                (s.data.get("years_active", "")
                 for s in r.signals if s.layer_name == "cslb_lifecycle"),
                "",
            )),
            "Fired": ", ".join(fired_names) if fired_names else "None",
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%.0f",
            ),
        },
    )


# ─── TAB: Map ────────────────────────────────────────────────────────────────

with tab_map:
    bbox = config.get_bbox()
    center_lat = (bbox[0] + bbox[2]) / 2
    center_lon = (bbox[1] + bbox[3]) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=10,
        tiles="CartoDB positron",
    )

    for r in results:
        c = r.company
        if not (c.lat and c.lon):
            continue

        if r.opportunity_score >= 50:
            color, fill = "#1B4332", "#40916C"
        elif r.opportunity_score >= 25:
            color, fill = "#B8860B", "#DAA520"
        else:
            color, fill = "#6C757D", "#ADB5BD"

        radius = max(5, r.opportunity_score / 10)

        fired_chips = "".join(
            '<span style="display:inline-block;padding:2px 6px;border-radius:0;'
            'font-size:10px;font-family:Montserrat,sans-serif;'
            'background:#E8F5E9;color:#2A4028;border:1px solid #4A6741;margin:2px;">'
            '{}</span>'.format(SIGNAL_LABELS.get(s.layer_name, s.layer_name))
            for s in r.signals if s.signal
        )

        popup_html = (
            '<div style="font-family:Montserrat,sans-serif;min-width:220px;padding:4px;">'
            '<div style="font-family:Cormorant Garamond,serif;font-size:1.2rem;'
            'font-weight:400;color:#1B4332;margin-bottom:4px;">{name}</div>'
            '<div style="font-size:0.7rem;color:#6C757D;margin-bottom:6px;'
            'letter-spacing:0.1em;text-transform:uppercase;">{city} &bull; {entity}</div>'
            '<div style="font-family:Cormorant Garamond,serif;font-size:1.6rem;'
            'font-weight:300;color:{color};margin-bottom:4px;">{score:.0f}%</div>'
            '<div style="background:#E9ECEF;height:4px;margin-bottom:8px;">'
            '<div style="background:{color};height:4px;width:{score}%;"></div></div>'
            '<div>{badges}</div></div>'
        ).format(
            name=c.business_name,
            city=c.city or "",
            entity=c.license_type or "Unknown",
            color=color,
            score=r.opportunity_score,
            badges=fired_chips or '<span style="color:#6C757D;font-size:11px;">No signals</span>',
        )

        folium.CircleMarker(
            location=[c.lat, c.lon],
            radius=radius,
            color=color,
            fill=True,
            fill_color=fill,
            fill_opacity=0.7,
            weight=2,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip="{} ({:.0f}%)".format(c.business_name, r.opportunity_score),
        ).add_to(m)

    st.caption("Companies plotted by registered address. "
               "Marker size reflects opportunity score.")
    st_folium(m, use_container_width=True, height=560)


# ─── TAB: Company Cards ─────────────────────────────────────────────────────

with tab_cards:
    for r in results:
        c = r.company
        score = r.opportunity_score
        if score >= 50:
            score_color = "#1B4332"
        elif score >= 25:
            score_color = "#B8860B"
        else:
            score_color = "#6C757D"

        with st.expander(
            "**{}** — {} — {:.0f}%".format(c.business_name, c.city or "", score),
            expanded=(score >= 50),
        ):
            # Header with score
            st.markdown(
                '<div style="padding:0.75rem 0 0.5rem;border-bottom:1px solid #B7D4C0;">'
                '<span style="font-size:0.56rem;font-weight:700;text-transform:uppercase;'
                'letter-spacing:0.18em;color:{color};">SCORE {score:.0f}%</span>'
                '<div style="font-family:Cormorant Garamond,serif;font-size:1.35rem;'
                'font-weight:400;color:#1B4332;">{name}</div>'
                '</div>'.format(color=score_color, score=score, name=c.business_name),
                unsafe_allow_html=True,
            )

            # Key intel table
            st.markdown(
                '<div style="padding:0.6rem 0;border-bottom:1px solid #B7D4C0;">'
                '<table style="width:100%;font-family:Montserrat,sans-serif;font-size:0.72rem;color:#2A3E30;">'
                '<tr><td>&#128100; Owner</td><td style="text-align:right;font-weight:500;">{owner}</td></tr>'
                '<tr><td>&#128205; Address</td><td style="text-align:right;font-weight:500;">{addr}</td></tr>'
                '<tr><td>&#128222; Phone</td><td style="text-align:right;font-weight:500;">{phone}</td></tr>'
                '<tr><td>&#127380; License</td><td style="text-align:right;font-weight:500;">{lic} ({type})</td></tr>'
                '</table></div>'.format(
                    owner=c.owner_name or "Unknown",
                    addr=c.address or "N/A",
                    phone=c.phone or "N/A",
                    lic=c.license_number or "N/A",
                    type=c.license_type or "Unknown",
                ),
                unsafe_allow_html=True,
            )

            # Review data
            if c.google_rating or c.yelp_rating:
                parts = []
                if c.google_rating:
                    parts.append("Google {:.1f}★ ({})".format(
                        c.google_rating, c.google_review_count or 0))
                if c.yelp_rating:
                    parts.append("Yelp {:.1f}★ ({})".format(
                        c.yelp_rating, c.yelp_review_count or 0))
                st.caption(" &bull; ".join(parts))

            # Signal chips
            fired = [s for s in r.signals if s.signal]
            if fired:
                chips = "".join(
                    '<span style="display:inline-block;background:#E8F5E9;border:1px solid #4A6741;'
                    'color:#2A4028;font-size:0.58rem;font-family:Montserrat,sans-serif;'
                    'padding:2px 6px;margin:2px;">{}</span>'.format(
                        SIGNAL_LABELS.get(s.layer_name, s.layer_name))
                    for s in fired
                )
                st.markdown(chips, unsafe_allow_html=True)

            # Full signal details
            with st.expander("Full signal details"):
                for signal in r.signals:
                    icon = "&#9989;" if signal.signal else "&#11036;"
                    label = SIGNAL_LABELS.get(signal.layer_name, signal.layer_name)
                    score_str = " ({:.0%})".format(signal.score) if signal.score is not None else ""
                    st.markdown(
                        "{} **{}**{} — {}".format(icon, label, score_str, signal.detail),
                        unsafe_allow_html=True,
                    )


# ─── TAB: Outreach ──────────────────────────────────────────────────────────

with tab_outreach:
    company_options = {
        "{} ({:.0f}%)".format(r.company.business_name, r.opportunity_score): r
        for r in results if r.signals_fired > 0
    }

    if not company_options:
        st.info("No companies with fired signals.")
    else:
        selected_name = st.selectbox(
            "Target Company",
            options=list(company_options.keys()),
        )
        selected = company_options[selected_name]

        oc1, oc2 = st.columns(2)
        with oc1:
            template_type = st.selectbox(
                "Message Type",
                options=["intro_email", "acquisition_letter", "partnership_inquiry"],
                format_func=lambda x: {
                    "intro_email": "Introduction Email",
                    "acquisition_letter": "Acquisition Letter",
                    "partnership_inquiry": "Partnership Inquiry",
                }[x],
            )
        with oc2:
            buyer_name = st.text_input(
                "Your Name / Company",
                value="a local landscape management group",
            )

        if not config.ANTHROPIC_API_KEY:
            st.caption("Using template-based outreach. "
                       "Add ANTHROPIC_API_KEY for AI-personalized messages.")

        if st.button("Generate Outreach", type="primary"):
            with st.spinner("Generating message..."):
                from outreach.templates import generate_outreach
                message = generate_outreach(selected, template_type, buyer_name)

            st.markdown("---")
            st.text_area("Generated Message", value=message, height=350)


# ─── TAB: Raw Data ──────────────────────────────────────────────────────────

with tab_data:
    conn = get_connection()
    total = get_company_count(conn)
    signal_count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    permit_count = conn.execute("SELECT COUNT(*) FROM permit_records").fetchone()[0]
    conn.close()

    dc1, dc2, dc3 = st.columns(3)
    dc1.metric("Total Companies", total)
    dc2.metric("Signal Records", signal_count)
    dc3.metric("Permit Records", permit_count)

    st.markdown("---")
    st.dataframe(pd.DataFrame(flat).head(50), use_container_width=True, hide_index=True)
