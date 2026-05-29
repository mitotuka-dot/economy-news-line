from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.config import load_settings
from app.db import init_db, mark_notified, was_notified
from app.following import load_watchlist
from app.line_client import LineClient, format_notification
from app.main import run
from app.relevance import calculate_relevance_score
from app.reply_generator import ReplyGenerator, generate_rule_based_reply
from app.scoring import calculate_engagement_score, is_growing


def iso_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def test_watchlist_loads_usernames(tmp_path):
    path = tmp_path / "watchlist.txt"
    path.write_text("@xRINGx\nnews9111\n@aryarya\n@xRINGx\n", encoding="utf-8")
    assert load_watchlist(str(path)) == ["xringx", "aryarya"]


def test_x_user_id_is_optional(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "x-token")
    monkeypatch.delenv("X_USER_ID", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("DRY_RUN", "true")
    settings = load_settings(validate=True)
    assert settings.x_user_id == ""


def test_openai_is_optional(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "x-token")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("USE_OPENAI", "false")
    settings = load_settings(validate=True)
    assert settings.use_openai is False
    assert settings.openai_api_key == ""


def test_engagement_score():
    assert calculate_engagement_score(
        {"like_count": 10, "retweet_count": 2, "reply_count": 3, "quote_count": 4}
    ) == 39


def test_category_growth_thresholds():
    growing, _ = is_growing("FAST_MARKET", 60, iso_hours_ago(0.8))
    assert growing is True
    not_growing, _ = is_growing("BIG_INFLUENCER", 100, iso_hours_ago(0.2))
    assert not_growing is False
    avg_growing, _ = is_growing("ANALYSIS_INVESTOR", 201, iso_hours_ago(5), past_average=100)
    assert avg_growing is True


def test_relevance_score():
    text = "フジクラとNVIDIA、データセンター向け電線需要と決算に注目したい"
    assert calculate_relevance_score(text) >= 50


def test_notified_tweet_is_notified():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    assert was_notified(conn, "1") is False
    mark_notified(conn, "1", "S", 100, 40)
    assert was_notified(conn, "1") is True


def test_line_notification_format_stable():
    message = format_notification(
        {
            "ai": {
                "reply_priority": "S",
                "recommended_reason": "会話に入りやすい材料です。",
                "why_trending": "決算と半導体テーマが重なっています。",
                "reply_1": "決算後の見方が大事ですね。",
                "reply_2": "相場の温度計が一気に上がった感じです。",
                "reply_3": "半導体周辺も見ておきたいです。",
            },
            "username": "xringx",
            "category": "FAST_MARKET",
            "text": "半導体と決算の話",
            "like_count": 10,
            "retweet_count": 2,
            "reply_count": 1,
            "quote_count": 1,
            "engagement_score": 21,
            "relevance_score": 40,
            "x_url": "https://x.com/xringx/status/1",
        }
    )
    assert "【返信優先度】S" in message
    assert "投稿URL:" in message


def test_dry_run_does_not_send_line(monkeypatch, capsys):
    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("requests.post should not be called in DRY_RUN")

    monkeypatch.setattr("app.line_client.requests.post", fake_post)
    client = LineClient("token", "user", dry_run=True)
    client.send_notifications(["hello"])
    assert called is False
    assert "DRY_RUN LINE MESSAGE" in capsys.readouterr().out


def test_rule_based_reply_keeps_notification_eligible():
    tweet = {
        "text": "NVIDIAと半導体、データセンター需要と決算IRが話題。フジクラも連想されそう",
        "category": "FAST_MARKET",
        "engagement_score": 137,
        "relevance_score": 80,
    }
    result = generate_rule_based_reply(tweet)
    assert result["reply_priority"] == "S"
    assert "半導体" in result["reply_1"]


def test_reply_generator_without_openai_uses_rule_based():
    generator = ReplyGenerator("", "gpt-4.1-mini", use_openai=False)
    result = generator.generate(
        {
            "text": "日銀と金利、ドル円が相場の焦点になっています",
            "category": "FAST_MARKET",
            "engagement_score": 100,
            "relevance_score": 40,
        }
    )
    assert result["reply_priority"] in {"S", "A"}


def test_main_mock_dry_run_filters_b_and_notified(monkeypatch, tmp_path):
    db_path = tmp_path / "radar.db"
    watchlist_path = tmp_path / "watchlist.txt"
    watchlist_path.write_text("@xRINGx\n", encoding="utf-8")
    settings = Settings(
        x_bearer_token="x-token",
        x_user_id="123",
        openai_api_key="openai-key",
        line_channel_access_token="line-token",
        line_user_id="line-user",
        dry_run=True,
        db_path=str(db_path),
        watchlist_path=str(watchlist_path),
    )
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        init_db(conn)
        mark_notified(conn, "already-notified", "S", 200, 40)

    sent_messages: list[str] = []
    now = datetime.now(timezone.utc)

    class FakeReplyGenerator:
        def __init__(self, *args, **kwargs):
            pass

        def generate(self, tweet):
            if tweet["tweet_id"] == "ai-b":
                return {
                    "reply_priority": "B",
                    "recommended_reason": "見送りです。",
                    "why_trending": "反応はありますが会話に入りにくいです。",
                    "reply_1": "見送り",
                    "reply_2": "見送り",
                    "reply_3": "見送り",
                }
            return {
                "reply_priority": "S",
                "recommended_reason": "半導体と決算の文脈で会話に入りやすいです。",
                "why_trending": "反応が強く、リプと引用も付いています。",
                "reply_1": "決算後の見方が大事ですね。",
                "reply_2": "相場の体温が一気に上がる材料ですね。",
                "reply_3": "半導体周辺の連想も見ておきたいです。",
            }

    class FakeLineClient:
        def __init__(self, *args, **kwargs):
            pass

        def send_notifications(self, messages):
            sent_messages.extend(messages)

    def tweet(tweet_id, text, metrics):
        return {
            "id": tweet_id,
            "created_at": (now - timedelta(minutes=20)).isoformat(),
            "text": text,
            "lang": "ja",
            "public_metrics": metrics,
            "entities": {"urls": [{"expanded_url": "https://example.com/ir/news.pdf"}]},
        }

    monkeypatch.setattr("app.main.load_settings", lambda validate=True: settings)
    monkeypatch.setattr(
        "app.main.resolve_usernames",
        lambda client, usernames: [
            {
                "user_id": "u1",
                "username": "xringx",
                "name": "xRING",
                "category": "FAST_MARKET",
            }
        ],
    )
    monkeypatch.setattr(
        "app.main.fetch_recent_tweets",
        lambda client, user_id, hours: [
            tweet(
                "notify-me",
                "NVIDIAと半導体、データセンター需要と決算IRが話題。フジクラも連想されそう",
                {"like_count": 80, "retweet_count": 20, "reply_count": 3, "quote_count": 2},
            ),
            tweet(
                "ai-b",
                "半導体とAIの話題だが、AI判定では見送りにするモック投稿",
                {"like_count": 80, "retweet_count": 20, "reply_count": 3, "quote_count": 2},
            ),
            tweet(
                "already-notified",
                "NVIDIAと半導体、決算IRで既に通知済みのモック投稿",
                {"like_count": 80, "retweet_count": 20, "reply_count": 3, "quote_count": 2},
            ),
        ],
    )
    monkeypatch.setattr("app.main.ReplyGenerator", FakeReplyGenerator)
    monkeypatch.setattr("app.main.LineClient", FakeLineClient)

    assert run() == 0
    assert len(sent_messages) == 1
    message = sent_messages[0]
    assert "【返信優先度】S" in message
    assert "notify-me" in message
    assert "ai-b" not in message
    assert "already-notified" not in message

    # DRY_RUN=true keeps the DB notification state unchanged while still skipping pre-notified tweets.
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert was_notified(conn, "already-notified") is True
        assert was_notified(conn, "notify-me") is False
