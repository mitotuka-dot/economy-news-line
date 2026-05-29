from __future__ import annotations

import re


HIGH_VALUE_KEYWORDS = [
    "日本株", "米国株", "決算", "上方修正", "下方修正", "日銀", "金利", "為替", "ドル円",
    "CPI", "FOMC", "NVIDIA", "半導体", "AI", "データセンター", "電線", "光通信", "冷却",
    "受注", "営業利益", "PER", "PBR", "高配当", "グロース", "バリュー",
]

INTEREST_KEYWORDS = [
    "フジクラ", "古河電工", "住友電工", "フルヤ金属", "ディスコ", "レーザーテック",
    "アドバンテスト", "ファナック", "安川電機", "キオクシア", "イビデン", "太陽誘電",
    "住友金属鉱山", "三井金属", "SBI", "D-Wave", "QBTS",
]

MARKET_TERMS = ["相場", "株", "投資", "為替", "金利", "決算", "半導体", "AI"]
NEWS_URL_RE = re.compile(r"https?://\S*(?:news|ir|tdnet|pdf|release|kabutan|nikkei|reuters)\S*", re.I)
TICKER_RE = re.compile(r"(?<![A-Za-z0-9])(?:[A-Z]{2,5}|\d{4}[A-Z]?)(?![A-Za-z0-9])")

EXCLUDE_TERMS = [
    "炎上", "晒し", "詐欺", "詐欺注意", "拡散希望", "許せない", "個人攻撃",
    "売れ", "買え", "絶対買い", "絶対売り", "爆益自慢", "政治家", "政党",
]

DAILY_ONLY_TERMS = ["おはよう", "ランチ", "飲み会", "旅行", "家族", "眠い", "筋トレ"]


def _contains_any(text: str, words: list[str]) -> bool:
    lower = text.lower()
    return any(word.lower() in lower for word in words)


def calculate_relevance_score(text: str, entities: dict | None = None) -> int:
    if not _contains_any(text, MARKET_TERMS + HIGH_VALUE_KEYWORDS + INTEREST_KEYWORDS):
        return 0
    score = 0
    if _contains_any(text, HIGH_VALUE_KEYWORDS):
        score += 20
    if _contains_any(text, INTEREST_KEYWORDS):
        score += 30
    urls = (entities or {}).get("urls", [])
    expanded_urls = " ".join(url.get("expanded_url", "") for url in urls if isinstance(url, dict))
    if NEWS_URL_RE.search(text) or NEWS_URL_RE.search(expanded_urls):
        score += 20
    if TICKER_RE.search(text):
        score += 10
    return score


def has_high_flame_risk(text: str) -> bool:
    return _contains_any(text, EXCLUDE_TERMS)


def should_exclude_post(text: str) -> tuple[bool, str]:
    if has_high_flame_risk(text):
        return True, "high_flame_or_advice_risk"
    if _contains_any(text, DAILY_ONLY_TERMS) and not _contains_any(text, MARKET_TERMS):
        return True, "daily_only"
    if len(text.strip()) < 8:
        return True, "too_short"
    return False, ""


def passes_final_filter(
    *,
    category: str,
    relevance_score: int,
    reply_count: int,
    quote_count: int,
    text: str,
) -> tuple[bool, str]:
    excluded, reason = should_exclude_post(text)
    if excluded:
        return False, reason
    if relevance_score < 20:
        return False, "low_relevance"
    if category == "FAST_MARKET" and relevance_score >= 40:
        return True, "fast_market_exception"
    if reply_count + quote_count < 1:
        return False, "no_reply_or_quote"
    return True, "ok"
