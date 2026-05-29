from __future__ import annotations

import logging
from textwrap import wrap

import requests


LOG = logging.getLogger(__name__)
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def format_notification(item: dict) -> str:
    ai = item["ai"]
    return f"""【返信優先度】{ai['reply_priority']}
【おすすめ理由】
{ai['recommended_reason']}

【伸びてる投稿】
アカウント: @{item['username']}
カテゴリ: {item['category']}
投稿内容:
{item['text']}

反応:
いいね {item['like_count']} / RP {item['retweet_count']} / リプ {item['reply_count']} / 引用 {item['quote_count']}
スコア: {item['engagement_score']}
関連度: {item['relevance_score']}

投稿URL:
{item['x_url']}

【なぜ伸びてる？】
{ai['why_trending']}

【リプ案① 真面目】
{ai['reply_1']}

【リプ案② 居酒屋解説】
{ai['reply_2']}

【リプ案③ 銘柄・セクター連想】
{ai['reply_3']}"""


class LineClient:
    def __init__(self, channel_access_token: str, user_id: str, dry_run: bool) -> None:
        self.channel_access_token = channel_access_token
        self.user_id = user_id
        self.dry_run = dry_run

    def send_notifications(self, messages: list[str]) -> None:
        for message in messages:
            self._send_text(message)

    def _send_text(self, message: str) -> None:
        chunks = split_message(message)
        for chunk in chunks:
            if self.dry_run:
                print("\n===== DRY_RUN LINE MESSAGE =====")
                print(chunk)
                print("===== END DRY_RUN LINE MESSAGE =====\n")
                continue
            response = requests.post(
                LINE_PUSH_URL,
                headers={
                    "Authorization": f"Bearer {self.channel_access_token}",
                    "Content-Type": "application/json",
                },
                json={"to": self.user_id, "messages": [{"type": "text", "text": chunk}]},
                timeout=20,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"LINE API {response.status_code}: {response.text[:500]}")


def split_message(message: str, limit: int = 4500) -> list[str]:
    if len(message) <= limit:
        return [message]
    return wrap(message, width=limit, replace_whitespace=False, drop_whitespace=False)
