from __future__ import annotations

from datetime import datetime, timezone


CATEGORY_RULES = {
    "FAST_MARKET": {
        "thresholds": [(0.5, 30), (1, 60), (3, 120), (6, 200)],
        "avg_multiplier": 1.8,
    },
    "BIG_INFLUENCER": {
        "thresholds": [(0.5, 150), (1, 300), (3, 700), (6, 1200)],
        "avg_multiplier": 2.2,
    },
    "ANALYSIS_INVESTOR": {
        "thresholds": [(0.5, 40), (1, 80), (3, 180), (6, 300)],
        "avg_multiplier": 2.0,
    },
    "ENTERTAINMENT_MARKET": {
        "thresholds": [(1, 80), (3, 200), (6, 400)],
        "avg_multiplier": 2.5,
    },
}


def calculate_engagement_score(metrics: dict) -> int:
    return int(
        metrics.get("like_count", 0)
        + metrics.get("retweet_count", 0) * 2
        + metrics.get("reply_count", 0) * 3
        + metrics.get("quote_count", 0) * 4
    )


def parse_x_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def age_hours(created_at: str, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    created = parse_x_datetime(created_at)
    return max((now - created).total_seconds() / 3600, 0)


def is_growing(
    category: str,
    engagement_score: int,
    created_at: str,
    past_average: float | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    rules = CATEGORY_RULES.get(category, CATEGORY_RULES["ANALYSIS_INVESTOR"])
    hours = age_hours(created_at, now)
    for max_hours, threshold in rules["thresholds"]:
        if hours <= max_hours and engagement_score >= threshold:
            return True, f"absolute:{max_hours}h:{threshold}"
    if past_average and past_average > 0:
        required = past_average * rules["avg_multiplier"]
        if engagement_score >= required:
            return True, f"past_average:{rules['avg_multiplier']}x"
    return False, "below_threshold"
