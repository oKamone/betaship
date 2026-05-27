#!/usr/bin/env python3
"""
Betaship エンゲージメント確認・方針転換スクリプト
- Threads APIで過去7日間の投稿エンゲージメントを取得
- パターン別に集計して伸びた/伸びなかったを判定
- Claude APIで分析→style_guide.jsonを自動更新
週1回（木曜 9:00 JST）
"""
import os, json, requests
from anthropic import Anthropic
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN")
THREADS_USER_ID      = os.getenv("THREADS_USER_ID")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")

LOG_FILE         = BASE_DIR / "posted_log.json"
STYLE_GUIDE      = BASE_DIR / "style_guide.json"
ENGAGEMENT_LOG   = BASE_DIR / "engagement_log.json"


# ── Threadsエンゲージメント取得 ──────────────────────────────────

def fetch_recent_posts() -> list:
    """過去7日間の投稿一覧を取得。"""
    base  = "https://graph.threads.net/v1.0"
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    resp = requests.get(
        f"{base}/{THREADS_USER_ID}/threads",
        params={
            "fields": "id,text,timestamp",
            "since": since,
            "access_token": THREADS_ACCESS_TOKEN,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def fetch_insights(media_id: str) -> dict:
    """投稿ごとのエンゲージメントを取得。"""
    base = "https://graph.threads.net/v1.0"
    resp = requests.get(
        f"{base}/{media_id}/insights",
        params={
            "metric": "likes,replies,reposts,quotes,views",
            "access_token": THREADS_ACCESS_TOKEN,
        },
        timeout=15,
    )
    if not resp.ok:
        return {}
    data = resp.json().get("data", [])
    return {item["name"]: item.get("values", [{}])[0].get("value", 0) for item in data}


# ── ログとの突合 ──────────────────────────────────────────────────

def load_log() -> list:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    return []

def load_engagement_log() -> list:
    if ENGAGEMENT_LOG.exists():
        return json.loads(ENGAGEMENT_LOG.read_text(encoding="utf-8"))
    return []

def save_engagement_log(data: list):
    ENGAGEMENT_LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 方針転換分析（Claude API）────────────────────────────────────

def analyze_and_update_guide(records: list):
    """エンゲージメントデータを分析してstyle_guide.jsonを更新。"""
    if not records:
        print("分析対象データなし。スキップ。")
        return

    # パターン別スコア集計（エンゲージメント指標）
    pattern_scores: dict[str, list[int]] = {}
    for r in records:
        name  = r.get("angle", "unknown")
        score = r.get("likes", 0) + r.get("replies", 0) * 2 + r.get("reposts", 0) * 3
        pattern_scores.setdefault(name, []).append(score)

    summary = {
        name: {
            "avg_score": round(sum(scores) / len(scores), 1),
            "count": len(scores),
        }
        for name, scores in pattern_scores.items()
    }

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""以下はBetashipのSNS投稿パターン別エンゲージメントスコアです。
スコア = いいね + リプライ×2 + リポスト×3

{json.dumps(summary, ensure_ascii=False, indent=2)}

これを踏まえて、次週以降の投稿方針をJSON形式で出力してください。

出力形式（JSONのみ。説明不要）:
{{
  "top_patterns": ["伸びたパターン名（最大3つ）"],
  "avoid_patterns": ["伸びなかったパターン名（スコア0かつ2回以上試したもの）"],
  "tone_notes": "次回以降のトーン調整指示を1〜2文で"
}}"""
        }]
    )

    try:
        raw = resp.content[0].text.strip()
        # コードブロックが含まれる場合に除去
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        guide_update = json.loads(raw)
    except Exception as e:
        print(f"Claude応答のパース失敗: {e}\n{resp.content[0].text}")
        return

    # style_guide.json 更新
    guide = {}
    if Path(STYLE_GUIDE).exists():
        guide = json.loads(Path(STYLE_GUIDE).read_text(encoding="utf-8"))

    history = guide.get("history", [])
    history.append({
        "updated_at": datetime.now().isoformat(),
        "summary": summary,
        "applied": guide_update,
    })

    guide.update({
        "top_patterns":    guide_update.get("top_patterns", []),
        "avoid_patterns":  guide_update.get("avoid_patterns", []),
        "tone_notes":      guide_update.get("tone_notes", ""),
        "updated_at":      datetime.now().isoformat(),
        "history":         history[-12:],  # 直近12週分だけ保持
    })

    Path(STYLE_GUIDE).write_text(json.dumps(guide, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"style_guide.json 更新完了")
    print(f"  top:   {guide['top_patterns']}")
    print(f"  avoid: {guide['avoid_patterns']}")
    print(f"  tone:  {guide['tone_notes']}")


# ── メイン ────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] エンゲージメント確認開始")

    post_log   = load_log()
    eng_log    = load_engagement_log()
    already_checked = {e["threads_media_id"] for e in eng_log}

    # Threadsの投稿一覧取得
    try:
        posts = fetch_recent_posts()
    except Exception as e:
        print(f"Threads API取得失敗: {e}")
        return

    new_records = []
    for post in posts:
        mid = post["id"]
        if mid in already_checked:
            continue

        # posted_logから角度名を逆引き
        angle_name = "unknown"
        for entry in post_log:
            if entry.get("threads_media_id") == mid:
                angle_name = entry.get("angle", "unknown")
                break

        insights = fetch_insights(mid)
        record = {
            "threads_media_id": mid,
            "angle":   angle_name,
            "text":    post.get("text", ""),
            "checked_at": datetime.now().isoformat(),
            **insights,
        }
        new_records.append(record)
        print(f"  {angle_name}: likes={insights.get('likes',0)} replies={insights.get('replies',0)} reposts={insights.get('reposts',0)}")

    if not new_records:
        print("新規チェック対象なし。")
        return

    eng_log.extend(new_records)
    save_engagement_log(eng_log)
    print(f"{len(new_records)}件をengagement_log.jsonに保存")

    # 直近4週分のデータで方針更新
    four_weeks_ago = (datetime.now() - timedelta(weeks=4)).isoformat()
    recent = [r for r in eng_log if r.get("checked_at", "") >= four_weeks_ago]
    analyze_and_update_guide(recent)


if __name__ == "__main__":
    main()
