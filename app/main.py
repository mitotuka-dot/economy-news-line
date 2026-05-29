from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import load_settings
from app.db import (
    connect,
    get_past_average_score,
    init_db,
    mark_notified,
    save_tweet,
    upsert_account,
    was_notified,
)
from app.following import load_watchlist, resolve_usernames
from app.line_client import LineClient, format_notification
from app.relevance import calculate_relevance_score, passes_final_filter
from app.reply_generator import ReplyGenerator
from app.scoring import calculate_engagement_score, is_growing, parse_x_datetime
from app.tweet_fetcher import fetch_recent_tweets
from app.x_client import XApiError, XClient


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOG = logging.getLogger(__name__)


def build_x_url(username: str, tweet_id: str) -> str:
    return f"https://x.com/{username}/status/{tweet_id}"


def run() -> int:
    settings = load_settings(validate=True)
    x_client = XClient(settings.x_bearer_token, timeout=settings.request_timeout)
    reply_generator = ReplyGenerator(
        settings.openai_api_key,
        settings.openai_model,
        use_openai=settings.use_openai,
    )
    line_client = LineClient(
        settings.line_channel_access_token, settings.line_user_id, settings.dry_run
    )

    usernames = load_watchlist(settings.watchlist_path)
    LOG.info("Loaded %d watchlist accounts", len(usernames))
    if not usernames:
        LOG.info("No watchlist accounts found. Nothing to do.")
        return 0

    try:
        accounts = resolve_usernames(x_client, usernames)
    except XApiError as exc:
        if exc.status_code == 402:
            LOG.error(
                "X API credits are depleted. Add credits or enable billing in X Developer Portal."
            )
            return 0
        LOG.error("Failed to resolve usernames via X API: %s", exc)
        return 1

    candidates: list[dict] = []
    with connect(settings.db_path) as conn:
        init_db(conn)
        for account in accounts:
            upsert_account(
                conn,
                account["user_id"],
                account["username"],
                account["name"],
                account["category"],
            )
            try:
                tweets = fetch_recent_tweets(x_client, account["user_id"], hours=6)
            except XApiError as exc:
                LOG.warning("Failed to fetch tweets for @%s: %s", account["username"], exc)
                continue

            for raw in tweets:
                metrics = raw.get("public_metrics", {})
                tweet_id = raw["id"]
                engagement_score = calculate_engagement_score(metrics)
                relevance_score = calculate_relevance_score(raw.get("text", ""), raw.get("entities"))
                past_average = get_past_average_score(conn, account["username"], tweet_id)
                growing, growing_reason = is_growing(
                    account["category"],
                    engagement_score,
                    raw["created_at"],
                    past_average,
                    now=datetime.now(timezone.utc),
                )
                tweet = {
                    "tweet_id": tweet_id,
                    "user_id": account["user_id"],
                    "username": account["username"],
                    "category": account["category"],
                    "text": raw.get("text", ""),
                    "created_at": raw["created_at"],
                    "like_count": int(metrics.get("like_count", 0)),
                    "retweet_count": int(metrics.get("retweet_count", 0)),
                    "reply_count": int(metrics.get("reply_count", 0)),
                    "quote_count": int(metrics.get("quote_count", 0)),
                    "engagement_score": engagement_score,
                    "relevance_score": relevance_score,
                    "x_url": build_x_url(account["username"], tweet_id),
                    "growing_reason": growing_reason,
                    "created_dt": parse_x_datetime(raw["created_at"]),
                }
                save_tweet(conn, tweet)
                if was_notified(conn, tweet_id):
                    continue
                if not growing:
                    continue
                passes, reason = passes_final_filter(
                    category=account["category"],
                    relevance_score=relevance_score,
                    reply_count=tweet["reply_count"],
                    quote_count=tweet["quote_count"],
                    text=tweet["text"],
                )
                if not passes:
                    LOG.info("Skip @%s %s: %s", account["username"], tweet_id, reason)
                    continue
                candidates.append(tweet)

        LOG.info("Found %d candidate tweets before AI filtering", len(candidates))
        enriched: list[dict] = []
        for tweet in candidates:
            ai = reply_generator.generate(tweet)
            if ai["reply_priority"] not in {"S", "A"}:
                LOG.info("AI skipped @%s %s with priority B", tweet["username"], tweet["tweet_id"])
                continue
            tweet["ai"] = ai
            enriched.append(tweet)

        priority_rank = {"S": 0, "A": 1}
        enriched.sort(
            key=lambda item: (
                priority_rank.get(item["ai"]["reply_priority"], 9),
                -item["relevance_score"],
                -item["engagement_score"],
                -item["created_dt"].timestamp(),
            )
        )
        selected = enriched[: settings.max_notifications]
        if not selected:
            LOG.info("No LINE notifications to send.")
            return 0

        messages = [format_notification(item) for item in selected]
        line_client.send_notifications(messages)

        if settings.dry_run:
            LOG.info("DRY_RUN=true, not marking tweets as notified.")
        else:
            for item in selected:
                mark_notified(
                    conn,
                    item["tweet_id"],
                    item["ai"]["reply_priority"],
                    item["engagement_score"],
                    item["relevance_score"],
                )
    LOG.info("Done. sent_or_previewed=%d", len(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
