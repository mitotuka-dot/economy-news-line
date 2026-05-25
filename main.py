from __future__ import annotations

import argparse
import html
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import requests
import schedule
from dotenv import load_dotenv


load_dotenv()

DB_PATH = os.getenv("DB_PATH", "news_notifications.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
USE_OPENAI = os.getenv("USE_OPENAI", "false").lower() in {"1", "true", "yes", "on"}
NEWS_SOURCE_PRIORITY = os.getenv("NEWS_SOURCE_PRIORITY", "newsapi_jp").lower()
JAPANESE_RSS_ENABLED = os.getenv("JAPANESE_RSS_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
NEWS_API_EVERYTHING_URL = "https://newsapi.org/v2/everything"
NEWS_API_TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
JAPANESE_RSS_FEEDS = [
    ("Yahoo!ニュース 経済", "https://news.yahoo.co.jp/rss/topics/business.xml"),
    ("NHK 経済", "https://www3.nhk.or.jp/rss/news/cat5.xml"),
]
GOOGLE_NEWS_RSS_QUERIES = [
    (
        "Google News 日経検索",
        "site:nikkei.com (日経平均 OR 日銀 OR 金利 OR 半導体 OR AI OR 決算 OR 為替 OR キオクシア OR アドバンテスト OR レーザーテック OR フジクラ)",
    ),
    (
        "Google News Reuters検索",
        "site:reuters.com (Japan stocks OR Bank of Japan OR BOJ OR yen OR semiconductor OR Nvidia OR AI OR rates OR oil OR earnings)",
    ),
    (
        "Google News 市場重要ニュース",
        "(日銀 OR 金融政策 OR 円安 OR 円高 OR 日経平均 OR 半導体 OR 生成AI OR データセンター OR NVIDIA OR キオクシア OR アドバンテスト OR レーザーテック OR フジクラ OR 古河電工)",
    ),
]

MAX_NEWS_PER_RUN = int(os.getenv("MAX_NEWS_PER_RUN", "30"))
MAX_NOTIFICATIONS_PER_RUN = int(os.getenv("MAX_NOTIFICATIONS_PER_RUN", "5"))
NOTIFY_MIN_SCORE = int(os.getenv("NOTIFY_MIN_SCORE", "4"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))

macro_keywords = [
    "Federal Reserve",
    "FRB",
    "FOMC",
    "interest rates",
    "rate cut",
    "rate hike",
    "CPI",
    "inflation",
    "PCE",
    "jobs report",
    "unemployment",
    "GDP",
    "Treasury yields",
    "bond market",
    "yen",
    "dollar",
    "BOJ",
    "Bank of Japan",
    "Nikkei",
    "TOPIX",
    "S&P 500",
    "Nasdaq",
    "oil prices",
    "gold",
    "Hormuz",
    "ホルムズ",
    "インフレ",
    "イラン",
    "イスラエル",
    "停戦",
    "戦争",
    "地政学",
    "米国金利",
    "日銀",
    "金融政策",
    "円安",
    "円高",
    "日経平均",
    "為替",
    "原油",
]

theme_keywords = [
    "AI",
    "ＡＩ",
    "artificial intelligence",
    "generative AI",
    "semiconductor",
    "chip",
    "GPU",
    "data center",
    "HBM",
    "memory",
    "NAND",
    "DRAM",
    "quantum computing",
    "cryptocurrency",
    "Bitcoin",
    "stablecoin",
    "fintech",
    "electric vehicle",
    "EV",
    "autonomous driving",
    "生成AI",
    "半導体",
    "データセンター",
    "量子コンピューター",
    "暗号資産",
]

watchlist = [
    "NVIDIA",
    "NVDA",
    "Microsoft",
    "MSFT",
    "Apple",
    "AAPL",
    "Google",
    "グーグル",
    "Alphabet",
    "GOOGL",
    "GOOG",
    "Amazon",
    "AMZN",
    "Meta",
    "META",
    "Tesla",
    "TSLA",
    "Kioxia",
    "キオクシア",
    "Advantest",
    "アドバンテスト",
    "Lasertec",
    "レーザーテック",
    "Fujikura",
    "フジクラ",
    "Furukawa Electric",
    "古河電気工業",
    "semiconductor equipment",
    "半導体製造装置",
    "光ファイバー",
    "データセンター",
    "電線",
    "AIサーバー",
    "Blackwell",
    "Rubin",
    "TSMC",
    "Samsung",
    "Intel",
    "ASML",
]

japanese_watchlist_aliases = {
    "キオクシア": ["Kioxia", "キオクシア", "285A"],
    "アドバンテスト": ["Advantest", "アドバンテスト", "6857"],
    "レーザーテック": ["Lasertec", "レーザーテック", "6920"],
    "フジクラ": ["Fujikura", "フジクラ", "5803"],
    "古河電気工業": ["Furukawa Electric", "古河電気工業", "5801"],
}

high_impact_terms = [
    "earnings",
    "guidance",
    "forecast",
    "M&A",
    "merger",
    "acquisition",
    "regulation",
    "lawsuit",
    "bankruptcy",
    "downgrade",
    "upgrade",
    "export controls",
    "sanctions",
    "large order",
    "capex",
    "investment",
    "決算",
    "業績予想",
    "上方修正",
    "下方修正",
    "買収",
    "合併",
    "規制",
    "訴訟",
    "破綻",
    "格下げ",
    "大型受注",
    "設備投資",
    "輸出規制",
]

low_quality_terms = [
    "sponsored",
    "advertisement",
    "promoted",
    "rumor",
    "unconfirmed",
    "analyst says",
    "price target",
    "shares edge",
    "shares dip",
    "consensus rating",
    "price momentum",
    "undervalued",
    "value trap",
    "wall street analysts",
    "swot analysis",
    "zacks research",
    "analysts raise",
    "analysts reduce",
    "小幅",
    "噂",
    "観測",
    "広告",
    "PR",
    "目標株価",
    "アナリスト",
    "レーティング",
    "株価予想",
    "買ってたら",
    "買っていれば",
    "今ごろ",
    "チャンス",
    "億円に",
]

trusted_sources = [
    "Reuters",
    "Bloomberg",
    "Associated Press",
    "CNBC",
    "The Wall Street Journal",
    "Financial Times",
    "Nikkei",
    "日本経済新聞",
    "ロイター",
    "ブルームバーグ",
    "NHK",
    "Yahoo!ニュース",
    "東洋経済オンライン",
    "会社四季報オンライン",
    "MarketWatch",
    "Investing.com",
]

PLACEHOLDER_PREFIXES = ("your_", "YOUR_", "ここに")


def configured_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith(PLACEHOLDER_PREFIXES):
        return ""
    return value


@dataclass
class NewsItem:
    title: str
    url: str
    summary: str = ""
    source: str = ""
    published_at: str = ""
    provider: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    score: int
    category: str
    summary_bullets: list[str]
    related_symbols: list[str]
    reason: str = ""


def configure_logging() -> None:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def init_db(db_path: str = DB_PATH) -> None:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                url TEXT,
                title TEXT,
                score INTEGER,
                category TEXT,
                provider TEXT,
                sent_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                url TEXT,
                title TEXT,
                score INTEGER,
                category TEXT,
                provider TEXT,
                seen_at TEXT NOT NULL
            )
            """
        )


def make_fingerprint(item: NewsItem) -> str:
    key = item.url.strip() or item.title.strip().lower()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def is_processed(item: NewsItem, db_path: str = DB_PATH) -> bool:
    fingerprint = make_fingerprint(item)
    with sqlite3.connect(db_path) as conn:
        sent = conn.execute(
            "SELECT 1 FROM sent_news WHERE fingerprint = ? LIMIT 1", (fingerprint,)
        ).fetchone()
        seen = conn.execute(
            "SELECT 1 FROM seen_news WHERE fingerprint = ? LIMIT 1", (fingerprint,)
        ).fetchone()
    return bool(sent or seen)


def mark_seen(item: NewsItem, analysis: AnalysisResult, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO seen_news
                (fingerprint, url, title, score, category, provider, seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                make_fingerprint(item),
                item.url,
                item.title,
                analysis.score,
                analysis.category,
                item.provider,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def mark_sent(item: NewsItem, analysis: AnalysisResult, db_path: str = DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO sent_news
                (fingerprint, url, title, score, category, provider, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                make_fingerprint(item),
                item.url,
                item.title,
                analysis.score,
                analysis.category,
                item.provider,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.execute(
            "DELETE FROM seen_news WHERE fingerprint = ?", (make_fingerprint(item),)
        )


def fetch_alpha_vantage_news(api_key: str) -> list[NewsItem]:
    if not api_key:
        logging.info("ALPHA_VANTAGE_API_KEY is not set. Skipping Alpha Vantage.")
        return []

    params = {
        "function": "NEWS_SENTIMENT",
        "sort": "LATEST",
        "limit": str(MAX_NEWS_PER_RUN),
        "apikey": api_key,
    }
    response = requests.get(
        ALPHA_VANTAGE_URL, params=params, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()

    if "Information" in data or "Note" in data:
        logging.warning("Alpha Vantage response message: %s", data.get("Information") or data.get("Note"))

    feed = data.get("feed", [])
    items: list[NewsItem] = []
    for article in feed:
        items.append(
            NewsItem(
                title=article.get("title", "").strip(),
                url=article.get("url", "").strip(),
                summary=article.get("summary", "").strip(),
                source=article.get("source", "").strip(),
                published_at=article.get("time_published", "").strip(),
                provider="alpha_vantage",
                raw=article,
            )
        )
    return [item for item in items if item.title and item.url]


def fetch_newsapi_news(api_key: str) -> list[NewsItem]:
    if not api_key:
        logging.info("NEWS_API_KEY is not set. Skipping NewsAPI fallback.")
        return []

    since = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(microsecond=0)
    query = (
        '(Federal Reserve OR FOMC OR CPI OR PCE OR "Bank of Japan" OR yen OR '
        'NVIDIA OR Microsoft OR Apple OR Google OR Amazon OR Meta OR Tesla OR '
        'semiconductor OR "data center" OR AI OR "export controls" OR oil)'
    )
    params = {
        "q": query,
        "searchIn": "title,description",
        "language": "en",
        "sortBy": "publishedAt",
        "from": since.isoformat().replace("+00:00", "Z"),
        "pageSize": str(min(MAX_NEWS_PER_RUN, 100)),
        "apiKey": api_key,
    }
    response = requests.get(
        NEWS_API_EVERYTHING_URL, params=params, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "ok":
        logging.warning("NewsAPI everything returned non-ok status: %s", data)
        return fetch_newsapi_top_headlines(api_key)

    return normalize_newsapi_articles(data.get("articles", []), "newsapi_everything")


def fetch_newsapi_japanese_news(api_key: str) -> list[NewsItem]:
    if not api_key:
        logging.info("NEWS_API_KEY is not set. Skipping Japanese NewsAPI.")
        return []

    items: list[NewsItem] = []
    since = (datetime.now(timezone.utc) - timedelta(hours=12)).replace(microsecond=0)
    jp_query = (
        "日銀 OR 金融政策 OR 円安 OR 円高 OR 日経平均 OR TOPIX OR 半導体 OR 生成AI OR "
        "データセンター OR NVIDIA OR エヌビディア OR Microsoft OR Apple OR Tesla OR "
        "キオクシア OR アドバンテスト OR レーザーテック OR フジクラ OR 古河電工 OR "
        "決算 OR 上方修正 OR 下方修正 OR 買収 OR 規制 OR 原油 OR 金利"
    )

    everything_params = {
        "q": jp_query,
        "searchIn": "title,description",
        "language": "ja",
        "sortBy": "publishedAt",
        "from": since.isoformat().replace("+00:00", "Z"),
        "pageSize": str(min(MAX_NEWS_PER_RUN, 100)),
        "apiKey": api_key,
    }
    try:
        response = requests.get(
            NEWS_API_EVERYTHING_URL, params=everything_params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "ok":
            items.extend(
                normalize_newsapi_articles(data.get("articles", []), "newsapi_jp_everything")
            )
        else:
            logging.warning("Japanese NewsAPI everything returned non-ok status: %s", data)
    except Exception:
        logging.exception("Japanese NewsAPI everything fetch failed.")

    top_params = {
        "country": "jp",
        "category": "business",
        "pageSize": str(min(MAX_NEWS_PER_RUN, 100)),
        "apiKey": api_key,
    }
    try:
        response = requests.get(
            NEWS_API_TOP_HEADLINES_URL, params=top_params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "ok":
            items.extend(
                normalize_newsapi_articles(data.get("articles", []), "newsapi_jp_top_headlines")
            )
        else:
            logging.warning("Japanese NewsAPI top-headlines returned non-ok status: %s", data)
    except Exception:
        logging.exception("Japanese NewsAPI top-headlines fetch failed.")

    return prioritize_news_items(dedupe_news_items(items))


def fetch_newsapi_top_headlines(api_key: str) -> list[NewsItem]:
    params = {
        "category": "business",
        "language": "en",
        "pageSize": str(min(MAX_NEWS_PER_RUN, 100)),
        "apiKey": api_key,
    }
    response = requests.get(
        NEWS_API_TOP_HEADLINES_URL, params=params, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "ok":
        logging.warning("NewsAPI top-headlines returned non-ok status: %s", data)
        return []
    return normalize_newsapi_articles(data.get("articles", []), "newsapi_top_headlines")


def normalize_newsapi_articles(articles: list[dict[str, Any]], provider: str) -> list[NewsItem]:
    items: list[NewsItem] = []
    for article in articles:
        source = article.get("source") or {}
        title = (article.get("title") or "").strip()
        url = (article.get("url") or "").strip()
        if not title or not url:
            continue
        items.append(
            NewsItem(
                title=title,
                url=url,
                summary=(article.get("description") or article.get("content") or "").strip(),
                source=(source.get("name") or "").strip(),
                published_at=(article.get("publishedAt") or "").strip(),
                provider=provider,
                raw=article,
            )
        )
    return items


def fetch_japanese_rss_news() -> list[NewsItem]:
    if not JAPANESE_RSS_ENABLED:
        return []

    items: list[NewsItem] = []
    feed_sources = list(JAPANESE_RSS_FEEDS)
    for source_name, query in GOOGLE_NEWS_RSS_QUERIES:
        feed_sources.append(
            (
                source_name,
                "https://news.google.com/rss/search?"
                f"q={quote_plus(query)}&hl=ja&gl=JP&ceid=JP:ja",
            )
        )

    for source_name, feed_url in feed_sources:
        try:
            response = requests.get(feed_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except Exception:
            logging.exception("Japanese RSS fetch failed: %s", feed_url)
            continue

        for item_node in root.findall(".//item"):
            title = get_xml_text(item_node, "title")
            url = get_xml_text(item_node, "link")
            summary = get_xml_text(item_node, "description")
            published_at = get_xml_text(item_node, "pubDate")
            item_source = get_xml_text(item_node, "source")
            display_source = item_source if source_name.startswith("Google News") and item_source else source_name
            if source_name.startswith("Google News"):
                if not contains_japanese(title):
                    continue
                summary = ""
            if not title or not url:
                continue
            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    summary=summary,
                    source=display_source,
                    published_at=published_at,
                    provider="japanese_rss",
                    raw={"feed_url": feed_url, "feed_name": source_name},
                )
            )
    return prioritize_news_items(dedupe_news_items(items))


def get_xml_text(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def contains_japanese(text: str) -> bool:
    return re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text) is not None


def dedupe_news_items(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    deduped: list[NewsItem] = []
    for item in items:
        key = item.url or item.title.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def prioritize_news_items(items: list[NewsItem]) -> list[NewsItem]:
    def source_rank(item: NewsItem) -> int:
        text = f"{item.source} {item.title} {item.url}".lower()
        if "nikkei" in text or "日経" in text:
            return 0
        if "reuters" in text or "ロイター" in text:
            return 0
        if "nhk" in text:
            return 1
        if "yahoo" in text:
            return 2
        return 3

    return sorted(
        items,
        key=lambda item: (
            -keyword_analysis(item).score,
            source_rank(item),
            item.published_at,
        ),
    )


def fetch_news() -> list[NewsItem]:
    alpha_key = configured_env("ALPHA_VANTAGE_API_KEY")
    newsapi_key = configured_env("NEWS_API_KEY")

    if NEWS_SOURCE_PRIORITY in {"japanese", "jp", "rss_jp", "newsapi_jp"}:
        rss_items = fetch_japanese_rss_news()
        if rss_items:
            logging.info("Fetched %s Japanese RSS news items.", len(rss_items))
            return rss_items

    if NEWS_SOURCE_PRIORITY == "newsapi_jp":
        try:
            jp_items = fetch_newsapi_japanese_news(newsapi_key)
            if jp_items:
                logging.info("Fetched %s Japanese news items from NewsAPI.", len(jp_items))
                return jp_items
        except Exception:
            logging.exception("Japanese NewsAPI fetch failed. Falling back to Alpha Vantage.")

    try:
        alpha_items = fetch_alpha_vantage_news(alpha_key)
        if alpha_items:
            logging.info("Fetched %s news items from Alpha Vantage.", len(alpha_items))
            return alpha_items
    except Exception:
        logging.exception("Alpha Vantage fetch failed. Falling back to NewsAPI.")

    try:
        newsapi_items = fetch_newsapi_news(newsapi_key)
        logging.info("Fetched %s news items from NewsAPI.", len(newsapi_items))
        return newsapi_items
    except Exception:
        logging.exception("NewsAPI fetch failed.")
        return []


def text_for_analysis(item: NewsItem) -> str:
    return " ".join(
        part
        for part in [item.title, item.summary, json.dumps(item.raw.get("topics", ""), ensure_ascii=False)]
        if part
    )


def term_matches(text: str, term: str) -> bool:
    if term.isascii() and re.fullmatch(r"[A-Za-z0-9.+-]{1,5}", term):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(term.lower())}(?![A-Za-z0-9])", text.lower()) is not None
    return term.lower() in text.lower()


def contains_any(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term_matches(text, term)]


def detect_related_symbols(text: str) -> list[str]:
    related: list[str] = []
    for term in watchlist:
        if term_matches(text, term) and term not in related:
            related.append(term)
    for canonical, aliases in japanese_watchlist_aliases.items():
        if any(alias.lower() in text.lower() for alias in aliases) and canonical not in related:
            related.append(canonical)
    return related[:12]


def detect_category(text: str) -> str:
    categories = [
        ("米国金利", ["Federal Reserve", "FRB", "FOMC", "rate cut", "rate hike", "Treasury", "CPI", "PCE"]),
        ("日本株", ["Nikkei", "TOPIX", "BOJ", "Bank of Japan", "日銀", "日本株", "日経平均"]),
        ("AI", ["AI", "artificial intelligence", "generative AI", "生成AI"]),
        ("半導体", ["semiconductor", "chip", "GPU", "HBM", "NAND", "DRAM", "半導体"]),
        ("個別株", watchlist),
        ("為替", ["yen", "dollar", "円安", "円高", "為替"]),
        ("金利", ["interest rates", "bond market", "Treasury yields", "金利", "債券"]),
        ("原油・資源", ["oil", "crude", "原油", "ホルムズ", "タンカー", "資源"]),
        ("地政学", ["geopolitical", "war", "sanctions", "tariff", "export controls", "地政学", "制裁", "関税", "イラン", "イスラエル", "停戦", "戦争", "紛争"]),
    ]
    for category, terms in categories:
        if contains_any(text, terms):
            return category
    return "経済"


def keyword_analysis(item: NewsItem) -> AnalysisResult:
    text = text_for_analysis(item)
    matches_macro = contains_any(text, macro_keywords)
    matches_theme = contains_any(text, theme_keywords)
    matches_watch = detect_related_symbols(text)
    matches_high = contains_any(text, high_impact_terms)
    matches_low = contains_any(text, low_quality_terms)
    source_bonus = any(source.lower() in item.source.lower() for source in trusted_sources)

    score = 1
    if matches_macro:
        score = max(score, 3)
    if matches_theme:
        score = max(score, 3)
    if matches_watch:
        score = max(score, 4)
    if matches_high and (matches_macro or matches_theme or matches_watch):
        score = max(score, 4)
    if source_bonus and score >= 3:
        score += 1
    if matches_low:
        score -= 1
    if matches_low and not (matches_macro or matches_theme or matches_watch):
        score = min(score, 2)
    score = min(5, max(1, score))

    category = detect_category(text)
    bullets = build_keyword_summary(item, score, category, matches_watch)
    return AnalysisResult(
        score=score,
        category=category,
        summary_bullets=bullets,
        related_symbols=matches_watch,
        reason="keyword_fallback",
    )


def build_keyword_summary(
    item: NewsItem, score: int, category: str, related_symbols: list[str]
) -> list[str]:
    title = item.title.rstrip("。")
    source = item.source or "ニュースサイト"
    description = clean_summary_text(item.summary)
    related = "、".join(normalize_related_symbols(related_symbols)) if related_symbols else category
    event = description if description else infer_event_from_title(title)
    return [
        f"何が起きたか：{source}が、{event}。",
        f"なぜ重要か：{category}に関係し、重要度は{score}/5です。市場参加者の判断材料になりやすい内容です。",
        f"市場への影響：{market_impact_sentence(category, related_symbols)}関連銘柄・テーマは{related}を中心に確認します。",
        f"次に見る点：{next_watch_point(category, related_symbols)}",
    ]


def clean_summary_text(summary: str) -> str:
    text = html.unescape(summary)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.replace("\n", " ").split())
    for marker in ["[", "…", "..."]:
        if marker in text and len(text) > 120:
            text = text.split(marker)[0].strip()
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
    return text.rstrip("。")


def infer_event_from_title(title: str) -> str:
    normalized = title.strip().rstrip("。")
    patterns = [
        (r"(.+?) 終値初の(.+)", r"\1が終値で初めて\2となりました"),
        (r"(.+?) 終値 (.+?)で最高値を更新", r"\1が終値で\2となり、最高値を更新しました"),
        (r"(.+?)が死去", r"\1が死去したと報じられました"),
        (r"(.+?)へ (.+)", r"\1へ向けた動きとして、\2が報じられました"),
    ]
    for pattern, replacement in patterns:
        if re.search(pattern, normalized):
            return re.sub(pattern, replacement, normalized)
    return f"「{normalized}」というニュースが出ています"


def normalize_related_symbols(symbols: list[str]) -> list[str]:
    aliases = {
        "NVIDIA": "NVDA",
        "Microsoft": "MSFT",
        "Apple": "AAPL",
        "Google": "GOOGL",
        "グーグル": "GOOGL",
        "Alphabet": "GOOGL",
        "Amazon": "AMZN",
        "Meta": "META",
        "Tesla": "TSLA",
    }
    normalized: list[str] = []
    for symbol in symbols:
        value = aliases.get(symbol, symbol)
        if value not in normalized:
            normalized.append(value)
    return normalized


def market_impact_sentence(category: str, related_symbols: list[str]) -> str:
    if category in {"米国金利", "金利"}:
        return "金利・為替・グロース株のバリュエーションに波及する可能性があります。"
    if category == "為替":
        return "輸出株、日本株、米国株の円換算リターンに影響しやすい材料です。"
    if category in {"AI", "半導体"}:
        return "AIインフラ、半導体、データセンター関連の需給や投資テーマに関わります。"
    if category == "日本株":
        return "日経平均、TOPIX、半導体・輸出関連株の地合いに影響する可能性があります。"
    if category == "原油・資源":
        return "原油価格、海運、商社、エネルギー関連株、インフレ期待に波及する可能性があります。"
    if category == "地政学":
        return "原油、為替、金利、リスク資産全体の値動きに波及する可能性があります。"
    if related_symbols:
        return "個別銘柄だけでなく、同業他社や関連テーマにも波及する可能性があります。"
    return "指数、為替、金利、関連セクターの反応を確認したい内容です。"


def next_watch_point(category: str, related_symbols: list[str]) -> str:
    if category in {"米国金利", "金利"}:
        return "米国債利回り、ドル円、FOMC参加者発言、次のCPI/PCEを確認してください。"
    if category == "為替":
        return "ドル円、米日金利差、日銀・FRB発言、輸出株の寄り付き反応を確認してください。"
    if category in {"AI", "半導体"}:
        return "NVIDIA、半導体製造装置、メモリ、データセンター投資への連想買い・売りを確認してください。"
    if category == "日本株":
        return "日経平均先物、TOPIX、半導体株、為替感応株の反応を確認してください。"
    if category == "原油・資源":
        return "WTI/ブレント原油、海上輸送リスク、商社・エネルギー株、為替への波及を確認してください。"
    return "一次情報、決算資料、会社発表、続報の有無を確認してください。"


def analyze_with_openai(item: NewsItem, api_key: str) -> AnalysisResult | None:
    if not api_key:
        return None

    prompt = {
        "title": item.title,
        "summary": item.summary,
        "source": item.source,
        "published_at": item.published_at,
        "url": item.url,
        "watchlist": watchlist,
        "japanese_watchlist_aliases": japanese_watchlist_aliases,
    }
    instructions = (
        "あなたは金融ニュースの編集者です。市場影響を冷静に評価してください。"
        "重要度は1〜5。4以上だけ通知対象です。買い・売りを断定せず、煽らず、"
        "公式発表・決算・大手メディア・規制当局発表を高めに、広告・噂・薄い株価記事を低めにします。"
        "出力はJSONのみ。schema: "
        '{"score": int, "category": str, "summary_bullets": [str, str, str, str], '
        '"related_symbols": [str], "reason": str}'
    )
    payload = {
        "model": OPENAI_MODEL,
        "instructions": instructions,
        "input": "Analyze this news item and return json only:\n"
        + json.dumps(prompt, ensure_ascii=False),
        "temperature": 0.2,
        "max_output_tokens": 900,
        "text": {"format": {"type": "json_object"}},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            OPENAI_RESPONSES_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        output_text = extract_openai_text(data)
        parsed = json.loads(output_text)
        return AnalysisResult(
            score=int(parsed.get("score", 1)),
            category=str(parsed.get("category", "経済")),
            summary_bullets=list(parsed.get("summary_bullets", []))[:4],
            related_symbols=list(parsed.get("related_symbols", []))[:12],
            reason=str(parsed.get("reason", "openai")),
        )
    except Exception:
        logging.exception("OpenAI analysis failed. Using keyword fallback.")
        return None


def extract_openai_text(data: dict[str, Any]) -> str:
    texts: list[str] = []
    for output in data.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text":
                texts.append(content.get("text", ""))
    if not texts:
        raise ValueError("OpenAI response did not contain output_text.")
    return "\n".join(texts)


def analyze_news(item: NewsItem) -> AnalysisResult:
    if not USE_OPENAI:
        return keyword_analysis(item)

    result = analyze_with_openai(item, configured_env("OPENAI_API_KEY"))
    if result:
        if not result.summary_bullets:
            result.summary_bullets = build_keyword_summary(
                item, result.score, result.category, result.related_symbols
            )
        result.score = min(5, max(1, result.score))
        return result
    return keyword_analysis(item)


def format_line_message(item: NewsItem, analysis: AnalysisResult) -> str:
    stars = "★" * analysis.score + "☆" * (5 - analysis.score)
    related = analysis.related_symbols or detect_related_symbols(text_for_analysis(item))
    related_text = "\n".join(f"- {symbol}" for symbol in related) if related else "- 該当なし"
    bullets = "\n".join(f"・{bullet.lstrip('・')}" for bullet in analysis.summary_bullets[:4])

    return (
        "【重要経済ニュース】\n"
        f"重要度：{stars}\n"
        f"カテゴリ：{analysis.category}\n\n"
        "タイトル：\n"
        f"{item.title}\n\n"
        "要約：\n"
        f"{bullets}\n\n"
        "関連銘柄：\n"
        f"{related_text}\n\n"
        "URL：\n"
        f"{item.url}"
    )


def send_line_push(message: str) -> None:
    token = configured_env("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = configured_env("LINE_USER_ID")
    if not token or not user_id:
        logging.warning("LINE credentials are not set. Message was not sent.")
        logging.info("LINE message preview:\n%s", message)
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message[:5000]}],
    }
    response = requests.post(
        LINE_PUSH_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
    )
    if response.status_code >= 400:
        logging.error("LINE push failed: %s %s", response.status_code, response.text)
    response.raise_for_status()


def process_news_once() -> None:
    logging.info("Starting news check.")
    init_db()
    items = fetch_news()
    if not items:
        logging.info("No news items fetched.")
        return

    candidates: list[tuple[NewsItem, AnalysisResult]] = []
    for item in items[:MAX_NEWS_PER_RUN]:
        try:
            if is_processed(item):
                logging.info("Skipping duplicate: %s", item.title)
                continue
            analysis = analyze_news(item)
            candidates.append((item, analysis))
        except Exception:
            logging.exception("Failed to analyze item: %s", item.title)

    candidates.sort(key=notification_sort_key)

    sent_count = 0
    for item, analysis in candidates:
        try:
            if analysis.score >= NOTIFY_MIN_SCORE:
                if sent_count >= MAX_NOTIFICATIONS_PER_RUN:
                    mark_seen(item, analysis)
                    logging.info(
                        "Notification limit reached. Recorded score %s news: %s",
                        analysis.score,
                        item.title,
                    )
                    continue
                message = format_line_message(item, analysis)
                send_line_push(message)
                mark_sent(item, analysis)
                sent_count += 1
                logging.info("Sent score %s news: %s", analysis.score, item.title)
                time.sleep(1)
            else:
                mark_seen(item, analysis)
                logging.info("Recorded non-notified score %s news: %s", analysis.score, item.title)
        except Exception:
            logging.exception("Failed to process item: %s", item.title)

    logging.info("News check finished. Sent %s messages.", sent_count)


def notification_sort_key(candidate: tuple[NewsItem, AnalysisResult]) -> tuple[int, int, str]:
    item, analysis = candidate
    return (-analysis.score, source_priority_rank(item), item.published_at)


def source_priority_rank(item: NewsItem) -> int:
    text = f"{item.source} {item.title} {item.url}".lower()
    if "nikkei" in text or "日本経済新聞" in text or "日経" in text:
        return 0
    if "reuters" in text or "ロイター" in text:
        return 1
    if "nhk" in text:
        return 2
    if "yahoo" in text:
        return 3
    return 4


def send_test_line_message() -> None:
    init_db()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    send_line_push(
        "【重要経済ニュース】\n"
        "重要度：★★★★☆\n"
        "カテゴリ：疎通確認\n\n"
        "タイトル：\n"
        "LINE通知テスト\n\n"
        "要約：\n"
        f"・このメッセージは {timestamp} の疎通確認です。\n"
        "・この通知が届けば LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID は有効です。\n"
        "・次は python3 main.py --once でニュース取得から通知まで確認できます。\n"
        "・常駐実行は python3 main.py です。\n\n"
        "関連銘柄：\n"
        "- 該当なし\n\n"
        "URL：\n"
        "https://developers.line.biz/"
    )


def run_scheduler() -> None:
    process_news_once()
    schedule.every(1).hours.do(process_news_once)
    logging.info("Scheduler started. Running every 1 hour.")
    while True:
        schedule.run_pending()
        time.sleep(30)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Important economy news LINE notifier")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one news check and exit. Useful for GitHub Actions or cron.",
    )
    parser.add_argument(
        "--test-line",
        action="store_true",
        help="Send a LINE test message and exit.",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    if args.test_line:
        send_test_line_message()
    elif args.once:
        process_news_once()
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
