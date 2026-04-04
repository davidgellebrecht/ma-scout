"""
layers/website_decay.py — Strategy: Website Decay Detection

Checks if a company's website domain is expired, parked, or hasn't
been updated in years.  Uses two free data sources:

    1. WHOIS lookup (python-whois, free) — domain registration and expiry
    2. Wayback Machine CDX API (free) — last time the site was crawled

A company that had a website but let it expire is a strong signal:
they invested in their business at some point but stopped caring.
Combined with an active CSLB license, it means the owner is coasting
toward retirement.

Signals:
    - Domain expired or about to expire
    - Website not updated (Wayback) in 2+ years
    - Domain exists but no recent crawls (site is "dark")
    - No website at all (combined with other signals)

Score components:
    - domain_expired_score:  1.0 if expired, 0.5 if expiring soon
    - wayback_stale_score:   how long since last Wayback snapshot
    - no_site_score:         1.0 if no website listed at all
"""

from __future__ import annotations

from datetime import date, datetime

import requests

import config
from layers.base import BaseLayer


class WebsiteDecayLayer(BaseLayer):
    name = "website_decay"
    label = "Website Decay"
    paid = False

    def run(self, company: dict) -> dict:
        """Check a company's website for signs of decay or abandonment."""

        website = company.get("website", "")

        # No website at all — strong signal when combined with active license
        if not website:
            has_license = bool(company.get("license_number"))
            if has_license:
                return {
                    "layer": self.name,
                    "label": self.label,
                    "signal": True,
                    "score": 0.6,
                    "detail": "No website listed despite active CSLB license",
                    "data": {"has_website": False, "has_license": has_license},
                    "paid": self.paid,
                }
            else:
                return self._empty_result("No website and no license data")

        # Clean the domain
        domain = website.strip().lower()
        for prefix in ("http://", "https://", "www."):
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        domain = domain.rstrip("/").split("/")[0]

        if not domain or "." not in domain:
            return self._empty_result("Invalid website: {}".format(website))

        # ── Check Wayback Machine CDX API (free, no account) ─────────────
        wayback_last = self._check_wayback(domain)
        if wayback_last:
            days_since_snapshot = (date.today() - wayback_last).days
        else:
            days_since_snapshot = 9999  # never crawled = very stale

        wayback_stale = days_since_snapshot > (config.WEBSITE_DECAY_MIN_YEARS * 365)
        wayback_score = self._clamp((days_since_snapshot - 365) / (365 * 4)) if wayback_stale else 0.0

        # ── Check WHOIS domain expiry (free) ─────────────────────────────
        domain_expired = False
        domain_expiry_days = None
        if config.WEBSITE_DECAY_CHECK_WHOIS:
            expiry_date = self._check_whois(domain)
            if expiry_date:
                domain_expiry_days = (expiry_date - date.today()).days
                domain_expired = domain_expiry_days <= 0

        domain_expired_score = 1.0 if domain_expired else (
            0.5 if domain_expiry_days is not None and domain_expiry_days < 90 else 0.0
        )

        # ── Composite ────────────────────────────────────────────────────
        composite = (
            0.50 * wayback_score
            + 0.50 * domain_expired_score
        )
        composite = self._clamp(composite)

        # ── Signal fires? ────────────────────────────────────────────────
        signal = wayback_stale or domain_expired

        if signal:
            parts = []
            if domain_expired:
                parts.append("domain expired")
            elif domain_expiry_days is not None and domain_expiry_days < 90:
                parts.append("domain expires in {} days".format(domain_expiry_days))
            if wayback_stale:
                if wayback_last:
                    parts.append("last crawled {}".format(wayback_last.isoformat()))
                else:
                    parts.append("never crawled by Wayback Machine")
            detail = "Website decay: {} ({})".format(domain, ", ".join(parts))
        else:
            detail = "Website appears active: {}".format(domain)

        return {
            "layer": self.name,
            "label": self.label,
            "signal": signal,
            "score": composite,
            "detail": detail,
            "data": {
                "domain": domain,
                "wayback_last_snapshot": str(wayback_last) if wayback_last else None,
                "days_since_snapshot": days_since_snapshot,
                "domain_expired": domain_expired,
                "domain_expiry_days": domain_expiry_days,
            },
            "paid": self.paid,
        }

    def _check_wayback(self, domain: str) -> date | None:
        """Query the Wayback Machine CDX API for the most recent snapshot."""
        try:
            url = "http://web.archive.org/cdx/search/cdx"
            params = {
                "url": domain,
                "output": "json",
                "limit": "1",
                "fl": "timestamp",
                "sort": "reverse",
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if len(data) > 1:  # first row is header
                    ts = data[1][0]  # timestamp like "20240315123456"
                    return datetime.strptime(ts[:8], "%Y%m%d").date()
        except Exception:
            pass
        return None

    def _check_whois(self, domain: str) -> date | None:
        """Check WHOIS for domain expiry date."""
        try:
            import whois
            w = whois.whois(domain)
            if w.expiration_date:
                exp = w.expiration_date
                if isinstance(exp, list):
                    exp = exp[0]
                if isinstance(exp, datetime):
                    return exp.date()
                elif isinstance(exp, date):
                    return exp
        except Exception:
            pass
        return None
