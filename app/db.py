from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    path = Path(db_path)
    if path.parent and str(path.parent) != ".":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            name TEXT,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tweets (
            tweet_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            like_count INTEGER NOT NULL,
            retweet_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            quote_count INTEGER NOT NULL,
            engagement_score INTEGER NOT NULL,
            relevance_score INTEGER NOT NULL,
            fetched_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notified_tweets (
            tweet_id TEXT PRIMARY KEY,
            notified_at TEXT NOT NULL,
            reply_priority TEXT NOT NULL,
            engagement_score INTEGER NOT NULL,
            relevance_score INTEGER NOT NULL
        );
        """
    )


def upsert_account(
    conn: sqlite3.Connection, user_id: str, username: str, name: str, category: str
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO accounts (user_id, username, name, category, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            name = excluded.name,
            category = excluded.category,
            updated_at = excluded.updated_at
        """,
        (user_id, username.lower(), name, category, now, now),
    )


def save_tweet(conn: sqlite3.Connection, tweet: dict) -> None:
    conn.execute(
        """
        INSERT INTO tweets (
            tweet_id, user_id, username, text, created_at,
            like_count, retweet_count, reply_count, quote_count,
            engagement_score, relevance_score, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tweet_id) DO UPDATE SET
            text = excluded.text,
            like_count = excluded.like_count,
            retweet_count = excluded.retweet_count,
            reply_count = excluded.reply_count,
            quote_count = excluded.quote_count,
            engagement_score = excluded.engagement_score,
            relevance_score = excluded.relevance_score,
            fetched_at = excluded.fetched_at
        """,
        (
            tweet["tweet_id"],
            tweet["user_id"],
            tweet["username"].lower(),
            tweet["text"],
            tweet["created_at"],
            tweet["like_count"],
            tweet["retweet_count"],
            tweet["reply_count"],
            tweet["quote_count"],
            tweet["engagement_score"],
            tweet["relevance_score"],
            utc_now_iso(),
        ),
    )


def was_notified(conn: sqlite3.Connection, tweet_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notified_tweets WHERE tweet_id = ?", (tweet_id,)
    ).fetchone()
    return row is not None


def mark_notified(
    conn: sqlite3.Connection,
    tweet_id: str,
    reply_priority: str,
    engagement_score: int,
    relevance_score: int,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO notified_tweets (
            tweet_id, notified_at, reply_priority, engagement_score, relevance_score
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (tweet_id, utc_now_iso(), reply_priority, engagement_score, relevance_score),
    )


def get_past_average_score(
    conn: sqlite3.Connection, username: str, exclude_tweet_id: str | None = None, limit: int = 30
) -> float | None:
    params: list[str | int] = [username.lower()]
    where = "WHERE username = ?"
    if exclude_tweet_id:
        where += " AND tweet_id != ?"
        params.append(exclude_tweet_id)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT engagement_score FROM tweets
        {where}
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    if not rows:
        return None
    return sum(row["engagement_score"] for row in rows) / len(rows)
