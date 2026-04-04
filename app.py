#!/usr/bin/env python3
"""
app.py — M&A Scout Streamlit Web Portal

The main dashboard for the acquisition sourcing engine.  Users can:
    - Run data collection and analysis directly from the UI
    - View ranked acquisition targets on an interactive map
    - Explore detailed company cards with signal breakdowns
    - Generate outreach letters/emails
    - Export data to CSV/JSON

Layout:
    ┌────────────────────────────────────┐
    │  Header + Metrics                  │
    │  Tabs: Map | Rankings | Cards |    │
    │        Outreach | Data Export       │  ← FREE
    │────────────────────────────────────│
    │  ── Premium Layers ──              │
    │  Permit Pipeline | Fleet Aging     │  ← PREMIUM (bottom)
    └────────────────────────────────────┘
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

# ─── Page Config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="M&A Scout — Orange County",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main-header {
        background: linear-gradient(135deg, #1B4332 0%, #2D6A4F 100%);
        padding: 2rem 2.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .main-header h1 {
        font-size: 2rem; font-weight: 700;
        margin: 0 0 0.3rem 0; color: white;
    }
    .main-header p {
        font-size: 1rem; opacity: 0.85;
        margin: 0; color: #E9ECEF;
    }

    .signal-badge {
        display: inline-block; padding: 0.25rem 0.6rem;
        border-radius: 12px; font-size: 0.78rem; font-weight: 500; margin: 0.15rem;
    }
    .signal-fired { background: #D4EDDA; color: #155724; border: 1px solid #C3E6CB; }
    .signal-quiet { background: #F8F9FA; color: #6C757D; border: 1px solid #DEE2E6; }

    .premium-header {
        background: linear-gradient(135deg, #4A4A4A 0%, #6B6B6B 100%);
        padding: 1.2rem 1.8rem;
        border-radius: 10px;
        margin: 2.5rem 0 1rem 0;
        color: white;
    }
    .premium-header h2 {
        font-size: 1.3rem; font-weight: 600;
        margin: 0 0 0.2rem 0; color: white;
    }
    .premium-header p {
        font-size: 0.85rem; opacity: 0.8;
        margin: 0; color: #E0E0E0;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ─── Market Selector ─────────────────────────────────────────────────────────

market_options = list(config.MARKETS.keys())
selected_market = st.selectbox(
    "Select Market",
    options=market_options,
    index=market_options.index(config.ACTIVE_MARKET),
    key="market_selector",
)
# Update the active market so all config accessors use it
config.ACTIVE_MARKET = selected_market

st.markdown(
    '<div class="main-header">'
    '<h1>M&A Scout</h1>'
    '<p>Acquisition Sourcing Engine &mdash; {}</p>'
    '</div>'.format(config.get_region()),
    unsafe_allow_html=True,
)


# ─── Sidebar Controls ───────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Configuration")

    st.markdown("**Free Layers**")
    layers_state = {}
    free_layers = ["cslb_lifecycle", "digital_ghost", "fbn_sweep",
                   "digital_distress", "nextdoor_referral"]
    for layer_name in free_layers:
        layers_state[layer_name] = st.checkbox(
            SIGNAL_LABELS.get(layer_name, layer_name),
            value=config.LAYERS.get(layer_name, True),
            key="layer_" + layer_name,
        )

    st.markdown("**Premium Layers**")
    for layer_name in ("permit_pipeline", "fleet_aging"):
        layers_state[layer_name] = st.checkbox(
            SIGNAL_LABELS.get(layer_name, layer_name) + " (PAID)",
            value=config.LAYERS.get(layer_name, False),
            key="layer_" + layer_name,
        )

    st.markdown("---")
    st.markdown("**Filters**")
    min_score = st.slider("Minimum Score", 0, 100, 0, 5)

    city_filter = st.multiselect(
        "Filter by City",
        options=config.get_cities(),
        default=[],
    )

    st.markdown("---")
    if st.button("Run Full Scan", type="primary", use_container_width=True):
        st.session_state["run_scan"] = True


# ─── Data Loading ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_data():
    """Load ranked companies from the database."""
    conn = get_connection()
    results = get_ranked_companies(conn)
    conn.close()
    return results


def run_full_scan():
    """Run the complete pipeline: scout -> analyze for the active market."""
    from analyze import run_analysis

    with st.spinner("Collecting data for {}...".format(config.get_region())):
        conn = get_connection()

        # Free collectors
        from collectors.cslb import collect_cslb
        from collectors.yelp import collect_yelp
        collect_cslb(conn)
        collect_yelp(conn)

        if layers_state.get("fbn_sweep"):
            from collectors.fbn import collect_fbn
            collect_fbn(conn)

        if layers_state.get("digital_distress"):
            from collectors.google_distress import collect_google_distress
            collect_google_distress(conn)

        if layers_state.get("nextdoor_referral"):
            from collectors.nextdoor import collect_nextdoor
            collect_nextdoor(conn)

        # Premium collectors
        if config.GOOGLE_MAPS_API_KEY:
            from collectors.google_places import collect_google_places
            collect_google_places(conn)

        if layers_state.get("permit_pipeline"):
            from collectors.permits import collect_permits
            collect_permits(conn)

    with st.spinner("Running signal analysis..."):
        run_analysis(conn)
        conn.close()

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

# Count enabled layers for display
enabled_count = sum(1 for v in config.LAYERS.values() if v)

# ─── Metrics Row ─────────────────────────────────────────────────────────────

if results:
    scores = [r.opportunity_score for r in results]
    with_signals = sum(1 for r in results if r.signals_fired > 0)
    avg_score = sum(scores) / len(scores) if scores else 0
    top_score = max(scores) if scores else 0

    cols = st.columns(4)
    cols[0].metric("Companies", len(results))
    cols[1].metric("With Signals", with_signals)
    cols[2].metric("Avg Score", "{:.1f}".format(avg_score))
    cols[3].metric("Top Score", "{:.1f}".format(top_score))
else:
    st.info(
        "No companies in database yet. "
        "Click **Run Full Scan** in the sidebar to collect data, "
        "or run `python3 rank.py --full` from the terminal."
    )


# ═══════════════════════════════════════════════════════════════════════════
# FREE SECTION — Tabs for the core (free) acquisition intelligence
# ═══════════════════════════════════════════════════════════════════════════

tab_map, tab_rankings, tab_cards, tab_outreach, tab_data = st.tabs([
    "Map", "Rankings", "Company Cards", "Outreach", "Data Export"
])


# ─── TAB: Map ────────────────────────────────────────────────────────────────

with tab_map:
    if results:
        m = folium.Map(
            location=[33.72, -117.78],
            zoom_start=10,
            tiles="CartoDB positron",
        )

        for r in results:
            c = r.company
            if c.lat and c.lon:
                if r.opportunity_score >= 50:
                    color, fill = "#2D6A4F", "#40916C"
                elif r.opportunity_score >= 25:
                    color, fill = "#B8860B", "#DAA520"
                else:
                    color, fill = "#6C757D", "#ADB5BD"

                radius = max(5, r.opportunity_score / 10)

                fired_badges = "".join(
                    '<span style="display:inline-block;padding:2px 6px;border-radius:10px;'
                    'font-size:11px;background:#D4EDDA;color:#155724;margin:2px;">'
                    '{}</span>'.format(SIGNAL_LABELS.get(s.layer_name, s.layer_name))
                    for s in r.signals if s.signal
                )

                popup_html = """
                <div style="font-family:Inter,sans-serif;min-width:220px;padding:4px;">
                    <div style="font-size:14px;font-weight:600;color:#1B4332;margin-bottom:4px;">
                        {name}
                    </div>
                    <div style="font-size:12px;color:#6C757D;margin-bottom:6px;">
                        {city} &bull; {entity}
                    </div>
                    <div style="font-size:20px;font-weight:700;color:{color};margin-bottom:4px;">
                        {score:.0f}/100
                    </div>
                    <div style="background:#E9ECEF;border-radius:4px;height:6px;margin-bottom:8px;">
                        <div style="background:{color};height:6px;border-radius:4px;width:{score}%;"></div>
                    </div>
                    <div style="font-size:11px;">
                        {badges}
                    </div>
                </div>
                """.format(
                    name=c.business_name,
                    city=c.city or "",
                    entity=c.license_type or "Unknown entity",
                    color=color,
                    score=r.opportunity_score,
                    badges=fired_badges or '<span style="color:#6C757D;">No signals</span>',
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
                    tooltip="{} ({:.0f}/100)".format(c.business_name, r.opportunity_score),
                ).add_to(m)

        st_folium(m, width=None, height=550, use_container_width=True)

        st.markdown("""
        <div style="display:flex;gap:1.5rem;justify-content:center;margin-top:0.5rem;font-size:0.85rem;">
            <span><span style="color:#2D6A4F;font-size:1.2rem;">&#9679;</span> Score &ge; 50 (Hot)</span>
            <span><span style="color:#DAA520;font-size:1.2rem;">&#9679;</span> Score &ge; 25 (Warm)</span>
            <span><span style="color:#ADB5BD;font-size:1.2rem;">&#9679;</span> Score &lt; 25 (Cool)</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No companies with coordinates to display on the map.")


