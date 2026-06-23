from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from neodym_lead_discovery.models import LeadCandidate, QualifiedLead

_COMPANY_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company)\b\.?",
    re.IGNORECASE,
)


def normalize_domain(website: str | None) -> str | None:
    """Return a stable domain key for a website URL."""
    if not website:
        return None
    raw = website.strip().lower()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path.split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip("/") or None


def normalize_company_name(name: str) -> str:
    """Return a stable company-name key for duplicate detection."""
    cleaned = name.lower().strip()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = _COMPANY_SUFFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class LeadStorage:
    """SQLite persistence for local run state and lead data."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("DROP TABLE IF EXISTS enriched_companies")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT
                );

                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_name TEXT NOT NULL,
                    normalized_domain TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(normalized_name, normalized_domain)
                );

                CREATE TABLE IF NOT EXISTS candidate_website_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER NOT NULL UNIQUE,
                    company_name TEXT NOT NULL,
                    industry TEXT,
                    website TEXT,
                    page_count INTEGER NOT NULL CHECK(page_count >= 0),
                    facts_json TEXT NOT NULL CHECK(json_valid(facts_json)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_candidate_website_facts_candidate_id
                    ON candidate_website_facts(candidate_id);

                CREATE TABLE IF NOT EXISTS qualified_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    company TEXT NOT NULL,
                    website TEXT,
                    fit_score REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                """
            )

    def upsert_candidate(self, candidate: LeadCandidate) -> int:
        now = _now_iso()
        normalized_name = normalize_company_name(candidate.company_name)
        normalized_domain = normalize_domain(candidate.website)
        payload = candidate.model_dump_json()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM candidates
                WHERE normalized_name = ? AND normalized_domain IS ?
                """,
                (normalized_name, normalized_domain),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE candidates
                    SET payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (payload, now, existing["id"]),
                )
                return int(existing["id"])
            cursor = conn.execute(
                """
                INSERT INTO candidates (
                    normalized_name, normalized_domain, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized_name, normalized_domain, payload, now, now),
            )
            return int(cursor.lastrowid)

    def get_candidate(self, candidate_id: int) -> LeadCandidate | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            return None
        return LeadCandidate.model_validate_json(row["payload_json"])

    def count_candidates(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM candidates").fetchone()
        return int(row["count"])

    def list_candidates(self, limit: int | None = None) -> list[tuple[int, LeadCandidate]]:
        query = "SELECT id, payload_json FROM candidates ORDER BY id ASC"
        params: tuple[int, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            (int(row["id"]), LeadCandidate.model_validate_json(row["payload_json"]))
            for row in rows
        ]

    def save_candidate_website_facts(
        self,
        candidate_id: int,
        candidate: LeadCandidate,
        facts: Mapping[str, Any],
        page_count: int,
    ) -> int:
        """Persist only structured Reader facts for a candidate website.

        The raw website Markdown/content is intentionally not accepted by this method and
        is never stored in SQLite. The candidate snapshot columns make the fact row easy
        to inspect while candidate_id remains the canonical join back to candidates.
        """
        now = _now_iso()
        facts_json = json.dumps(dict(facts), sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO candidate_website_facts (
                    candidate_id, company_name, industry, website,
                    page_count, facts_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    company_name = excluded.company_name,
                    industry = excluded.industry,
                    website = excluded.website,
                    page_count = excluded.page_count,
                    facts_json = excluded.facts_json,
                    updated_at = excluded.updated_at
                """,
                (
                    candidate_id,
                    candidate.company_name,
                    candidate.industry,
                    candidate.website,
                    page_count,
                    facts_json,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM candidate_website_facts WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            return int(row["id"])

    def get_candidate_website_facts(self, candidate_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, candidate_id, company_name, industry, website,
                       page_count, facts_json, created_at, updated_at
                FROM candidate_website_facts
                WHERE candidate_id = ?
                """,
                (candidate_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "candidate_id": int(row["candidate_id"]),
            "company_name": row["company_name"],
            "industry": row["industry"],
            "website": row["website"],
            "page_count": int(row["page_count"]),
            "facts": json.loads(row["facts_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def start_run(self, stage: str, metadata: Mapping[str, Any] | None = None) -> int:
        now = _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (stage, status, metadata_json, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (stage, "running", json.dumps(dict(metadata or {})), now),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, metadata_json = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, json.dumps(dict(metadata or {})), _now_iso(), run_id),
            )

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "stage": row["stage"],
            "status": row["status"],
            "metadata": json.loads(row["metadata_json"]),
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    def save_qualified_lead(self, lead: QualifiedLead, run_id: int | None = None) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO qualified_leads (
                    run_id, company, website, fit_score, payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    lead.company,
                    lead.website,
                    lead.fit_score,
                    lead.model_dump_json(),
                    _now_iso(),
                ),
            )
            return int(cursor.lastrowid)

    def list_qualified_leads(self) -> list[QualifiedLead]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM qualified_leads ORDER BY fit_score DESC, id ASC"
            ).fetchall()
        return [QualifiedLead.model_validate_json(row["payload_json"]) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
