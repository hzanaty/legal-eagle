import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta


DB_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), "config.db")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Open a sqlite3 connection with foreign_keys enabled and rows as dict-like objects.
    """
    path = db_path or DB_PATH_DEFAULT
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("PRAGMA foreign_keys = ON;")
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
    Return RSS feeds with per-source config (url, max_lookback_days, last_fetch_date).
    Returns List[Dict] since v2.9.
    """
    rows = conn.execute(
        "SELECT url, COALESCE(max_lookback_days, 7) as max_lookback_days, last_fetch_date FROM rss_feeds WHERE profile_id = ? ORDER BY url",
        (profile_id,)
    ).fetchall()
    return [
        {
            "url": r["url"],
            "max_lookback_days": r["max_lookback_days"],
            "last_fetch_date": r["last_fetch_date"],
        }
        for r in rows
    ]


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

def upsert_rss_feed(conn: sqlite3.Connection, profile_id: int, url: str) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO rss_feeds(profile_id, url) VALUES(?,?)",
            (profile_id, url)
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
                      weight: float = 1.0, notes: Optional[str] = None) -> int:
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO glossary_terms(profile_id, term, lang, category, product, weight, notes)
            VALUES(?,?,?,?,?,?,?)
            """,
            (profile_id, term, lang, category, product, weight, notes)
        )
        row = conn.execute(
            "SELECT id FROM glossary_terms WHERE profile_id=? AND term=? AND lang=? AND IFNULL(product,'')=IFNULL(?, '')",
            (profile_id, term, lang, product)
        ).fetchone()
        return int(row["id"]) if row else -1


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
                    hash_signature=COALESCE(?, hash_signature)
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
                    news_id,
                ),
            )
            return news_id

        # 3) Insert new
        conn.execute(
            """
            INSERT INTO news_items(profile_id, source_type, source_id, url, domain, title, content, published_at, first_seen_at, last_seen_at, hash_signature)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
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
        SELECT id, profile_id, source_type, source_id, url, domain, title, content, published_at, first_seen_at, last_seen_at, hash_signature
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
        "last_successful_fetch": Optional[str], "created_at": str}]
    """
    rows = conn.execute(
        "SELECT url, mode, sample_link, read_more_label, crawl_version, max_depth, allowed_domains, path_filter, max_results, date_scope, last_successful_fetch, created_at FROM url_sources WHERE profile_id = ? ORDER BY url",
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
            "last_successful_fetch": r["last_successful_fetch"],
            "created_at": r["created_at"],
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
    date_scope: str = "all"
) -> None:
    """
    Insert a new url_source or update existing with all parameters including recursive options.
    """
    now_iso = datetime.utcnow().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO url_sources(profile_id, url, mode, sample_link, read_more_label, crawl_version, 
                                   max_depth, allowed_domains, path_filter, max_results, date_scope, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_id, url) DO UPDATE SET
              mode=excluded.mode,
              sample_link=excluded.sample_link,
              read_more_label=excluded.read_more_label,
              crawl_version=excluded.crawl_version,
              max_depth=excluded.max_depth,
              allowed_domains=excluded.allowed_domains,
              path_filter=excluded.path_filter,
              max_results=excluded.max_results,
              date_scope=excluded.date_scope
            """,
            (profile_id, url, mode, sample_link, read_more_label, crawl_version, 
             max_depth, allowed_domains, path_filter, max_results, date_scope, now_iso)
        )


def delete_url_source(conn: sqlite3.Connection, profile_id: int, url: str) -> None:
    """
    Delete a url_source row for a profile.
    """
    with conn:
        conn.execute("DELETE FROM url_sources WHERE profile_id = ? AND url = ?", (profile_id, url))


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
        metric_fields = ["rss_count","tweet_count","url_count","filtered_count","grouped_count","email_status"]
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
