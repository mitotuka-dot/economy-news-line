from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.scoring import parse_x_datetime
from app.x_client import XClient


def fetch_recent_tweets(client: XClient, user_id: str, hours: int = 6) -> list[dict]:
    payload = client.get(
        f"/users/{user_id}/tweets",
        params={
            "max_results": 5,
            "exclude": "replies,retweets",
            "tweet.fields": "created_at,public_metrics,author_id,conversation_id,lang,entities",
        },
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    tweets = []
    for tweet in payload.get("data", []):
        created_at = parse_x_datetime(tweet["created_at"])
        if created_at < cutoff:
            continue
        if tweet.get("lang") not in {"ja", "en"}:
            continue
        tweets.append(tweet)
    return tweets
