import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta


DB_PATH_DEFAULT = os.environ.get("LEGAL_EAGLE_DB") or os.path.join(os.path.dirname(__file__), "config.db")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Open a sqlite3 connection with foreign_keys enabled and rows as dict-like objects.
    """
    path = db_path or DB_PATH_DEFAULT
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        # Let readers/writers wait for a held lock instead of erroring instantly with
        # "database is locked" (the run worker writes run_logs rapidly while the Run page
        # and SSE stream read concurrently). Prevents transient 500s during a live run.
        conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def create_schema_if_needed(conn: sqlite3.Connection) -> None:
    """
    Create all tables if they do not exist. This schema is profile-scoped for multi-country/LoB.
    """
    with conn:
        # Profiles
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY,
                country_code TEXT NOT NULL,
                lob TEXT NOT NULL,
                name TEXT,
                language TEXT DEFAULT 'en',
                active INTEGER DEFAULT 1,
                schedule_day TEXT,
                UNIQUE(country_code, lob, name)
            );
            """
        )

        # Attempt to add schedule_day column for existing databases
        try:
            conn.execute("ALTER TABLE profiles ADD COLUMN schedule_day TEXT")
        except Exception:
            pass
        # Add profile-level date_scope (lookback window) — replaces per-source date_scope
        try:
            conn.execute("ALTER TABLE profiles ADD COLUMN date_scope TEXT DEFAULT 'all'")
        except Exception:
            pass

        # v3.8: retire the legacy 'delta'/'all'/'force_full' scope (unbounded first run) —
        # it was misleading (incremental fetch is always applied regardless). Migrate any
        # such profile to the bounded 30-day initial-run window. Idempotent.
        try:
            conn.execute(
                "UPDATE profiles SET date_scope='last_30_days' "
                "WHERE date_scope IN ('delta','all','force_full') OR date_scope IS NULL OR date_scope=''"
            )
        except Exception:
            pass

        # Settings (per profile key/value)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                UNIQUE(profile_id, key),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )

        # Feeds/accounts/urls/email (per profile)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rss_feeds (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                max_lookback_days INTEGER DEFAULT 7,
                last_fetch_date TEXT,
                UNIQUE(profile_id, url),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )
        # Add max_lookback_days and last_fetch_date to existing rss_feeds tables
        try:
            conn.execute("ALTER TABLE rss_feeds ADD COLUMN max_lookback_days INTEGER DEFAULT 7")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE rss_feeds ADD COLUMN last_fetch_date TEXT")
        except Exception:
            pass

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tweet_accounts (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                handle TEXT NOT NULL,
                max_lookback_days INTEGER DEFAULT 7,
                last_fetch_date TEXT,
                UNIQUE(profile_id, handle),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )
        # Add max_lookback_days and last_fetch_date to existing tweet_accounts tables
        try:
            conn.execute("ALTER TABLE tweet_accounts ADD COLUMN max_lookback_days INTEGER DEFAULT 7")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE tweet_accounts ADD COLUMN last_fetch_date TEXT")
        except Exception:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_urls (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                UNIQUE(profile_id, url),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snap_urls (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                UNIQUE(profile_id, url),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_receivers (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                translation_lang TEXT DEFAULT 'en',
                UNIQUE(profile_id, email),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )
        # Attempt to add translation_lang column for existing databases
        try:
            conn.execute("ALTER TABLE email_receivers ADD COLUMN translation_lang TEXT DEFAULT 'en'")
        except Exception:
            pass

        # Glossary (normalized) per profile
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS glossary_terms (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                term TEXT NOT NULL,
                lang TEXT DEFAULT 'en',
                category TEXT,
                product TEXT,
                weight REAL DEFAULT 1.0,
                notes TEXT,
                UNIQUE(profile_id, term, lang, product),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS glossary_synonyms (
                id INTEGER PRIMARY KEY,
                term_id INTEGER NOT NULL,
                synonym TEXT NOT NULL,
                UNIQUE(term_id, synonym),
                FOREIGN KEY(term_id) REFERENCES glossary_terms(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS glossary_patterns (
                id INTEGER PRIMARY KEY,
                term_id INTEGER NOT NULL,
                regex TEXT NOT NULL,
                FOREIGN KEY(term_id) REFERENCES glossary_terms(id) ON DELETE CASCADE
            );
            """
        )
        # Glossary Labels — canonical parent grouping. A label's `name` is what the matcher
        # stamps as topic_label and what the announcement topic bar displays; many member
        # terms (multilingual) live under one label.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS glossary_labels (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(profile_id, name),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )
        # Link each glossary term to its label (nullable — unlabeled terms match on themselves).
        try:
            conn.execute("ALTER TABLE glossary_terms ADD COLUMN label_id INTEGER")
        except Exception:
            pass

        # Weekly baseline storage for semantic dedup/update detection
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                source_type TEXT NOT NULL,          -- rss | tweet | crawl | snap
                source_id TEXT,                     -- rss: guid, tweet: tweet_id
                url TEXT,
                domain TEXT,
                title TEXT,
                content TEXT,
                published_at TEXT,                  -- ISO timestamp if available
                first_seen_at TEXT NOT NULL,        -- ISO now() on insert
                last_seen_at TEXT NOT NULL,         -- ISO now() updated on repeat/update
                hash_signature TEXT NOT NULL,       -- normalized text hash for quick fuzzy match
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_items_profile_first ON news_items(profile_id, first_seen_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_items_profile_last ON news_items(profile_id, last_seen_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_items_profile_url ON news_items(profile_id, url)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_items_profile_source ON news_items(profile_id, source_type, source_id)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uniq_news_items_sig ON news_items(profile_id, source_type, hash_signature)"
        )
        conn.execute("DROP INDEX IF EXISTS uniq_news_items_sourceid")
        conn.execute("DROP INDEX IF EXISTS uniq_news_items_url")

        # Unified URL sources with per-URL crawl mode and optional sample_link
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS url_sources (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('auto','force_static','force_dynamic')),
                sample_link TEXT,
                read_more_label TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(profile_id, url),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )


        # Admin audit log
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER,
                entity TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL
            );
            """
        )

        # Filtered news for manual review and glossary enhancement
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS filtered_news (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                run_id INTEGER,
                source_type TEXT,                   -- rss | tweet | crawl | snap
                url TEXT,
                title TEXT,
                content TEXT,
                filter_reason TEXT,                 -- domain_country | glossary | llm_classification
                relevance_score INTEGER,            -- NULL until reviewed, 1-5 scale
                reviewed_at TEXT,                   -- ISO timestamp when scored
                published_at TEXT,                  -- Original publication date from source
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );
            """
        )
        # Attempt to add published_at column for existing databases
        try:
            conn.execute("ALTER TABLE filtered_news ADD COLUMN published_at TEXT")
        except Exception:
            pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_filtered_news_profile ON filtered_news(profile_id, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_filtered_news_reviewed ON filtered_news(profile_id, relevance_score)"
        )

        # Run executions (history + status)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                status TEXT NOT NULL,                  -- Queued | Running | Success | Failed | Canceled
                started_at TEXT,
                finished_at TEXT,
                duration_ms INTEGER,
                rss_count INTEGER DEFAULT 0,
                tweet_count INTEGER DEFAULT 0,
                url_count INTEGER DEFAULT 0,
                filtered_count INTEGER DEFAULT 0,
                grouped_count INTEGER DEFAULT 0,
                email_status TEXT,                     -- Sent | Failed
                cancel_requested INTEGER DEFAULT 0,    -- 1 when cancel requested
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )
        # Attempt to add origin column for existing databases
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN origin TEXT DEFAULT 'manual'")
        except Exception:
            pass
        # F3 (v3.1): structured failure info surfaced in the run status UI
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN error_step TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN error_message TEXT")
        except Exception:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_logs (
                id INTEGER PRIMARY KEY,
                run_id INTEGER NOT NULL,
                ts TEXT NOT NULL,                      -- ISO timestamp
                level TEXT DEFAULT 'INFO',             -- INFO | WARN | ERROR
                line TEXT NOT NULL,
                seq INTEGER NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_logs_run_seq ON run_logs(run_id, seq)")
        # Attempt to add read_more_label column for existing databases (idempotent)
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN read_more_label TEXT")
        except Exception:
            pass
        # Add crawl_version column for v1/v2 runner selection
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN crawl_version TEXT")
        except Exception:
            pass
        # Default existing NULL/empty crawl_version values to 'v1'
        try:
            conn.execute("UPDATE url_sources SET crawl_version = 'v1' WHERE crawl_version IS NULL OR crawl_version = ''")
        except Exception:
            pass
        # Add url_date_template column for Mechanism B (URL-per-day generation)
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN url_date_template TEXT")
        except Exception:
            pass

        # Authorities — legislative bodies per profile (v3.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS authorities (
                id INTEGER PRIMARY KEY,
                profile_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                aliases TEXT,
                UNIQUE(profile_id, name),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
        """)

        # rss_feeds source attribution columns (v3.0)
        try:
            conn.execute("ALTER TABLE rss_feeds ADD COLUMN publisher_name TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE rss_feeds ADD COLUMN authority_id INTEGER")
        except Exception:
            pass

        # url_sources source attribution columns (v3.0)
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN publisher_name TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE url_sources ADD COLUMN authority_id INTEGER")
        except Exception:
            pass

        # url_sources recursive-crawl + delta columns (ensure present on fresh schema;
        # list_url_sources SELECTs these, so they must exist even with no rows).
        for _col, _decl in (
            ("max_depth", "INTEGER"),
            ("allowed_domains", "TEXT"),
            ("path_filter", "TEXT"),
            ("max_results", "INTEGER"),
            ("date_scope", "TEXT DEFAULT 'all'"),
            ("last_successful_fetch", "TEXT"),
            # Source Simulator columns (v3.1, F9). Old mode/crawl columns are left in
            # place (SQLite can't easily drop) but ignored by simulated sources.
            ("simulation_status", "TEXT DEFAULT 'pending'"),
            ("simulated_at", "TEXT"),
            ("container_selector", "TEXT"),
            ("field_selectors", "TEXT"),
            ("read_more_selector", "TEXT"),
            ("pagination_type", "TEXT"),
            ("pagination_selector", "TEXT"),
            ("depth_level", "INTEGER"),
            ("requires_js", "INTEGER DEFAULT 0"),
        ):
            try:
                conn.execute(f"ALTER TABLE url_sources ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # Item-level source attribution columns (v3.1)
        # Stamped by the ATTRIBUTE stage (agents/authority_attributor.py).
        # publisher: display name of the source; authority_id: FK to authorities;
        # authority_status: 'configured' (from feed config) | 'inferred' (AI, v3.2+) | 'unknown'
        # dedup_status: 'new' | 'update' | 'duplicate' — set by compare_news (F7: duplicates
        # are preserved, never dropped, so they stay queryable/visible in Review).
        for _tbl in ("news_items", "filtered_news"):
            for _col, _type in (
                ("publisher", "TEXT"),
                ("authority_id", "INTEGER"),
                ("authority_status", "TEXT"),
                ("dedup_status", "TEXT"),
            ):
                try:
                    conn.execute(f"ALTER TABLE {_tbl} ADD COLUMN {_col} {_type}")
                except Exception:
                    pass

        # Ranking columns on news_items (v3.2)
        # significance_rank: 0=duplicate, 1-5 scored by news_ranker
        # rank_tier: 'tier1' (deterministic) | 'tier2' (AI) | 'duplicate'
        # rank_reasoning: one-line rationale from ranker
        # repetition_status: 'new' | 'update' | 'repeated' | 'duplicate'  (the Status classification)
        # repetition_count: times same entity fingerprint seen across runs
        # Migration: rename the legacy repetition_tag column in place (SQLite 3.25+).
        try:
            _cols = [r[1] for r in conn.execute("PRAGMA table_info(news_items)").fetchall()]
            if "repetition_tag" in _cols and "repetition_status" not in _cols:
                conn.execute("ALTER TABLE news_items RENAME COLUMN repetition_tag TO repetition_status")
        except Exception:
            pass
        for _col, _decl in (
            ("significance_rank", "INTEGER DEFAULT 0"),
            ("rank_tier", "TEXT"),
            ("rank_reasoning", "TEXT"),
            ("repetition_status", "TEXT"),
            ("repetition_count", "INTEGER DEFAULT 0"),
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # Ranking engine tables (v3.2)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ranking_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                signal_type TEXT,
                pattern TEXT,
                min_rank INTEGER,
                confidence REAL,
                created_from TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ranking_grounding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                rank INTEGER,
                summary TEXT,
                source_item_id INTEGER
            );
            """
        )

        # Tagging + email gate columns (v3.3)
        # topic_label: JSON array of glossary terms matching item text
        # email_eligible: 1 if significance_rank >= threshold and not duplicate
        # email_sent: 1 once item has been included in a sent digest
        for _col, _decl in (
            ("topic_label", "TEXT"),
            ("email_eligible", "INTEGER NOT NULL DEFAULT 0"),
            ("email_sent", "INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # Human override columns (v3.4) — written by confirm-challenge route
        for _col, _decl in (
            ("human_rank_override", "INTEGER"),
            ("human_override_reason", "TEXT"),
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # Glossary gap flag (v3.5) — set by Tag stage when significance_rank >= 3
        # AND topic_label == '["General"]' (rank-significant item with no glossary match)
        for _col, _decl in (
            ("glossary_gap", "INTEGER NOT NULL DEFAULT 0"),
            # Effective date (v3.8) — the date a law/policy/rate comes into force, extracted
            # by the AI ranker from the article body (ISO YYYY-MM-DD). NULL when none stated.
            ("effective_date", "TEXT"),
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # Announcements table (v3.4) — one row per AI-detected announcement per run
        # (renamed from news_aspects in v3.4)
        try:
            conn.execute("ALTER TABLE news_aspects RENAME TO news_announcements")
        except Exception:
            pass  # already renamed or doesn't exist
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_announcements (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id             INTEGER NOT NULL REFERENCES runs(id),
                topic_label        TEXT NOT NULL,
                title              TEXT NOT NULL,
                announcement_md    TEXT NOT NULL,
                impact_analysis_md TEXT,
                first_published    TEXT,
                source_links_json  TEXT NOT NULL,
                item_ids_json      TEXT NOT NULL,
                created_at         TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        # v3.6: close-the-loop columns on news_announcements
        # jira_legal_change: JIRA Legal Change key the LPM links after publishing to RCM
        # status: draft (default) -> done (once JIRA linked + marked done)
        for _c, _d in (("jira_legal_change", "TEXT"), ("status", "TEXT")):
            try:
                conn.execute(f"ALTER TABLE news_announcements ADD COLUMN {_c} {_d}")
            except Exception:
                pass
        # v3.6: AI-filled RCM template content (JSON string), generated once on first Preview click
        try:
            conn.execute("ALTER TABLE news_announcements ADD COLUMN announcement_rcm_json TEXT")
        except Exception:
            pass

        # v3.13: L2 deep-fetch + grouping state machine columns on news_items
        # l2_summary: 2-3 sentence factual summary of the full article (L2 deep fetch)
        # l2_fetched_at: cache marker — skip re-fetch when already populated
        # act_ref: law/act/gazette reference (e.g. "7555 Sayılı...") — clustering key.
        #          Primary source L2 fetch; best-effort earlier from glossary_match. NULL when none.
        # announce_state: pending (new/dirty) -> assigned (titled+placed) -> excluded (below threshold)
        # announcement_id: persistent membership FK into news_announcements
        # english_title: AI-generated English title — the clustering fingerprint
        # added_after_publish: 1 when the item joined a frozen (done) announcement post-publication
        for _col, _decl in (
            ("l2_summary", "TEXT"),
            ("l2_fetched_at", "TEXT"),
            ("act_ref", "TEXT"),
            ("law_primary", "TEXT"),
            ("law_secondary", "TEXT"),
            ("law_reference", "TEXT"),
            ("announce_state", "TEXT"),
            ("announcement_id", "INTEGER"),
            ("english_title", "TEXT"),
            ("added_after_publish", "INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # v3.13: announcements become profile-scoped + persistent (no longer delete-regenerate
        # per run). profile_id added so announcements accumulate and carry a draft->done lifecycle.
        try:
            conn.execute("ALTER TABLE news_announcements ADD COLUMN profile_id INTEGER")
        except Exception:
            pass

        # v3.13: RCM reference titles cache — per-profile naming-convention examples pulled
        # offline from LOKA (scope=regulations). Used to ground announcement title generation.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rcm_reference_titles (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id       INTEGER NOT NULL,
                jira_key         TEXT,
                regulation_title TEXT NOT NULL,
                country          TEXT,
                effective_date   TEXT,
                synced_at        TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uniq_rcm_ref "
                "ON rcm_reference_titles (profile_id, jira_key)"
            )
        except Exception:
            pass

        # v3.16: Law Reference registry — per-profile canonical law catalog. A resolved
        # law_id is the primary cross-language grouping/dedup identity (act_ref stays a
        # fallback). Gazette/Presidential-Decision/circular numbers are NOT laws — they
        # remain news-level in news_items.law_reference, never here.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS law_refs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id     INTEGER NOT NULL,
                name_en        TEXT NOT NULL,
                name_native    TEXT,
                law_number     TEXT,
                law_year       TEXT,
                authority_id   INTEGER,
                effective_date TEXT,
                status         TEXT,
                source_url     TEXT,
                key_articles   TEXT,
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_law_refs_profile ON law_refs(profile_id)")

        # v3.16: news_items law-identity columns.
        #   law_id: FK into law_refs (resolved registered law) — primary grouping identity
        #   law_ref_status: 'registered' | 'suggested' | NULL
        #   cited_article: specific article/provision cited (metadata; does NOT split groups)
        for _col, _decl in (
            ("law_id", "INTEGER"),
            ("law_ref_status", "TEXT"),
            ("cited_article", "TEXT"),
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # v3.17: RCM Match — per-item proposed RCM title + tracked/net-new status.
        for _col, _decl in (
            ("proposed_rcm_title", "TEXT"),
            ("rcm_match_status", "TEXT"),   # 'tracked' | 'net-new' | NULL
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # v3.18: Impact gate — semantic signals consumed by the deterministic Rank.
        for _col, _decl in (
            ("operational_impact", "INTEGER"),          # 0-3 payroll operational impact
            ("regulatory_change_confirmed", "INTEGER"), # 0/1
            ("preparation_required", "INTEGER"),        # 0/1
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # v3.19: Timing + Rank fusion outputs.
        for _col, _decl in (
            ("timing_class", "TEXT"),       # immediate|upcoming|future|past|draft|none
            ("timing_signal", "INTEGER"),   # 0-2 numeric for Rank
            ("rank_score", "INTEGER"),
            ("grounding_strength", "INTEGER"),
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass

        # v3.25/v3.26/v3.31: structured L2 outputs.
        for _col, _decl in (
            ("law_references_json", "TEXT"),   # JSON array of {type, number, label}
            ("impact_evidence_json", "TEXT"),  # JSON array of verbatim operative clauses
            ("primary_authority", "TEXT"),     # AI responsible-authority name (mapped → authority_id)
        ):
            try:
                conn.execute(f"ALTER TABLE news_items ADD COLUMN {_col} {_decl}")
            except Exception:
                pass


# -----------------------
# Profiles
# -----------------------

def list_profiles(conn: sqlite3.Connection, active_only: bool = True) -> List[sqlite3.Row]:
    sql = "SELECT * FROM profiles"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY country_code, lob, COALESCE(name,'')"
    return list(conn.execute(sql).fetchall())


def get_profile(conn: sqlite3.Connection, country_code: str, lob: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM profiles WHERE country_code = ? AND lob = ? ORDER BY id LIMIT 1",
        (country_code, lob)
    ).fetchone()


def create_profile(conn: sqlite3.Connection, country_code: str, lob: str, name: Optional[str] = None, language: str = "en", active: int = 1) -> int:
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO profiles(country_code, lob, name, language, active)
            VALUES(?,?,?,?,?)
            """,
            (country_code, lob, name, language, active)
        )
        row = get_profile(conn, country_code, lob)
        return int(row["id"]) if row else -1


# -----------------------
# Settings and language
# -----------------------

def set_setting(conn: sqlite3.Connection, profile_id: int, key: str, value: str) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO settings(profile_id, key, value)
            VALUES(?,?,?)
            ON CONFLICT(profile_id, key) DO UPDATE SET value=excluded.value
            """,
            (profile_id, key, value)
        )


def get_setting(conn: sqlite3.Connection, profile_id: int, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM settings WHERE profile_id = ? AND key = ?",
        (profile_id, key)
    ).fetchone()
    return row["value"] if row else default


def get_language(conn: sqlite3.Connection, profile_id: int) -> str:
    row = conn.execute("SELECT language FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    return row["language"] if row and row["language"] else "en"


# -----------------------
# List helpers (feeds, accounts, urls, emails)
# -----------------------

def _list_simple(conn: sqlite3.Connection, table: str, col: str, profile_id: int) -> List[str]:
    sql = f"SELECT {col} FROM {table} WHERE profile_id = ? ORDER BY {col}"
    return [r[col] for r in conn.execute(sql, (profile_id,)).fetchall()]


def list_rss_feeds(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """
    Return RSS feeds with per-source config.
    Returns List[Dict] since v2.9; includes publisher_name and authority_id since v3.0.
    """
    rows = conn.execute(
        """SELECT id, url, COALESCE(max_lookback_days, 7) as max_lookback_days,
           last_fetch_date, publisher_name, authority_id
           FROM rss_feeds WHERE profile_id = ? ORDER BY url""",
        (profile_id,)
    ).fetchall()
    return [
        {
            "id": r["id"],
            "url": r["url"],
            "max_lookback_days": r["max_lookback_days"],
            "last_fetch_date": r["last_fetch_date"],
            "publisher_name": r["publisher_name"],
            "authority_id": r["authority_id"],
        }
        for r in rows
    ]


# -----------------------
# Authority CRUD (v3.0)
# -----------------------

def create_authority(conn: sqlite3.Connection, profile_id: int, name: str, aliases: str = "") -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO authorities(profile_id, name, aliases) VALUES(?,?,?)",
            (profile_id, name, aliases or "")
        )
        return cur.lastrowid


def list_authorities(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, aliases FROM authorities WHERE profile_id=? ORDER BY name",
        (profile_id,)
    ).fetchall()
    return [{"id": r["id"], "name": r["name"], "aliases": r["aliases"] or ""} for r in rows]


def get_authority(conn: sqlite3.Connection, authority_id: int) -> Optional[Dict[str, Any]]:
    r = conn.execute(
        "SELECT id, profile_id, name, aliases FROM authorities WHERE id=?", (authority_id,)
    ).fetchone()
    return {"id": r["id"], "profile_id": r["profile_id"], "name": r["name"], "aliases": r["aliases"] or ""} if r else None


def update_authority(conn: sqlite3.Connection, authority_id: int, name: str, aliases: str = "") -> None:
    with conn:
        conn.execute("UPDATE authorities SET name=?, aliases=? WHERE id=?", (name, aliases or "", authority_id))


def delete_authority(conn: sqlite3.Connection, authority_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM authorities WHERE id=?", (authority_id,))


def get_or_create_authority(conn: sqlite3.Connection, profile_id: int, name: str, aliases: str = "") -> int:
    """Return the id of the authority with this name for the profile, creating it if absent."""
    name = (name or "").strip()
    if not name:
        return -1
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO authorities(profile_id, name, aliases) VALUES(?,?,?)",
            (profile_id, name, aliases or ""),
        )
        row = conn.execute(
            "SELECT id FROM authorities WHERE profile_id=? AND name=?", (profile_id, name)
        ).fetchone()
        return int(row["id"]) if row else -1


# -----------------------
# Law Reference registry (v3.16)
# -----------------------

_LAW_REF_FIELDS = (
    "name_en", "name_native", "law_number", "law_year", "authority_id",
    "effective_date", "status", "source_url", "key_articles",
)


def list_law_refs(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """All registered laws for a profile, with the joined authority name."""
    rows = conn.execute(
        """SELECT lr.*, a.name AS authority_name
           FROM law_refs lr LEFT JOIN authorities a ON a.id = lr.authority_id
           WHERE lr.profile_id=? ORDER BY lr.name_en""",
        (profile_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_law_ref(conn: sqlite3.Connection, law_id: int) -> Optional[Dict[str, Any]]:
    r = conn.execute("SELECT * FROM law_refs WHERE id=?", (law_id,)).fetchone()
    return dict(r) if r else None


def add_law_ref(conn: sqlite3.Connection, profile_id: int, fields: Dict[str, Any]) -> int:
    cols = ["profile_id"] + [f for f in _LAW_REF_FIELDS]
    vals = [profile_id] + [fields.get(f) for f in _LAW_REF_FIELDS]
    ph = ",".join("?" * len(cols))
    with conn:
        cur = conn.execute(
            f"INSERT INTO law_refs({','.join(cols)}) VALUES({ph})", vals
        )
        return int(cur.lastrowid)


def update_law_ref(conn: sqlite3.Connection, law_id: int, fields: Dict[str, Any]) -> None:
    sets = ", ".join(f"{f}=?" for f in _LAW_REF_FIELDS)
    vals = [fields.get(f) for f in _LAW_REF_FIELDS] + [law_id]
    with conn:
        conn.execute(f"UPDATE law_refs SET {sets} WHERE id=?", vals)


def delete_law_ref(conn: sqlite3.Connection, law_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM law_refs WHERE id=?", (law_id,))


def update_news_fields(conn: sqlite3.Connection, item: Dict[str, Any],
                       fields: Dict[str, Any], profile_id: int | None = None) -> None:
    """UPDATE arbitrary news_items columns for a pipeline item.

    Uses the same id / source_id / url / hash_signature fallback as save_topic_labels
    (pipeline items may not carry a DB id yet). Column names come from code, not user
    input, so the f-string is safe.
    """
    if not fields:
        return
    set_clause = ", ".join(f"{c}=?" for c in fields)
    vals = list(fields.values())
    item_id = item.get("id")
    if item_id:
        conn.execute(f"UPDATE news_items SET {set_clause} WHERE id=?", (*vals, item_id))
        return
    src_type = item.get("source_type", "RSS")
    src_id = item.get("source_id") or item.get("guid") or item.get("tweet_id")
    url = item.get("url") or item.get("link")
    hash_sig = item.get("hash_signature")
    pid = item.get("profile_id") or profile_id
    if src_id and pid:
        conn.execute(f"UPDATE news_items SET {set_clause} WHERE profile_id=? AND source_type=? AND source_id=?",
                     (*vals, pid, src_type, src_id))
    elif url and pid:
        conn.execute(f"UPDATE news_items SET {set_clause} WHERE profile_id=? AND source_type=? AND url=?",
                     (*vals, pid, src_type, url))
    elif hash_sig and pid:
        conn.execute(f"UPDATE news_items SET {set_clause} WHERE profile_id=? AND source_type=? AND hash_signature=?",
                     (*vals, pid, src_type, hash_sig))


def list_tweet_accounts(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """
    Return tweet accounts with per-source config (handle, max_lookback_days, last_fetch_date).
    Returns List[Dict] since v2.9.
    """
    rows = conn.execute(
        "SELECT handle, COALESCE(max_lookback_days, 7) as max_lookback_days, last_fetch_date FROM tweet_accounts WHERE profile_id = ? ORDER BY handle",
        (profile_id,)
    ).fetchall()
    return [
        {
            "handle": r["handle"],
            "max_lookback_days": r["max_lookback_days"],
            "last_fetch_date": r["last_fetch_date"],
        }
        for r in rows
    ]


def list_crawl_urls(conn: sqlite3.Connection, profile_id: int) -> List[str]:
    return _list_simple(conn, "crawl_urls", "url", profile_id)


def list_snap_urls(conn: sqlite3.Connection, profile_id: int) -> List[str]:
    return _list_simple(conn, "snap_urls", "url", profile_id)


def list_email_receivers(conn: sqlite3.Connection, profile_id: int) -> List[str]:
    return _list_simple(conn, "email_receivers", "email", profile_id)


def list_email_receivers_with_lang(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """
    List email receivers with their translation language preference.
    Returns: [{"email": "x@y.com", "translation_lang": "en"}, ...]
    """
    rows = conn.execute(
        "SELECT email, COALESCE(translation_lang, 'en') as translation_lang FROM email_receivers WHERE profile_id = ? ORDER BY email",
        (profile_id,)
    ).fetchall()
    return [{"email": r["email"], "translation_lang": r["translation_lang"]} for r in rows]


def upsert_email_receiver_with_lang(conn: sqlite3.Connection, profile_id: int, email: str, translation_lang: str = "en") -> None:
    """
    Insert or update an email receiver with translation language preference.
    """
    with conn:
        conn.execute(
            """
            INSERT INTO email_receivers(profile_id, email, translation_lang)
            VALUES(?,?,?)
            ON CONFLICT(profile_id, email) DO UPDATE SET translation_lang=excluded.translation_lang
            """,
            (profile_id, email, translation_lang)
        )


# -----------------------
# Insert helpers (for migration/admin)
# -----------------------

def upsert_rss_feed(conn: sqlite3.Connection, profile_id: int, url: str,
                    publisher_name=None, authority_id=None) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO rss_feeds(profile_id, url) VALUES(?,?)",
            (profile_id, url)
        )
        conn.execute(
            "UPDATE rss_feeds SET publisher_name=?, authority_id=? WHERE profile_id=? AND url=?",
            (publisher_name, authority_id, profile_id, url)
        )


def upsert_tweet_account(conn: sqlite3.Connection, profile_id: int, handle: str) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO tweet_accounts(profile_id, handle) VALUES(?,?)",
            (profile_id, handle)
        )


def upsert_crawl_url(conn: sqlite3.Connection, profile_id: int, url: str) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO crawl_urls(profile_id, url) VALUES(?,?)",
            (profile_id, url)
        )


def upsert_snap_url(conn: sqlite3.Connection, profile_id: int, url: str) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO snap_urls(profile_id, url) VALUES(?,?)",
            (profile_id, url)
        )


def upsert_email_receiver(conn: sqlite3.Connection, profile_id: int, email: str) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO email_receivers(profile_id, email) VALUES(?,?)",
            (profile_id, email)
        )


def update_rss_feed_last_fetch(conn: sqlite3.Connection, profile_id: int, url: str, timestamp: str) -> None:
    """
    Update last_fetch_date for an RSS feed after successful fetch.

    Args:
        conn: Database connection
        profile_id: Profile ID
        url: RSS feed URL
        timestamp: ISO 8601 datetime string
    """
    with conn:
        conn.execute(
            "UPDATE rss_feeds SET last_fetch_date = ? WHERE profile_id = ? AND url = ?",
            (timestamp, profile_id, url)
        )


def update_tweet_account_last_fetch(conn: sqlite3.Connection, profile_id: int, handle: str, timestamp: str) -> None:
    """
    Update last_fetch_date for a Twitter account after successful fetch.

    Args:
        conn: Database connection
        profile_id: Profile ID
        handle: Twitter account handle (without @)
        timestamp: ISO 8601 datetime string
    """
    with conn:
        conn.execute(
            "UPDATE tweet_accounts SET last_fetch_date = ? WHERE profile_id = ? AND handle = ?",
            (timestamp, profile_id, handle)
        )


# -----------------------
# Glossary helpers
# -----------------------

def add_glossary_term(conn: sqlite3.Connection, profile_id: int, term: str, lang: str = "en",
                      category: Optional[str] = None, product: Optional[str] = None,
                      weight: float = 1.0, notes: Optional[str] = None,
                      label_id: Optional[int] = None) -> int:
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO glossary_terms(profile_id, term, lang, category, product, weight, notes, label_id)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (profile_id, term, lang, category, product, weight, notes, label_id)
        )
        row = conn.execute(
            "SELECT id FROM glossary_terms WHERE profile_id=? AND term=? AND lang=? AND IFNULL(product,'')=IFNULL(?, '')",
            (profile_id, term, lang, product)
        ).fetchone()
        term_id = int(row["id"]) if row else -1
        # Backfill label on an existing (IGNORE'd) row when one wasn't set yet.
        if term_id != -1 and label_id is not None:
            conn.execute(
                "UPDATE glossary_terms SET label_id=? WHERE id=? AND label_id IS NULL",
                (label_id, term_id),
            )
        return term_id


# -----------------------
# Glossary Labels (canonical parent grouping)
# -----------------------

def add_label(conn: sqlite3.Connection, profile_id: int, name: str) -> int:
    """Create (or fetch) a glossary label; returns its id."""
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO glossary_labels(profile_id, name) VALUES(?,?)",
            (profile_id, name.strip()),
        )
        row = conn.execute(
            "SELECT id FROM glossary_labels WHERE profile_id=? AND name=?",
            (profile_id, name.strip()),
        ).fetchone()
        return int(row["id"]) if row else -1


def list_labels(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """Return labels for a profile, each with its member terms (id, term, lang)."""
    labels = conn.execute(
        "SELECT id, name FROM glossary_labels WHERE profile_id=? ORDER BY name",
        (profile_id,),
    ).fetchall()
    result: List[Dict[str, Any]] = []
    for lb in labels:
        terms = conn.execute(
            "SELECT id, term, lang FROM glossary_terms WHERE label_id=? ORDER BY term",
            (lb["id"],),
        ).fetchall()
        result.append({
            "id": lb["id"], "name": lb["name"],
            "terms": [dict(t) for t in terms],
        })
    return result


def rename_label(conn: sqlite3.Connection, profile_id: int, label_id: int, new_name: str) -> None:
    with conn:
        conn.execute(
            "UPDATE glossary_labels SET name=? WHERE id=? AND profile_id=?",
            (new_name.strip(), label_id, profile_id),
        )


def delete_label(conn: sqlite3.Connection, profile_id: int, label_id: int) -> None:
    """Delete a label and its member terms (terms are meaningless without a label)."""
    with conn:
        conn.execute("DELETE FROM glossary_terms WHERE label_id=? AND profile_id=?", (label_id, profile_id))
        conn.execute("DELETE FROM glossary_labels WHERE id=? AND profile_id=?", (label_id, profile_id))


def assign_term_to_label(conn: sqlite3.Connection, term_id: int, label_id: int) -> None:
    with conn:
        conn.execute("UPDATE glossary_terms SET label_id=? WHERE id=?", (label_id, term_id))


def add_glossary_synonym(conn: sqlite3.Connection, term_id: int, synonym: str) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO glossary_synonyms(term_id, synonym) VALUES(?,?)",
            (term_id, synonym)
        )


def add_glossary_pattern(conn: sqlite3.Connection, term_id: int, regex: str) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO glossary_patterns(term_id, regex) VALUES(?,?)",
            (term_id, regex)
        )


def list_glossary_terms(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """
    Return a list of terms with nested synonyms and patterns for the given profile.
    """
    terms = conn.execute(
        "SELECT * FROM glossary_terms WHERE profile_id = ? ORDER BY term, lang",
        (profile_id,)
    ).fetchall()

    result: List[Dict[str, Any]] = []
    for t in terms:
        term_id = t["id"]
        synonyms = [r["synonym"] for r in conn.execute(
            "SELECT synonym FROM glossary_synonyms WHERE term_id=? ORDER BY synonym",
            (term_id,)
        ).fetchall()]
        patterns = [r["regex"] for r in conn.execute(
            "SELECT regex FROM glossary_patterns WHERE term_id=? ORDER BY id",
            (term_id,)
        ).fetchall()]
        result.append(
            {
                "id": term_id,
                "term": t["term"],
                "lang": t["lang"],
                "category": t["category"],
                "product": t["product"],
                "weight": t["weight"],
                "notes": t["notes"],
                "label_id": t["label_id"] if "label_id" in t.keys() else None,
                "synonyms": synonyms,
                "patterns": patterns,
            }
        )
    return result


# -----------------------
# Convenience: flatten glossary for prompt consumption
# -----------------------

def flatten_glossary_for_prompt(glossary_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convert normalized glossary into a simple structure usable by prompt code.
    Example output shape (flexible to match downstream needs):
    {
        "terms": [
            {
                "term": "income tax",
                "lang": "en",
                "category": "HCM",
                "product": "SAP HCM",
                "weight": 1.0,
                "synonyms": ["tax on income", "salary tax"],
                "patterns": ["\\bIncome Tax\\b"]
            },
            ...
        ]
    }
    """
    return {"terms": glossary_rows}


# -----------------------
# News baseline helpers
# -----------------------

def upsert_news_item(conn: sqlite3.Connection, profile_id: int, item: Dict[str, Any]) -> int:
    """
    Insert or update a news item for weekly baseline.
    Strategy:
      1) Try to find existing row by (source_id) or (url) or (hash_signature)
      2) If found → update last_seen_at and enrich missing fields
      3) Else → insert new row
    """
    now_iso = datetime.utcnow().isoformat()
    source_type = item.get("source_type") or ""
    source_id = item.get("source_id")
    url = item.get("url")
    domain = item.get("domain")
    title = item.get("title")
    content = item.get("content")
    published_at = item.get("published_at")
    hash_sig = item.get("hash_signature")
    # v3.1 source attribution + dedup marker (optional; stamped by attributor/compare stages)
    publisher = item.get("publisher")
    authority_id = item.get("authority_id")
    authority_status = item.get("authority_status")
    dedup_status = item.get("dedup_status")
    # v3.2 ranking + repetition (optional; stamped by ranker/compare stages; also used by seed)
    significance_rank = item.get("significance_rank")
    rank_tier = item.get("rank_tier")
    rank_reasoning = item.get("rank_reasoning")
    repetition_status = item.get("repetition_status")
    repetition_count = item.get("repetition_count")
    # v3.3 tagging + email gate (optional; stamped by tagger/gate stages; also used by seed)
    topic_label = item.get("topic_label")
    email_eligible = item.get("email_eligible") or 0
    email_sent = item.get("email_sent") or 0
    # v3.8 effective date (optional; stamped by ranker / effective-date step)
    effective_date = item.get("effective_date")
    # v3.13 L2 deep-fetch + grouping fields (optional; stamped by l2_fetcher / glossary_match)
    l2_summary = item.get("l2_summary")
    l2_fetched_at = item.get("l2_fetched_at")
    act_ref = item.get("act_ref")
    law_primary = item.get("law_primary")
    law_secondary = item.get("law_secondary")
    law_reference = item.get("law_reference")
    announce_state = item.get("announce_state")

    with conn:
        # 1) Locate existing row by strongest identifiers first
        row = None
        if source_id:
            row = conn.execute(
                "SELECT id FROM news_items WHERE profile_id=? AND source_type=? AND source_id=?",
                (profile_id, source_type, source_id),
            ).fetchone()

        if not row and url:
            row = conn.execute(
                "SELECT id FROM news_items WHERE profile_id=? AND source_type=? AND url=?",
                (profile_id, source_type, url),
            ).fetchone()

        if not row and hash_sig:
            row = conn.execute(
                "SELECT id FROM news_items WHERE profile_id=? AND source_type=? AND hash_signature=?",
                (profile_id, source_type, hash_sig),
            ).fetchone()

        # 2) Update existing
        if row:
            news_id = int(row["id"])
            conn.execute(
                """
                UPDATE news_items
                SET last_seen_at=?,
                    title=COALESCE(?, title),
                    content=COALESCE(?, content),
                    domain=COALESCE(?, domain),
                    published_at=COALESCE(?, published_at),
                    url=COALESCE(url, ?),
                    source_id=COALESCE(source_id, ?),
                    hash_signature=COALESCE(?, hash_signature),
                    publisher=COALESCE(?, publisher),
                    authority_id=COALESCE(?, authority_id),
                    authority_status=COALESCE(?, authority_status),
                    dedup_status=COALESCE(?, dedup_status),
                    significance_rank=COALESCE(?, significance_rank),
                    rank_tier=COALESCE(?, rank_tier),
                    rank_reasoning=COALESCE(?, rank_reasoning),
                    repetition_status=COALESCE(?, repetition_status),
                    repetition_count=COALESCE(?, repetition_count),
                    topic_label=COALESCE(?, topic_label),
                    email_eligible=COALESCE(?, email_eligible),
                    email_sent=COALESCE(?, email_sent),
                    effective_date=COALESCE(?, effective_date),
                    l2_summary=COALESCE(?, l2_summary),
                    l2_fetched_at=COALESCE(?, l2_fetched_at),
                    act_ref=COALESCE(?, act_ref),
                    law_primary=COALESCE(?, law_primary),
                    law_secondary=COALESCE(?, law_secondary),
                    law_reference=COALESCE(?, law_reference),
                    announce_state=COALESCE(?, announce_state)
                WHERE id=?
                """,
                (
                    now_iso,
                    title,
                    content,
                    domain,
                    published_at,
                    url,
                    source_id,
                    hash_sig,
                    publisher,
                    authority_id,
                    authority_status,
                    dedup_status,
                    significance_rank,
                    rank_tier,
                    rank_reasoning,
                    repetition_status,
                    repetition_count,
                    topic_label,
                    email_eligible,
                    email_sent,
                    effective_date,
                    l2_summary,
                    l2_fetched_at,
                    act_ref,
                    law_primary,
                    law_secondary,
                    law_reference,
                    announce_state,
                    news_id,
                ),
            )
            return news_id

        # 3) Insert new
        conn.execute(
            """
            INSERT INTO news_items(profile_id, source_type, source_id, url, domain, title, content, published_at, first_seen_at, last_seen_at, hash_signature, publisher, authority_id, authority_status, dedup_status, significance_rank, rank_tier, rank_reasoning, repetition_status, repetition_count, topic_label, email_eligible, email_sent, effective_date, l2_summary, l2_fetched_at, act_ref, law_primary, law_secondary, law_reference, announce_state)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                profile_id,
                source_type,
                source_id,
                url,
                domain,
                title,
                content,
                published_at,
                now_iso,
                now_iso,
                hash_sig,
                publisher,
                authority_id,
                authority_status,
                dedup_status,
                significance_rank,
                rank_tier,
                rank_reasoning,
                repetition_status,
                repetition_count,
                topic_label,
                email_eligible,
                email_sent,
                effective_date,
                l2_summary,
                l2_fetched_at,
                act_ref,
                law_primary,
                law_secondary,
                law_reference,
                announce_state,
            ),
        )
        row = conn.execute(
            "SELECT id FROM news_items WHERE profile_id=? AND source_type=? AND hash_signature=?",
            (profile_id, source_type, hash_sig),
        ).fetchone()
        return int(row["id"]) if row else -1


def update_last_seen(conn: sqlite3.Connection, news_id: int) -> None:
    """
    Touch last_seen_at for an existing news item.
    """
    now_iso = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            "UPDATE news_items SET last_seen_at=? WHERE id=?",
            (now_iso, news_id),
        )


def list_baseline_items(conn: sqlite3.Connection, profile_id: int, days: int = 7) -> List[Dict[str, Any]]:
    """
    Return items in the rolling baseline window (last X days by first_seen_at/last_seen_at).
    """
    window_iso = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
        SELECT id, profile_id, source_type, source_id, url, domain, title, content, published_at, first_seen_at, last_seen_at, hash_signature, repetition_count
        FROM news_items
        WHERE profile_id = ?
          AND (first_seen_at >= ? OR last_seen_at >= ?)
        ORDER BY COALESCE(published_at, last_seen_at) DESC
        """,
        (profile_id, window_iso, window_iso),
    ).fetchall()
    result: List[Dict[str, Any]] = []
    for r in rows:
        result.append({k: r[k] for k in r.keys()})
    return result


# -----------------------
# Unified URL sources helpers
# -----------------------

def list_url_sources(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """
    Return a list of URL sources with mode and sample_link for the given profile.
    Shape:
      [{"url": str, "mode": "auto|force_static|force_dynamic|recursive", "sample_link": Optional[str], "read_more_label": Optional[str],
        "crawl_version": str, "max_depth": int, "allowed_domains": str, "path_filter": str, "max_results": int, "date_scope": str,
        "url_date_template": Optional[str], "last_successful_fetch": Optional[str], "created_at": str}]
    """
    rows = conn.execute(
        "SELECT url, mode, sample_link, read_more_label, crawl_version, max_depth, allowed_domains, path_filter, max_results, date_scope, url_date_template, last_successful_fetch, created_at, "
        "simulation_status, simulated_at, container_selector, field_selectors, read_more_selector, pagination_type, pagination_selector, depth_level, requires_js, publisher_name, authority_id "
        "FROM url_sources WHERE profile_id = ? ORDER BY url",
        (profile_id,)
    ).fetchall()
    return [
        {
            "url": r["url"],
            "mode": r["mode"],
            "sample_link": r["sample_link"],
            "read_more_label": r["read_more_label"],
            "crawl_version": r["crawl_version"],
            "max_depth": r["max_depth"],
            "allowed_domains": r["allowed_domains"],
            "path_filter": r["path_filter"],
            "max_results": r["max_results"],
            "date_scope": r["date_scope"],
            "url_date_template": r["url_date_template"],
            "last_successful_fetch": r["last_successful_fetch"],
            "created_at": r["created_at"],
            # Source Simulator (v3.1, F9)
            "simulation_status": r["simulation_status"],
            "simulated_at": r["simulated_at"],
            "container_selector": r["container_selector"],
            "field_selectors": r["field_selectors"],
            "read_more_selector": r["read_more_selector"],
            "pagination_type": r["pagination_type"],
            "pagination_selector": r["pagination_selector"],
            "depth_level": r["depth_level"],
            "requires_js": r["requires_js"],
            # Source attribution (v3.0)
            "publisher_name": r["publisher_name"],
            "authority_id": r["authority_id"],
        }
        for r in rows
    ]


def upsert_url_source(
    conn: sqlite3.Connection,
    profile_id: int,
    url: str,
    mode: str = "auto",
    sample_link: Optional[str] = None,
    read_more_label: Optional[str] = None,
    crawl_version: str = "v1",
    max_depth: int = 2,
    allowed_domains: Optional[str] = None,
    path_filter: Optional[str] = None,
    max_results: int = 20,
    date_scope: str = "all",
    url_date_template: Optional[str] = None,
) -> None:
    """
    Insert a new url_source or update existing with all parameters including recursive options.
    """
    now_iso = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO url_sources(profile_id, url, mode, sample_link, read_more_label, crawl_version,
                                   max_depth, allowed_domains, path_filter, max_results, date_scope, url_date_template, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_id, url) DO UPDATE SET
              mode=excluded.mode,
              sample_link=excluded.sample_link,
              read_more_label=excluded.read_more_label,
              crawl_version=excluded.crawl_version,
              max_depth=excluded.max_depth,
              allowed_domains=excluded.allowed_domains,
              path_filter=excluded.path_filter,
              max_results=excluded.max_results,
              date_scope=excluded.date_scope,
              url_date_template=excluded.url_date_template
            """,
            (profile_id, url, mode, sample_link, read_more_label, crawl_version,
             max_depth, allowed_domains, path_filter, max_results, date_scope, url_date_template, now_iso)
        )


def delete_url_source(conn: sqlite3.Connection, profile_id: int, url: str) -> None:
    """
    Delete a url_source row for a profile.
    """
    with conn:
        conn.execute("DELETE FROM url_sources WHERE profile_id = ? AND url = ?", (profile_id, url))


def save_simulation_result(
    conn: sqlite3.Connection,
    profile_id: int,
    url: str,
    *,
    sample_link: Optional[str] = None,
    container_selector: Optional[str] = None,
    field_selectors: Optional[str] = None,
    read_more_selector: Optional[str] = None,
    pagination_type: Optional[str] = None,
    pagination_selector: Optional[str] = None,
    depth_level: Optional[int] = None,
    requires_js: int = 0,
    simulation_status: str = "success",
) -> None:
    """Persist Source Simulator output onto a url_source row (v3.1, F9).
    Inserts the row if missing (URL-only add), else updates the simulator columns."""
    now_iso = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO url_sources(profile_id, url, mode, simulation_status, simulated_at,
                container_selector, field_selectors, read_more_selector,
                pagination_type, pagination_selector, depth_level, requires_js, sample_link, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_id, url) DO UPDATE SET
                simulation_status=excluded.simulation_status,
                simulated_at=excluded.simulated_at,
                container_selector=excluded.container_selector,
                field_selectors=excluded.field_selectors,
                read_more_selector=excluded.read_more_selector,
                pagination_type=excluded.pagination_type,
                pagination_selector=excluded.pagination_selector,
                depth_level=excluded.depth_level,
                requires_js=excluded.requires_js,
                sample_link=COALESCE(excluded.sample_link, url_sources.sample_link)
            """,
            (profile_id, url, "auto", simulation_status, now_iso,
             container_selector, field_selectors, read_more_selector,
             pagination_type, pagination_selector, depth_level, int(requires_js or 0),
             sample_link, now_iso),
        )


def update_url_source_last_fetch(conn: sqlite3.Connection, profile_id: int, url: str, timestamp: str) -> None:
    """
    Update last_successful_fetch timestamp for a URL source after successful fetch.
    
    Args:
        conn: Database connection
        profile_id: Profile ID
        url: URL source
        timestamp: ISO 8601 datetime string (e.g., datetime.utcnow().isoformat())
    """
    with conn:
        conn.execute(
            "UPDATE url_sources SET last_successful_fetch = ? WHERE profile_id = ? AND url = ?",
            (timestamp, profile_id, url)
        )


# -----------------------
# Global credentials helpers
# -----------------------





# -----------------------
# Audit log helper
# -----------------------

def add_audit_log(conn: sqlite3.Connection, entity: str, action: str, details: Optional[str] = None, profile_id: Optional[int] = None) -> None:
    """
    Record an audit trail entry of admin changes.
    """
    now_iso = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            "INSERT INTO audit_log(profile_id, entity, action, details, created_at) VALUES(?,?,?,?,?)",
            (profile_id, entity, action, details, now_iso)
        )


# -----------------------
# Runs + Logs helpers
# -----------------------

def create_run(conn: sqlite3.Connection, profile_id: int, origin: str = "manual") -> int:
    with conn:
        conn.execute(
            "INSERT INTO runs(profile_id, status, origin, created_at) VALUES(?, 'Queued', ?, datetime('now'))",
            (profile_id, origin)
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        return int(row["id"])

def start_run(conn: sqlite3.Connection, run_id: int) -> None:
    now_iso = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            "UPDATE runs SET status='Running', started_at=? WHERE id=?",
            (now_iso, run_id)
        )

def finish_run(conn: sqlite3.Connection, run_id: int, status: str, metrics: Optional[Dict[str, Any]] = None) -> None:
    now_iso = datetime.utcnow().isoformat()
    with conn:
        # duration_ms computed if started_at exists
        row = conn.execute("SELECT started_at FROM runs WHERE id=?", (run_id,)).fetchone()
        duration_ms = None
        if row and row["started_at"]:
            try:
                started = datetime.fromisoformat(row["started_at"])
                duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            except Exception:
                duration_ms = None
        fields = ["status", "finished_at", "duration_ms"]
        values: List[Any] = [status, now_iso, duration_ms]
        metric_fields = ["rss_count","tweet_count","url_count","filtered_count","grouped_count","email_status","error_step","error_message"]
        if metrics:
            for k in metric_fields:
                if k in metrics:
                    fields.append(k)
                    values.append(metrics[k])
        set_clause = ", ".join([f"{f}=?" for f in fields])
        conn.execute(f"UPDATE runs SET {set_clause} WHERE id=?", (*values, run_id))

def append_run_log(conn: sqlite3.Connection, run_id: int, level: str, line: str) -> int:
    now_iso = datetime.utcnow().isoformat()
    row = conn.execute("SELECT COALESCE(MAX(seq),0)+1 AS next_seq FROM run_logs WHERE run_id=?", (run_id,)).fetchone()
    next_seq = int(row["next_seq"] or 1)
    with conn:
        conn.execute(
            "INSERT INTO run_logs(run_id, ts, level, line, seq) VALUES(?,?,?,?,?)",
            (run_id, now_iso, level, line, next_seq)
        )
    return next_seq

def list_runs_for_profile(conn: sqlite3.Connection, profile_id: int, limit: int = 30) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM runs
        WHERE profile_id = ? AND created_at >= datetime('now','-7 days')
        ORDER BY id DESC
        LIMIT ?
        """,
        (profile_id, limit)
    ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]

def get_run(conn: sqlite3.Connection, run_id: int) -> Optional[Dict[str, Any]]:
    r = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return ({k: r[k] for k in r.keys()} if r else None)

def list_run_logs(conn: sqlite3.Connection, run_id: int, after_seq: Optional[int] = None, limit: int = 1000) -> List[Dict[str, Any]]:
    if after_seq is None:
        rows = conn.execute(
            "SELECT ts, level, line, seq FROM run_logs WHERE run_id=? ORDER BY seq ASC LIMIT ?",
            (run_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT ts, level, line, seq FROM run_logs WHERE run_id=? AND seq>? ORDER BY seq ASC LIMIT ?",
            (run_id, after_seq, limit)
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]

def set_cancel_requested(conn: sqlite3.Connection, run_id: int) -> None:
    with conn:
        conn.execute("UPDATE runs SET cancel_requested=1 WHERE id=?", (run_id,))

def is_cancel_requested(conn: sqlite3.Connection, run_id: int) -> bool:
    r = conn.execute("SELECT cancel_requested FROM runs WHERE id=?", (run_id,)).fetchone()
    return bool(r and int(r["cancel_requested"] or 0) == 1)

def prune_old_runs(conn: sqlite3.Connection, days: int = 7) -> None:
    with conn:
        conn.execute(
            f"DELETE FROM run_logs WHERE run_id IN (SELECT id FROM runs WHERE created_at < datetime('now','-{days} days'))"
        )
        conn.execute(
            f"DELETE FROM runs WHERE created_at < datetime('now','-{days} days')"
        )


# -----------------------
# Filtered news helpers (for manual review)
# -----------------------

def insert_filtered_news(conn: sqlite3.Connection, profile_id: int, item: Dict[str, Any], filter_reason: str, run_id: Optional[int] = None) -> int:
    """
    Insert a filtered (discarded) news item for later manual review.
    Returns the inserted row id.
    """
    # Extract published_at from various possible field names
    published_at = (
        item.get("published_at") or 
        item.get("published") or 
        item.get("date") or 
        item.get("pubDate") or 
        ""
    )
    with conn:
        conn.execute(
            """
            INSERT INTO filtered_news(profile_id, run_id, source_type, url, title, content, filter_reason, published_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                profile_id,
                run_id,
                item.get("source_type") or item.get("type") or "",
                item.get("link") or item.get("url") or "",
                item.get("title") or "",
                item.get("content") or "",
                filter_reason,
                published_at,
            ),
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        return int(row["id"]) if row else -1


def list_filtered_news(conn: sqlite3.Connection, profile_id: int, reviewed: Optional[bool] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """
    List filtered news items for a profile.
    - reviewed=None: all items
    - reviewed=True: only items with relevance_score set
    - reviewed=False: only items without relevance_score (pending review)
    """
    sql = "SELECT * FROM filtered_news WHERE profile_id = ?"
    params: List[Any] = [profile_id]
    
    if reviewed is True:
        sql += " AND relevance_score IS NOT NULL"
    elif reviewed is False:
        sql += " AND relevance_score IS NULL"
    
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(sql, params).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def count_filtered_news(conn: sqlite3.Connection, profile_id: int, reviewed: Optional[bool] = None) -> int:
    """
    Count filtered news items for a profile.
    """
    sql = "SELECT COUNT(*) AS cnt FROM filtered_news WHERE profile_id = ?"
    params: List[Any] = [profile_id]
    
    if reviewed is True:
        sql += " AND relevance_score IS NOT NULL"
    elif reviewed is False:
        sql += " AND relevance_score IS NULL"
    
    row = conn.execute(sql, params).fetchone()
    return int(row["cnt"]) if row else 0


def update_filtered_news_score(conn: sqlite3.Connection, item_id: int, relevance_score: int) -> None:
    """
    Update the relevance score for a filtered news item (1-5 scale).
    """
    now_iso = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            "UPDATE filtered_news SET relevance_score = ?, reviewed_at = ? WHERE id = ?",
            (relevance_score, now_iso, item_id),
        )


def delete_filtered_news(conn: sqlite3.Connection, item_id: int) -> None:
    """
    Delete a single filtered news item.
    """
    with conn:
        conn.execute("DELETE FROM filtered_news WHERE id = ?", (item_id,))


def clear_filtered_news(conn: sqlite3.Connection, profile_id: int, reviewed_only: bool = False) -> int:
    """
    Clear filtered news items for a profile.
    Returns count of deleted items.
    """
    if reviewed_only:
        sql = "SELECT COUNT(*) AS cnt FROM filtered_news WHERE profile_id = ? AND relevance_score IS NOT NULL"
    else:
        sql = "SELECT COUNT(*) AS cnt FROM filtered_news WHERE profile_id = ?"
    
    row = conn.execute(sql, (profile_id,)).fetchone()
    count = int(row["cnt"]) if row else 0
    
    with conn:
        if reviewed_only:
            conn.execute("DELETE FROM filtered_news WHERE profile_id = ? AND relevance_score IS NOT NULL", (profile_id,))
        else:
            conn.execute("DELETE FROM filtered_news WHERE profile_id = ?", (profile_id,))
    
    return count


def prune_old_filtered_news(conn: sqlite3.Connection, days: int = 30) -> None:
    """
    Remove filtered news older than X days (default 30).
    """
    with conn:
        conn.execute(
            f"DELETE FROM filtered_news WHERE created_at < datetime('now','-{days} days')"
        )


def list_all_news_for_review(
    conn: sqlite3.Connection, 
    profile_id: int, 
    source: Optional[str] = None,
    reviewed: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Fetch news items from BOTH news_items (accepted/baseline) and filtered_news tables.
    Returns combined list with 'item_source' field to distinguish origin.
    
    Args:
        profile_id: Profile to fetch news for
        source: Filter by source - 'accepted', 'filtered', or None for all
        reviewed: Filter by review status - True (reviewed), False (pending), None (all)
        limit: Max items to return
        offset: Pagination offset
    
    Returns:
        List of dicts with 'item_source' field ('accepted' or 'filtered')
    """
    results: List[Dict[str, Any]] = []
    
    # Fetch from news_items (accepted/baseline) if requested
    if source is None or source == 'accepted':
        sql_accepted = """
            SELECT id, profile_id, source_type, source_id, url, domain, title, content,
                   published_at, first_seen_at, last_seen_at, hash_signature,
                   relevance_score, reviewed_at,
                   publisher, authority_id, authority_status, dedup_status,
                   significance_rank, rank_tier, rank_reasoning,
                   human_rank_override, human_override_reason,
                   repetition_status, repetition_count,
                   topic_label, email_eligible, email_sent, glossary_gap,
                   effective_date, l2_summary, act_ref, law_primary, law_secondary, law_reference,
                   law_id, law_ref_status, cited_article, proposed_rcm_title, rcm_match_status,
                   law_references_json, impact_evidence_json, primary_authority,
                   operational_impact, timing_class,
                   (SELECT name FROM authorities WHERE authorities.id = news_items.authority_id) AS authority_name
            FROM news_items
            WHERE profile_id = ?
        """
        params_accepted: List[Any] = [profile_id]
        
        if reviewed is True:
            sql_accepted += " AND relevance_score IS NOT NULL"
        elif reviewed is False:
            sql_accepted += " AND relevance_score IS NULL"
        
        sql_accepted += " ORDER BY COALESCE(published_at, last_seen_at) DESC"
        
        rows_accepted = conn.execute(sql_accepted, params_accepted).fetchall()
        for r in rows_accepted:
            item = {k: r[k] for k in r.keys()}
            item['item_source'] = 'accepted'
            item['created_at'] = r['first_seen_at']
            # v3.2: unified rank/tag fields for template
            item['rank'] = r['significance_rank'] if 'significance_rank' in r.keys() else None
            item['override_rank'] = r['human_rank_override'] if 'human_rank_override' in r.keys() else None
            item['override_reason'] = r['human_override_reason'] if 'human_override_reason' in r.keys() else None
            item['status'] = (r['repetition_status'] or '').upper() if 'repetition_status' in r.keys() else ''
            # v3.5: glossary gap flag — consumed by review_news.html (item.is_gap)
            item['is_gap'] = bool(int(item.get('glossary_gap') or 0))
            results.append(item)
    
    # Fetch from filtered_news if requested
    if source is None or source == 'filtered':
        sql_filtered = """
            SELECT id, profile_id, source_type, url, title, content, filter_reason,
                   created_at, relevance_score, reviewed_at
            FROM filtered_news 
            WHERE profile_id = ?
        """
        params_filtered: List[Any] = [profile_id]
        
        if reviewed is True:
            sql_filtered += " AND relevance_score IS NOT NULL"
        elif reviewed is False:
            sql_filtered += " AND relevance_score IS NULL"
        
        sql_filtered += " ORDER BY created_at DESC"
        
        rows_filtered = conn.execute(sql_filtered, params_filtered).fetchall()
        for r in rows_filtered:
            item = {k: r[k] for k in r.keys()}
            item['item_source'] = 'filtered'
            # Add missing fields for consistency
            item['source_id'] = None
            item['domain'] = None
            item['published_at'] = None
            item['first_seen_at'] = r['created_at']
            item['last_seen_at'] = r['created_at']
            item['hash_signature'] = None
            results.append(item)
    
    # Sort combined results by publish date (most recent first); fall back to
    # collection time only when an item has no publish date.
    results.sort(key=lambda x: x.get('published_at') or x.get('created_at') or x.get('last_seen_at') or '', reverse=True)
    
    # Apply pagination
    return results[offset:offset + limit]


def count_all_news_for_review(
    conn: sqlite3.Connection,
    profile_id: int,
    source: Optional[str] = None,
    reviewed: Optional[bool] = None
) -> int:
    """
    Count news items from BOTH news_items and filtered_news tables.
    
    Args:
        profile_id: Profile to count news for
        source: Filter by source - 'accepted', 'filtered', or None for all
        reviewed: Filter by review status - True (reviewed), False (pending), None (all)
    
    Returns:
        Total count across both tables
    """
    total = 0
    
    # Count from news_items (accepted/baseline)
    if source is None or source == 'accepted':
        sql_accepted = "SELECT COUNT(*) AS cnt FROM news_items WHERE profile_id = ?"
        params_accepted: List[Any] = [profile_id]
        
        if reviewed is True:
            sql_accepted += " AND relevance_score IS NOT NULL"
        elif reviewed is False:
            sql_accepted += " AND relevance_score IS NULL"
        
        row = conn.execute(sql_accepted, params_accepted).fetchone()
        total += int(row["cnt"]) if row else 0
    
    # Count from filtered_news
    if source is None or source == 'filtered':
        sql_filtered = "SELECT COUNT(*) AS cnt FROM filtered_news WHERE profile_id = ?"
        params_filtered: List[Any] = [profile_id]
        
        if reviewed is True:
            sql_filtered += " AND relevance_score IS NOT NULL"
        elif reviewed is False:
            sql_filtered += " AND relevance_score IS NULL"
        
        row = conn.execute(sql_filtered, params_filtered).fetchone()
        total += int(row["cnt"]) if row else 0
    
    return total


def update_news_item_score(conn: sqlite3.Connection, item_id: int, item_source: str, relevance_score: int) -> None:
    """
    Update the relevance score for a news item from EITHER table.
    
    Args:
        item_id: Item ID
        item_source: 'accepted' (news_items table) or 'filtered' (filtered_news table)
        relevance_score: Score 1-5
    """
    now_iso = datetime.utcnow().isoformat()
    with conn:
        if item_source == 'accepted':
            conn.execute(
                "UPDATE news_items SET relevance_score = ?, reviewed_at = ? WHERE id = ?",
                (relevance_score, now_iso, item_id),
            )
        elif item_source == 'filtered':
            conn.execute(
                "UPDATE filtered_news SET relevance_score = ?, reviewed_at = ? WHERE id = ?",
                (relevance_score, now_iso, item_id),
            )


def delete_news_item(conn: sqlite3.Connection, item_id: int, item_source: str) -> None:
    """
    Delete a news item from EITHER table.
    
    Args:
        item_id: Item ID
        item_source: 'accepted' (news_items table) or 'filtered' (filtered_news table)
    """
    with conn:
        if item_source == 'accepted':
            conn.execute("DELETE FROM news_items WHERE id = ?", (item_id,))
        elif item_source == 'filtered':
            conn.execute("DELETE FROM filtered_news WHERE id = ?", (item_id,))


def get_reviewed_news_baseline(conn: sqlite3.Connection, profile_id: int, min_score: int = 4) -> List[Dict[str, Any]]:
    """
    Retrieve filtered news items that have been manually reviewed with a high relevance score.
    These serve as high-quality examples for comparison, independent of date.
    
    Args:
        conn: Database connection
        profile_id: Profile ID to filter by
        min_score: Minimum relevance score (1-5) to include. Default is 4 (good or excellent).
    
    Returns:
        List of reviewed items, formatted for use in the compare_news baseline.
    """
    rows = conn.execute(
        """
        SELECT id, profile_id, source_type, url, title, content, relevance_score, reviewed_at
        FROM filtered_news
        WHERE profile_id = ? AND relevance_score IS NOT NULL AND relevance_score >= ?
        ORDER BY reviewed_at DESC
        """,
        (profile_id, min_score),
    ).fetchall()
    
    result: List[Dict[str, Any]] = []
    for r in rows:
        result.append({
            "id": r["id"],
            "profile_id": r["profile_id"],
            "source_type": r["source_type"],
            "url": r["url"],
            "title": r["title"],
            "content": r["content"],
            "relevance_score": r["relevance_score"],
            "reviewed_at": r["reviewed_at"],
            # These fields are expected by the compare_news agent
            "source_id": None,
            "domain": None,
            "hash_signature": None,
        })
    return result


# -----------------------
# Monitor updates helpers (Law-to-Specification email integration)
# -----------------------

def insert_monitor_update_processed(
    conn: sqlite3.Connection,
    profile_id: int,
    email_message_id: str,
    report_date: Optional[str],
    monitored_url: Optional[str],
    changes: List[str]
) -> int:
    """
    Mark a Law-to-Specification email as processed.
    
    Args:
        conn: Database connection
        profile_id: Profile ID
        email_message_id: Gmail message ID (unique)
        report_date: Report date from email (ISO format)
        monitored_url: URL being monitored
        changes: List of change summaries
    
    Returns:
        Inserted row ID
    """
    import json
    now_iso = datetime.utcnow().isoformat()
    changes_json = json.dumps(changes)
    
    with conn:
        try:
            conn.execute(
                """
                INSERT INTO monitor_updates_processed(
                    profile_id, email_message_id, report_date, monitored_url, changes_json, processed_at
                )
                VALUES(?,?,?,?,?,?)
                """,
                (profile_id, email_message_id, report_date, monitored_url, changes_json, now_iso)
            )
            row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
            return int(row["id"]) if row else -1
        except sqlite3.IntegrityError:
            # Email already processed (duplicate email_message_id)
            return -1


def is_monitor_email_processed(conn: sqlite3.Connection, email_message_id: str) -> bool:
    """
    Check if an email has already been processed.
    
    Args:
        conn: Database connection
        email_message_id: Gmail message ID
    
    Returns:
        True if email was already processed, False otherwise
    """
    row = conn.execute(
        "SELECT id FROM monitor_updates_processed WHERE email_message_id = ?",
        (email_message_id,)
    ).fetchone()
    return row is not None


def list_monitor_updates_for_profile(
    conn: sqlite3.Connection,
    profile_id: int,
    days: int = 7
) -> List[Dict[str, Any]]:
    """
    List recent monitor updates for a profile.
    
    Args:
        conn: Database connection
        profile_id: Profile ID
        days: How many days back to look (default: 7)
    
    Returns:
        List of monitor update records
    """
    import json
    window_iso = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    rows = conn.execute(
        """
        SELECT id, profile_id, email_message_id, report_date, monitored_url, changes_json, processed_at
        FROM monitor_updates_processed
        WHERE profile_id = ? AND processed_at >= ?
        ORDER BY processed_at DESC
        """,
        (profile_id, window_iso)
    ).fetchall()
    
    result: List[Dict[str, Any]] = []
    for r in rows:
        changes = json.loads(r["changes_json"]) if r["changes_json"] else []
        result.append({
            "id": r["id"],
            "profile_id": r["profile_id"],
            "email_message_id": r["email_message_id"],
            "report_date": r["report_date"],
            "monitored_url": r["monitored_url"],
            "changes": changes,
            "processed_at": r["processed_at"],
        })
    return result




def insert_ranking_grounding(
    conn: sqlite3.Connection,
    profile_id: int,
    item_id: int,
    example_md: str,
    source_label: Optional[str] = None,
    rank: Optional[int] = None,
) -> int:
    for _col, _decl in (("source_label", "TEXT"), ("created_at", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE ranking_grounding ADD COLUMN {_col} {_decl}")
        except Exception:
            pass
    cur = conn.execute(
        """
        INSERT INTO ranking_grounding(profile_id, source_item_id, summary, source_label, rank, created_at)
        VALUES(?,?,?,?,?,datetime('now'))
        """,
        (profile_id, item_id, example_md, source_label, rank),
    )
    return cur.lastrowid


def insert_ranking_signal(
    conn: sqlite3.Connection,
    profile_id: int,
    pattern: str,
    rank: int,
    reason: Optional[str] = None,
) -> int:
    for _col, _decl in (("reason", "TEXT"), ("created_at", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE ranking_signals ADD COLUMN {_col} {_decl}")
        except Exception:
            pass
    cur = conn.execute(
        """
        INSERT INTO ranking_signals(profile_id, signal_type, pattern, min_rank, confidence, created_from, reason, created_at)
        VALUES(?,?,?,?,?,?,?,datetime('now'))
        """,
        (profile_id, "human_confirmed", pattern, rank, 1.0, "challenge_modal", reason),
    )
    return cur.lastrowid


def get_announcements_for_run_with_sources(
    conn: sqlite3.Connection, run_id: int
) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM news_announcements WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    result = []
    for row in rows:
        ann = dict(row)
        try:
            item_ids = json.loads(ann.get("item_ids_json") or "[]")
        except Exception:
            item_ids = []
        sources = []
        if item_ids:
            placeholders = ",".join("?" * len(item_ids))
            src_rows = conn.execute(
                f"""SELECT *,
                    (SELECT name FROM authorities WHERE authorities.id = news_items.authority_id) AS authority_name
                    FROM news_items WHERE id IN ({placeholders})""",
                item_ids,
            ).fetchall()
            sources = [dict(s) for s in src_rows]
        ann["sources"] = sources
        result.append(ann)
    return result


def set_announcement_publish(conn: sqlite3.Connection, announcement_id: int,
                             jira_legal_change: Optional[str], status: str) -> None:
    """v3.6: persist the JIRA Legal Change link + status on an announcement (close the loop)."""
    with conn:
        conn.execute(
            "UPDATE news_announcements SET jira_legal_change=?, status=? WHERE id=?",
            ((jira_legal_change or None), status, announcement_id),
        )


# -----------------------
# v3.13 — persistent, profile-scoped announcement state machine
# -----------------------

def get_announcements_for_profile_with_sources(
    conn: sqlite3.Connection, profile_id: int
) -> List[Dict[str, Any]]:
    """Profile-scoped read for the Announcement tab (persistent across runs)."""
    rows = conn.execute(
        "SELECT * FROM news_announcements WHERE profile_id=? ORDER BY "
        "CASE WHEN status='done' THEN 1 ELSE 0 END, id DESC",
        (profile_id,),
    ).fetchall()
    result = []
    for row in rows:
        ann = dict(row)
        try:
            item_ids = json.loads(ann.get("item_ids_json") or "[]")
        except Exception:
            item_ids = []
        sources = []
        if item_ids:
            placeholders = ",".join("?" * len(item_ids))
            src_rows = conn.execute(
                f"""SELECT *,
                    (SELECT name FROM authorities WHERE authorities.id = news_items.authority_id) AS authority_name
                    FROM news_items WHERE id IN ({placeholders})""",
                item_ids,
            ).fetchall()
            sources = [dict(s) for s in src_rows]
        ann["sources"] = sources
        result.append(ann)
    return result


def get_pending_announce_items(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """Items awaiting (re)grouping for announcements.

    Gated on rank (not the email_eligible flag): any non-duplicate item whose
    significance_rank meets the profile's threshold and is still announce_state='pending'.
    Decoupled from email so a human rank upgrade qualifies an item for announcement
    without a pipeline rerun.
    """
    threshold = int(get_setting(conn, profile_id, "email_rank_threshold", "3") or 3)
    rows = conn.execute(
        """SELECT * FROM news_items
           WHERE profile_id=? AND significance_rank >= ?
             AND COALESCE(rank_tier,'') != 'duplicate'
             AND COALESCE(announce_state,'pending')='pending'
           ORDER BY significance_rank DESC, id""",
        (profile_id, threshold),
    ).fetchall()
    return [dict(r) for r in rows]


def get_draft_announcements(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """Mutable (draft) announcements for a profile — candidates a pending item may join."""
    rows = conn.execute(
        "SELECT * FROM news_announcements WHERE profile_id=? AND COALESCE(status,'draft')!='done' ORDER BY id",
        (profile_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_done_announcements(conn: sqlite3.Connection, profile_id: int) -> List[Dict[str, Any]]:
    """Frozen (published) announcements — never regenerated, but may gain post-publish sources."""
    rows = conn.execute(
        "SELECT * FROM news_announcements WHERE profile_id=? AND status='done' ORDER BY id",
        (profile_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_announcement(
    conn: sqlite3.Connection, profile_id: int, run_id: int, topic_label: str,
    title: str, rcm_json: str, first_published: str,
    source_links: list, item_ids: list,
) -> int:
    """Insert a new draft announcement. Returns its id."""
    cur = conn.execute(
        """INSERT INTO news_announcements(run_id, profile_id, topic_label, title,
                announcement_md, announcement_rcm_json, first_published,
                source_links_json, item_ids_json, status)
           VALUES(?,?,?,?,?,?,?,?,?,'draft')""",
        (run_id, profile_id, topic_label, title, "", rcm_json, first_published,
         json.dumps(source_links or []), json.dumps(item_ids or [])),
    )
    return int(cur.lastrowid)


def update_announcement_content(
    conn: sqlite3.Connection, announcement_id: int, title: str, rcm_json: str,
    source_links: list, item_ids: list, first_published: str | None = None,
) -> None:
    """Regenerate a draft announcement's title/body/membership (never call on 'done')."""
    conn.execute(
        """UPDATE news_announcements
           SET title=?, announcement_rcm_json=?, source_links_json=?, item_ids_json=?,
               first_published=COALESCE(?, first_published)
           WHERE id=?""",
        (title, rcm_json, json.dumps(source_links or []), json.dumps(item_ids or []),
         first_published, announcement_id),
    )


def update_announcement_title(conn: sqlite3.Connection, announcement_id: int, title: str) -> None:
    """Inline title override from the Announcement tab."""
    with conn:
        conn.execute(
            "UPDATE news_announcements SET title=? WHERE id=?", (title, announcement_id)
        )


def append_item_to_announcement(
    conn: sqlite3.Connection, announcement_id: int, item_id: int, added_after_publish: bool
) -> None:
    """Add one item id to an announcement's item_ids_json (dedup); mark post-publish if frozen."""
    row = conn.execute(
        "SELECT item_ids_json FROM news_announcements WHERE id=?", (announcement_id,)
    ).fetchone()
    try:
        ids = json.loads(row["item_ids_json"]) if row else []
    except Exception:
        ids = []
    if item_id not in ids:
        ids.append(item_id)
    conn.execute(
        "UPDATE news_announcements SET item_ids_json=? WHERE id=?",
        (json.dumps(ids), announcement_id),
    )
    conn.execute(
        "UPDATE news_items SET announcement_id=?, announce_state='assigned', added_after_publish=? WHERE id=?",
        (announcement_id, 1 if added_after_publish else 0, item_id),
    )


def set_item_assigned(conn: sqlite3.Connection, item_id: int, announcement_id: int) -> None:
    conn.execute(
        "UPDATE news_items SET announce_state='assigned', announcement_id=? WHERE id=?",
        (announcement_id, item_id),
    )


def mark_items_pending(conn: sqlite3.Connection, item_ids: List[int]) -> None:
    """Flip items back to 'pending' and detach them from any DRAFT announcement.

    Items attached to a 'done' announcement are NOT detached (frozen record stays intact).
    """
    if not item_ids:
        return
    with conn:
        for iid in item_ids:
            row = conn.execute(
                """SELECT a.id, a.status FROM news_announcements a
                   JOIN news_items i ON i.announcement_id = a.id WHERE i.id=?""",
                (iid,),
            ).fetchone()
            if row and row["status"] == "done":
                # Keep membership in the frozen announcement; just re-evaluate.
                conn.execute(
                    "UPDATE news_items SET announce_state='pending' WHERE id=?", (iid,)
                )
            else:
                conn.execute(
                    "UPDATE news_items SET announce_state='pending', announcement_id=NULL WHERE id=?",
                    (iid,),
                )



def save_announcement_rcm(conn: sqlite3.Connection, announcement_id: int, rcm_json_str: str) -> None:
    """v3.6: persist the AI-filled RCM template JSON (called once on first Preview click)."""
    with conn:
        conn.execute(
            "UPDATE news_announcements SET announcement_rcm_json=? WHERE id=?",
            (rcm_json_str, announcement_id),
        )


def reset_review_data(
    conn: sqlite3.Connection, profile_id: Optional[int] = None
) -> Dict[str, int]:
    if profile_id is not None:
        run_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM runs WHERE profile_id=?", (profile_id,)
            ).fetchall()
        ]
    else:
        run_ids = [r[0] for r in conn.execute("SELECT id FROM runs").fetchall()]

    deleted_announcements = 0
    deleted_items = 0
    deleted_runs = 0

    # news_announcements is linked to runs via run_id
    if run_ids:
        placeholders = ",".join("?" * len(run_ids))
        deleted_announcements = conn.execute(
            f"DELETE FROM news_announcements WHERE run_id IN ({placeholders})", run_ids
        ).rowcount

    # news_items is scoped directly by profile_id (no run_id column)
    if profile_id is not None:
        deleted_items = conn.execute(
            "DELETE FROM news_items WHERE profile_id=?", (profile_id,)
        ).rowcount
    else:
        deleted_items = conn.execute("DELETE FROM news_items").rowcount

    if run_ids:
        placeholders = ",".join("?" * len(run_ids))
        deleted_runs = conn.execute(
            f"DELETE FROM runs WHERE id IN ({placeholders})", run_ids
        ).rowcount

    # Clear each URL source's last_successful_fetch so the next run starts from a
    # clean full window instead of a stale delta anchor (otherwise re-runs after a
    # reset fetch "since last fetch" and return nothing).
    if profile_id is not None:
        cleared_sources = conn.execute(
            "UPDATE url_sources SET last_successful_fetch=NULL WHERE profile_id=?",
            (profile_id,),
        ).rowcount
    else:
        cleared_sources = conn.execute(
            "UPDATE url_sources SET last_successful_fetch=NULL"
        ).rowcount

    return {
        "runs": deleted_runs,
        "news_items": deleted_items,
        "news_announcements": deleted_announcements,
        "url_sources_reset": cleared_sources,
    }