# ─── TAB: Rankings ───────────────────────────────────────────────────────────

with tab_rankings:
    if results:
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
                "Entity Type": c.license_type or "",
                "Years Active": str(next(
                    (s.data.get("years_active", "")
                     for s in r.signals if s.layer_name == "cslb_lifecycle"),
                    "",
                )),
                "Signals Fired": ", ".join(fired_names) if fired_names else "None",
            })

        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%.1f",
                ),
            },
        )
    else:
        st.info("No ranked companies to display.")


# ─── TAB: Company Cards ─────────────────────────────────────────────────────

with tab_cards:
    if results:
        for r in results:
            c = r.company
            with st.expander(
                "**{}** — {} — Score: {:.0f}/100".format(
                    c.business_name, c.city or "OC", r.opportunity_score
                ),
                expanded=(r.opportunity_score >= 50),
            ):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown("**Owner:** {}".format(c.owner_name or "Unknown"))
                    st.markdown("**Address:** {}".format(c.address or "N/A"))
                    st.markdown("**Phone:** {}".format(c.phone or "N/A"))
                    st.markdown("**Website:** {}".format(c.website or "None"))
                    st.markdown("**License:** {} ({})".format(
                        c.license_number or "N/A", c.license_type or "Unknown"))
                    if c.license_issue_date:
                        st.markdown("**Licensed Since:** {}".format(c.license_issue_date))
                    if c.license_expiry_date:
                        st.markdown("**Expires:** {}".format(c.license_expiry_date))

                with col2:
                    score_color = (
                        "#2D6A4F" if r.opportunity_score >= 50
                        else "#B8860B" if r.opportunity_score >= 25
                        else "#6C757D"
                    )
                    st.markdown(
                        '<div style="text-align:center;padding:1rem;">'
                        '<div style="font-size:2.5rem;font-weight:700;color:{};">'
                        '{:.0f}</div>'
                        '<div style="font-size:0.85rem;color:#6C757D;">/ 100</div>'
                        '</div>'.format(score_color, r.opportunity_score),
                        unsafe_allow_html=True,
                    )

                    if c.google_rating:
                        st.markdown("Google: {:.1f}★ ({} reviews)".format(
                            c.google_rating, c.google_review_count or 0))
                    if c.yelp_rating:
                        st.markdown("Yelp: {:.1f}★ ({} reviews)".format(
                            c.yelp_rating, c.yelp_review_count or 0))

                st.markdown("---")
                st.markdown("**Signal Analysis**")

                for signal in r.signals:
                    icon = "✅" if signal.signal else "⬜"
                    label = SIGNAL_LABELS.get(signal.layer_name, signal.layer_name)
                    score_str = " ({:.0%})".format(signal.score) if signal.score is not None else ""
                    st.markdown("{} **{}**{}".format(icon, label, score_str))
                    st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;{}".format(signal.detail))
    else:
        st.info("No companies to display. Run a scan first.")


