from __future__ import annotations

import logging
from pathlib import Path

from app.x_client import XApiError, XClient


LOG = logging.getLogger(__name__)

CATEGORIES = {
    "FAST_MARKET": {
        "xringx", "nicosokufx", "noatake1127", "aryarya", "marketmaker7",
        "goto_finance", "marikomabuchi",
    },
    "BIG_INFLUENCER": {
        "tesuta001", "cissan_9984", "imuvill", "kabu_st0ck", "yurumazu",
    },
    "ANALYSIS_INVESTOR": {
        "kenichishimada2", "2okutameo", "motohake", "investorduke", "deg_2020", "shiho_312",
    },
    "ENTERTAINMENT_MARKET": {
        "gihuboy", "entrypostman", "txjmdagjmwtjm",
    },
}


def normalize_username(value: str) -> str:
    return value.strip().lstrip("@").lower()


def category_for_username(username: str) -> str:
    normalized = normalize_username(username)
    for category, usernames in CATEGORIES.items():
        if normalized in usernames:
            return category
    return "ANALYSIS_INVESTOR"


def load_watchlist(path: str = "watchlist.txt") -> list[str]:
    usernames: list[str] = []
    seen: set[str] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        clean = normalize_username(line.split("#", 1)[0])
        if not clean or clean == "news9111":
            continue
        if clean not in seen:
            seen.add(clean)
            usernames.append(clean)
    return usernames


def resolve_usernames(client: XClient, usernames: list[str]) -> list[dict]:
    if not usernames:
        return []
    try:
        payload = client.get(
            "/users/by",
            params={
                "usernames": ",".join(usernames),
                "user.fields": "id,name,username",
            },
        )
    except XApiError as exc:
        if exc.status_code != 500:
            raise
        LOG.warning("Bulk username lookup failed with 500. Falling back to single lookups.")
        return resolve_usernames_one_by_one(client, usernames)
    users = []
    for item in payload.get("data", []):
        username = normalize_username(item["username"])
        users.append(
            {
                "user_id": item["id"],
                "username": username,
                "name": item.get("name", ""),
                "category": category_for_username(username),
            }
        )
    errors = payload.get("errors", [])
    if errors:
        LOG.warning("Some usernames could not be resolved: %s", errors)
    return users


def resolve_usernames_one_by_one(client: XClient, usernames: list[str]) -> list[dict]:
    users = []
    for username in usernames:
        payload = client.get(
            f"/users/by/username/{username}",
            params={"user.fields": "id,name,username"},
        )
        item = payload.get("data")
        if not item:
            LOG.warning("Username could not be resolved: %s", username)
            continue
        normalized = normalize_username(item["username"])
        users.append(
            {
                "user_id": item["id"],
                "username": normalized,
                "name": item.get("name", ""),
                "category": category_for_username(normalized),
            }
        )
    return users


def fetch_following_usernames(client: XClient, x_user_id: str, limit: int = 1000) -> list[str]:
    try:
        payload = client.get(
            f"/users/{x_user_id}/following",
            params={"max_results": min(limit, 1000), "user.fields": "username"},
        )
    except XApiError as exc:
        LOG.warning("Failed to fetch following list. watchlist.txt will still be used: %s", exc)
        return []
    return [normalize_username(item["username"]) for item in payload.get("data", [])]
