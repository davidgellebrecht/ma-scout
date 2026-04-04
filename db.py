"""
db.py — SQLite Database Layer

This module manages M&A Scout's persistent storage.  Unlike Parcel Scout
which writes fresh timestamped files each run, M&A Scout tracks companies
over time so we don't re-scrape expensive APIs unnecessarily.

The database file lives at data/mascout.db (configurable in config.py).
SQLite needs no server — it's a single file that Python can read/write
directly, making it perfect for a Streamlit app.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime
from typing import Any, Optional

import config
from models import Company, CompanyWithSignals, Signal


# ─── Connection ──────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """
    Open (or create) the SQLite database and ensure all tables exist.
    Returns a connection with row_factory set so rows behave like dicts.
    """
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection):
    """Create all tables if they don't already exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id                    TEXT PRIMARY KEY,
            business_name         TEXT NOT NULL,
            dba_name              TEXT,
            owner_name            TEXT,
            license_number        TEXT UNIQUE,
            license_type          TEXT,
            license_status        TEXT,
            license_issue_date    TEXT,
            license_expiry_date   TEXT,
            license_class         TEXT,
            address               TEXT,
            city                  TEXT,
            zip_code              TEXT,
            county                TEXT,
            lat                   REAL,
            lon                   REAL,
            phone                 TEXT,
            website               TEXT,
            google_place_id       TEXT,
            yelp_business_id      TEXT,
            employee_count_est    INTEGER,
            google_rating         REAL,
            google_review_count   INTEGER,
            google_last_review_date TEXT,
            yelp_rating           REAL,
            yelp_review_count     INTEGER,
            yelp_last_review_date TEXT,
            owner_response_rate   REAL,
            first_seen            TEXT NOT NULL,
            last_updated          TEXT NOT NULL,
            source                TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id  TEXT NOT NULL REFERENCES companies(id),
            layer_name  TEXT NOT NULL,
            signal      BOOLEAN NOT NULL,
            score       REAL,
            detail      TEXT,
            data_json   TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS street_view_images (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id   TEXT NOT NULL REFERENCES companies(id),
            image_path   TEXT NOT NULL,
            captured_at  TEXT NOT NULL,
            analysis_json TEXT
        );

        CREATE TABLE IF NOT EXISTS permit_records (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id          TEXT REFERENCES companies(id),
            permit_number       TEXT,
            city                TEXT NOT NULL,
            project_address     TEXT,
            project_description TEXT,
            contractor_name     TEXT,
            permit_date         TEXT,
            estimated_value     REAL,
            status              TEXT,
            source_url          TEXT,
            scraped_at          TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_companies_city
            ON companies(city);
        CREATE INDEX IF NOT EXISTS idx_companies_license
            ON companies(license_number);
        CREATE INDEX IF NOT EXISTS idx_signals_company
            ON signals(company_id);
        CREATE INDEX IF NOT EXISTS idx_signals_layer
            ON signals(layer_name);
        CREATE INDEX IF NOT EXISTS idx_permits_contractor
            ON permit_records(contractor_name);
    """)
    conn.commit()


# ─── Company CRUD ────────────────────────────────────────────────────────────

def upsert_company(conn: sqlite3.Connection, company: Company):
    """
    Insert a new company or update it if one with the same id already exists.
    'Upsert' = 'update + insert' — a common database pattern.
    """
    if not company.id:
        company.generate_id()
    company.last_updated = datetime.now()

    conn.execute("""
        INSERT INTO companies (
            id, business_name, dba_name, owner_name,
            license_number, license_type, license_status,
            license_issue_date, license_expiry_date, license_class,
            address, city, zip_code, county, lat, lon,
            phone, website, google_place_id, yelp_business_id,
            employee_count_est,
            google_rating, google_review_count, google_last_review_date,
            yelp_rating, yelp_review_count, yelp_last_review_date,
            owner_response_rate,
            first_seen, last_updated, source
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(id) DO UPDATE SET
            business_name       = excluded.business_name,
            dba_name            = COALESCE(excluded.dba_name, companies.dba_name),
            owner_name          = COALESCE(excluded.owner_name, companies.owner_name),
            license_number      = COALESCE(excluded.license_number, companies.license_number),
            license_type        = COALESCE(excluded.license_type, companies.license_type),
            license_status      = COALESCE(excluded.license_status, companies.license_status),
            license_issue_date  = COALESCE(excluded.license_issue_date, companies.license_issue_date),
            license_expiry_date = COALESCE(excluded.license_expiry_date, companies.license_expiry_date),
            license_class       = COALESCE(excluded.license_class, companies.license_class),
            address             = COALESCE(excluded.address, companies.address),
            city                = COALESCE(excluded.city, companies.city),
            zip_code            = COALESCE(excluded.zip_code, companies.zip_code),
            county              = COALESCE(excluded.county, companies.county),
            lat                 = COALESCE(excluded.lat, companies.lat),
            lon                 = COALESCE(excluded.lon, companies.lon),
            phone               = COALESCE(excluded.phone, companies.phone),
            website             = COALESCE(excluded.website, companies.website),
            google_place_id     = COALESCE(excluded.google_place_id, companies.google_place_id),
            yelp_business_id    = COALESCE(excluded.yelp_business_id, companies.yelp_business_id),
            employee_count_est  = COALESCE(excluded.employee_count_est, companies.employee_count_est),
            google_rating       = COALESCE(excluded.google_rating, companies.google_rating),
            google_review_count = COALESCE(excluded.google_review_count, companies.google_review_count),
            google_last_review_date = COALESCE(excluded.google_last_review_date, companies.google_last_review_date),
            yelp_rating         = COALESCE(excluded.yelp_rating, companies.yelp_rating),
            yelp_review_count   = COALESCE(excluded.yelp_review_count, companies.yelp_review_count),
            yelp_last_review_date = COALESCE(excluded.yelp_last_review_date, companies.yelp_last_review_date),
            owner_response_rate = COALESCE(excluded.owner_response_rate, companies.owner_response_rate),
            last_updated        = excluded.last_updated,
            source              = excluded.source
    """, (
        company.id, company.business_name, company.dba_name, company.owner_name,
        company.license_number, company.license_type, company.license_status,
        _date_str(company.license_issue_date), _date_str(company.license_expiry_date),
        company.license_class,
        company.address, company.city, company.zip_code, company.county,
        company.lat, company.lon,
        company.phone, company.website, company.google_place_id, company.yelp_business_id,
        company.employee_count_est,
        company.google_rating, company.google_review_count,
        _date_str(company.google_last_review_date),
        company.yelp_rating, company.yelp_review_count,
        _date_str(company.yelp_last_review_date),
        company.owner_response_rate,
        company.first_seen.isoformat(), company.last_updated.isoformat(),
        company.source,
    ))
    conn.commit()


def get_companies(conn: sqlite3.Connection, **filters) -> list[Company]:
    """
    Retrieve companies from the database, optionally filtered.
    Supported filters: city, source, license_status.
    """
    query = "SELECT * FROM companies WHERE 1=1"
    params: list[Any] = []
    for key in ("city", "source", "license_status"):
        if key in filters and filters[key]:
            query += f" AND {key} = ?"
            params.append(filters[key])
    query += " ORDER BY last_updated DESC"

    rows = conn.execute(query, params).fetchall()
    return [_row_to_company(row) for row in rows]


def get_company_count(conn: sqlite3.Connection) -> int:
    """Return total number of companies in the database."""
    return conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]


# ─── Signal CRUD ─────────────────────────────────────────────────────────────

def insert_signal(conn: sqlite3.Connection, signal: Signal):
    """Insert a new signal record."""
    conn.execute("""
        INSERT INTO signals (company_id, layer_name, signal, score, detail, data_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        signal.company_id, signal.layer_name, signal.signal,
        signal.score, signal.detail,
        json.dumps(signal.data, default=str),
        signal.created_at.isoformat(),
    ))
    conn.commit()


def get_latest_signals(conn: sqlite3.Connection, company_id: str) -> list[Signal]:
    """Get the most recent signal per layer for a given company."""
    rows = conn.execute("""
        SELECT s.* FROM signals s
        INNER JOIN (
            SELECT company_id, layer_name, MAX(created_at) as max_created
            FROM signals
            WHERE company_id = ?
            GROUP BY company_id, layer_name
        ) latest ON s.company_id = latest.company_id
                 AND s.layer_name = latest.layer_name
                 AND s.created_at = latest.max_created
    """, (company_id,)).fetchall()

    return [_row_to_signal(row) for row in rows]


# ─── Combined Queries ────────────────────────────────────────────────────────

def get_ranked_companies(conn: sqlite3.Connection) -> list[CompanyWithSignals]:
    """
    Load all companies with their latest signals and compute
    opportunity scores.  Returns the list sorted by score, best first.
    """
    companies = get_companies(conn)
    results: list[CompanyWithSignals] = []

    # Count only enabled layers for scoring (not hardcoded to 4)
    enabled_count = sum(1 for v in config.LAYERS.values() if v)
    enabled_count = max(enabled_count, 1)  # avoid division by zero

    for company in companies:
        signals = get_latest_signals(conn, company.id)
        fired = sum(1 for s in signals if s.signal)
        score = round((fired / enabled_count) * 100, 1)

        results.append(CompanyWithSignals(
            company=company,
            signals=signals,
            opportunity_score=score,
            signals_fired=fired,
            signals_total=enabled_count,
        ))

    results.sort(key=lambda r: r.opportunity_score, reverse=True)
    return results


# ─── Permit Records ──────────────────────────────────────────────────────────

def insert_permit(conn: sqlite3.Connection, permit: dict):
    """Insert a permit record."""
    conn.execute("""
        INSERT INTO permit_records (
            company_id, permit_number, city, project_address,
            project_description, contractor_name, permit_date,
            estimated_value, status, source_url, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        permit.get("company_id"),
        permit.get("permit_number"),
        permit["city"],
        permit.get("project_address"),
        permit.get("project_description"),
        permit.get("contractor_name"),
        permit.get("permit_date"),
        permit.get("estimated_value"),
        permit.get("status"),
        permit.get("source_url"),
        datetime.now().isoformat(),
    ))
    conn.commit()


def get_permits_for_company(conn: sqlite3.Connection, company_id: str) -> list[dict]:
    """Get all permit records linked to a company."""
    rows = conn.execute(
        "SELECT * FROM permit_records WHERE company_id = ? ORDER BY permit_date DESC",
        (company_id,)
    ).fetchall()
    return [dict(row) for row in rows]


# ─── Street View Images ─────────────────────────────────────────────────────

def insert_street_view_image(conn: sqlite3.Connection, company_id: str,
                              image_path: str, analysis: dict | None = None):
    """Record a captured Street View image and optional vision analysis."""
    conn.execute("""
        INSERT INTO street_view_images (company_id, image_path, captured_at, analysis_json)
        VALUES (?, ?, ?, ?)
    """, (
        company_id, image_path, datetime.now().isoformat(),
        json.dumps(analysis, default=str) if analysis else None,
    ))
    conn.commit()


def get_street_view_analysis(conn: sqlite3.Connection, company_id: str) -> dict | None:
    """Get the most recent Street View analysis for a company."""
    row = conn.execute("""
        SELECT analysis_json FROM street_view_images
        WHERE company_id = ? AND analysis_json IS NOT NULL
        ORDER BY captured_at DESC LIMIT 1
    """, (company_id,)).fetchone()
    if row and row["analysis_json"]:
        return json.loads(row["analysis_json"])
    return None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _date_str(d: date | None) -> str | None:
    """Convert a date to ISO string for SQLite storage, or None."""
    return d.isoformat() if d else None


def _row_to_company(row: sqlite3.Row) -> Company:
    """Convert a SQLite row to a Company model."""
    d = dict(row)
    # Convert ISO date strings back to date/datetime objects
    for date_field in ("license_issue_date", "license_expiry_date",
                       "google_last_review_date", "yelp_last_review_date"):
        if d.get(date_field):
            d[date_field] = date.fromisoformat(d[date_field])
    for dt_field in ("first_seen", "last_updated"):
        if d.get(dt_field):
            d[dt_field] = datetime.fromisoformat(d[dt_field])
    return Company(**d)


def _row_to_signal(row: sqlite3.Row) -> Signal:
    """Convert a SQLite row to a Signal model."""
    d = dict(row)
    d["data"] = json.loads(d.pop("data_json", "{}") or "{}")
    d["created_at"] = datetime.fromisoformat(d["created_at"])
    d.pop("id", None)  # autoincrement PK, not part of the Pydantic model
    return Signal(**d)
