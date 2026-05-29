from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI


LOG = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは、30代サラリーマン投資家のX運用を支援するSNS編集者です。
ユーザーは「会社員でも、経済と株を味方につければ人生は変えられる」という考えを広めたい人です。
経済ニュースや株式市場の話を、初心者にもわかりやすく、少しユーモアを交えて解説するスタイルです。
以下の投稿に対して、自然に会話へ参加できるリプ案を3つ作ってください。
リプは120字以内を基本にしてください。
断定、煽り、投資助言、過度な買い煽り・売り煽りは避けてください。
銘柄を出す場合は、あくまで連想や注目ポイントとして表現してください。
炎上リスクが高い場合や、リプする価値が低い場合は reply_priority を B にしてください。

出力は必ずJSON形式にしてください。

{
  "reply_priority": "S or A or B",
  "recommended_reason": "リプする価値がある理由を1行",
  "why_trending": "なぜ伸びているかを1〜2行",
  "reply_1": "真面目な投資家向けリプ",
  "reply_2": "居酒屋レベルでわかるユーモア系リプ",
  "reply_3": "銘柄・セクター連想リプ"
}
"""

FALLBACK = {
    "reply_priority": "B",
    "recommended_reason": "AI生成に失敗したため、手動確認を優先してください。",
    "why_trending": "反応数と関連キーワードから注目度はありますが、内容確認が必要です。",
    "reply_1": "この材料、短期の反応だけでなく次の決算や業績見通しまで見ておきたいですね。",
    "reply_2": "相場って一つ材料が出ると、一気に空気が変わるのが早いですね。",
    "reply_3": "関連セクターまで連想が広がりそうなので、周辺銘柄の反応も見ておきたいです。",
}


def _parse_json(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(content[start : end + 1])
    result = FALLBACK | data
    if result.get("reply_priority") not in {"S", "A", "B"}:
        result["reply_priority"] = "B"
    return result


class ReplyGenerator:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, tweet: dict) -> dict[str, Any]:
        user_prompt = f"""
投稿者: @{tweet['username']}
カテゴリ: {tweet['category']}
投稿内容:
{tweet['text']}

反応:
いいね {tweet['like_count']} / RP {tweet['retweet_count']} / リプ {tweet['reply_count']} / 引用 {tweet['quote_count']}
engagement_score: {tweet['engagement_score']}
relevance_score: {tweet['relevance_score']}
投稿URL: {tweet['x_url']}
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
            )
            content = response.choices[0].message.content or "{}"
            return _parse_json(content)
        except Exception as exc:  # noqa: BLE001
            LOG.exception("OpenAI reply generation failed: %s", exc)
            return dict(FALLBACK)