# ─── TAB: Outreach ──────────────────────────────────────────────────────────

with tab_outreach:
    if results:
        company_options = {
            "{} ({:.0f}/100)".format(r.company.business_name, r.opportunity_score): r
            for r in results if r.signals_fired > 0
        }

        if not company_options:
            st.info("No companies with fired signals. Run analysis first.")
        else:
            selected_name = st.selectbox(
                "Select a company",
                options=list(company_options.keys()),
            )
            selected = company_options[selected_name]

            col1, col2 = st.columns(2)
            with col1:
                template_type = st.selectbox(
                    "Message Type",
                    options=["intro_email", "acquisition_letter", "partnership_inquiry"],
                    format_func=lambda x: {
                        "intro_email": "Introduction Email",
                        "acquisition_letter": "Acquisition Letter",
                        "partnership_inquiry": "Partnership Inquiry",
                    }[x],
                )
            with col2:
                buyer_name = st.text_input(
                    "Your Name / Company",
                    value="a local landscape management group",
                )

            # Note about premium LLM outreach
            if not config.ANTHROPIC_API_KEY:
                st.caption(
                    "Using template-based outreach. "
                    "Add an ANTHROPIC_API_KEY for AI-personalized messages."
                )

            if st.button("Generate Outreach", type="primary"):
                with st.spinner("Generating message..."):
                    from outreach.templates import generate_outreach
                    message = generate_outreach(selected, template_type, buyer_name)

                st.markdown("---")
                st.markdown("**Generated Message:**")
                st.text_area(
                    "Copy this message",
                    value=message,
                    height=350,
                    label_visibility="collapsed",
                )
    else:
        st.info("No companies available. Run a scan first.")


# ─── TAB: Data Export ────────────────────────────────────────────────────────

with tab_data:
    if results:
        flat = to_flat_dicts(results)
        df = pd.DataFrame(flat)

        col1, col2 = st.columns(2)
        with col1:
            csv_data = df.to_csv(index=False)
            st.download_button(
                "Download CSV",
                data=csv_data,
                file_name="ma_scout_{}.csv".format(datetime.now().strftime("%Y%m%d")),
                mime="text/csv",
                use_container_width=True,
            )
        with col2:
            json_data = json.dumps(flat, indent=2, default=str)
            st.download_button(
                "Download JSON",
                data=json_data,
                file_name="ma_scout_{}.json".format(datetime.now().strftime("%Y%m%d")),
                mime="application/json",
                use_container_width=True,
            )

        st.markdown("---")
        st.markdown("**Database Statistics**")
        conn = get_connection()
        total = get_company_count(conn)
        signal_count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        permit_count = conn.execute("SELECT COUNT(*) FROM permit_records").fetchone()[0]
        conn.close()

        stat_cols = st.columns(3)
        stat_cols[0].metric("Total Companies", total)
        stat_cols[1].metric("Signal Records", signal_count)
        stat_cols[2].metric("Permit Records", permit_count)

        st.markdown("---")
        st.markdown("**Raw Data Preview**")
        st.dataframe(df.head(20), use_container_width=True, hide_index=True)
    else:
        st.info("No data to export. Run a scan first.")


# ═══════════════════════════════════════════════════════════════════════════
# PREMIUM SECTION — Paid layers that require API subscriptions
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("""
<div class="premium-header">
    <h2>Premium Layers</h2>
    <p>Additional acquisition signals requiring paid API subscriptions.
       Enable in the sidebar after adding API keys to config.py.</p>
</div>
""", unsafe_allow_html=True)

premium_col1, premium_col2 = st.columns(2)

with premium_col1:
    with st.container(border=True):
        st.markdown("**Permit-to-Acquisition Pipeline**")
        st.caption("Scrapes OC city building permits to find small crews overwhelmed by large projects.")

        if config.LAYERS.get("permit_pipeline"):
            # Show permit data if enabled
            conn = get_connection()
            permit_count = conn.execute("SELECT COUNT(*) FROM permit_records").fetchone()[0]
            conn.close()
            st.metric("Permit Records", permit_count)
            st.success("Active")
        else:
            st.markdown(
                "**Status:** Disabled  \n"
                "**Requires:** City permit portal scrapers  \n"
                "**Cost:** Free (public records)  \n"
                "**Enable:** Set `permit_pipeline: True` in config.py"
            )

with premium_col2:
    with st.container(border=True):
        st.markdown("**Fleet Aging Vision Engine**")
        st.caption("Uses Street View + AI vision to analyze truck/equipment condition at business addresses.")

        if config.LAYERS.get("fleet_aging") and config.GOOGLE_MAPS_API_KEY and config.ANTHROPIC_API_KEY:
            st.success("Active")
        else:
            missing = []
            if not config.GOOGLE_MAPS_API_KEY:
                missing.append("GOOGLE_MAPS_API_KEY ($7/1K images)")
            if not config.ANTHROPIC_API_KEY:
                missing.append("ANTHROPIC_API_KEY (~$0.02/analysis)")
            st.markdown(
                "**Status:** Disabled  \n"
                "**Requires:** {}  \n"
                "**Enable:** Add keys to config.py, set `fleet_aging: True`".format(
                    ", ".join(missing) if missing else "API keys configured"
                )
            )

# Google Places enhancement note
with st.container(border=True):
    st.markdown("**Google Places Enhancement** (Optional)")
    st.caption(
        "Add a GOOGLE_MAPS_API_KEY to enrich company data with Google Reviews "
        "in addition to Yelp. Improves Digital Ghost accuracy with dual-platform review data."
    )
    if config.GOOGLE_MAPS_API_KEY:
        st.success("Active — Google + Yelp reviews")
    else:
        st.markdown(
            "**Status:** Using Yelp only (free)  \n"
            "**Cost:** ~$17 per 1,000 Place Details requests  \n"
            "**Enable:** Add GOOGLE_MAPS_API_KEY to config.py"
        )
