#!/usr/bin/env python3
"""
Betaship マーケター自動実行スクリプト
- コンテンツ生成（Claude API + style_guide.json で方針自動反映）
- Threads 全自動投稿（Meta Threads API）
- X 用下書き保存（x_drafts.json に追記、手動投稿用）
週3回（月・水・金 9:00 JST）
"""
import os, json, sys, time, requests
from anthropic import Anthropic
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN")
THREADS_USER_ID      = os.getenv("THREADS_USER_ID")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")
SUPABASE_URL         = os.getenv("BETASHIP_SUPABASE_URL")
SUPABASE_KEY         = os.getenv("BETASHIP_SUPABASE_SERVICE_KEY")

BETASHIP_URL = "https://betaship.web.app/"
LOG_FILE     = BASE_DIR / "posted_log.json"
STYLE_GUIDE  = BASE_DIR / "style_guide.json"
X_DRAFTS     = BASE_DIR / "x_drafts.json"

ANGLES = [
    {"name": "moshimo",           "hint": "Moshimo（もしも）の紹介。思い描いた相手とAIで話せる。相談が苦手な人に向けて。判断されない相手と話す体験。"},
    {"name": "reverie",           "hint": "Reverie（レヴリー）の紹介。気分・場所・天気を伝えるとゲーム・映画・アニメからBGMを提案。1分で試せる。"},
    {"name": "wearld",            "hint": "Wearld（ウェアルド）の紹介。テキストを別の世界観に変換する驚き。深海・廃墟VHS・魔女のノートなど。"},
    {"name": "await",             "hint": "Await（アウェイト）の紹介。会う前に気になる相手のことをAIと話すアプリ。待ち遠しさを育てる体験。"},
    {"name": "platform_user",     "hint": "Betashipというプラットフォームの紹介。登録不要・ログイン不要で今すぐ試せるAIツールが集まっている場所。"},
    {"name": "platform_creator",  "hint": "クリエイター向けBetashipの訴求。AIで作ったツール、APIコストが怖くて公開できていない人向け。Betashipがコスト・課金・配信を全部担う。"},
    {"name": "story",             "hint": "個人で複数のAIツールを作って公開している話。なぜ作るのか、何を目指しているか。作った人間の話。"},
    {"name": "scene",             "hint": "AIツールを使う具体的な場面・シーンの紹介。仕事の合間、眠れない夜、気分転換したいとき、など。"},
    {"name": "fail",              "hint": "AIツールを作るうえで失敗した話・詰まった話のリアル。「うまくいかなかった」という正直な経験談。自虐でも卑下でもなく、淡々と。"},
    {"name": "question",          "hint": "フォロワーへの問いかけ型投稿。「こういうとき何のツール使ってる？」など。返答を促す。宣伝感ゼロで。"},
    {"name": "compare",           "hint": "比較型投稿。「ChatGPTで試すより、こっちの方が向いてるケースがある」など、ユーザーが知ってるものと比較して差を語る。"},
    {"name": "build_in_public",   "hint": "Build in Publicスタイルの進捗報告。今週のUU数・目標・学んだこと・来週やること。数字を正直に出す。"},
    {"name": "making",            "hint": "制作プロセスの公開。コードや技術の話より、「なぜこれを作ろうと思ったか」「どんな感情・体験が原点にあるか」を語る人間的な投稿。"},
]


# ── データ取得 ──────────────────────────────────────────────────

def get_weekly_stats() -> dict:
    """Supabaseから週次統計を取得。取得できない場合はフォールバック値を返す。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"weekly_uu": 0, "total_users": 0, "target_uu": 50}
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        # 過去7日間のユニークユーザー数
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/rpc/get_weekly_uu",
            headers=headers, timeout=5
        )
        if resp.ok:
            return {**resp.json(), "target_uu": 50}
    except Exception:
        pass
    return {"weekly_uu": 0, "total_users": 0, "target_uu": 50}


# ── ログ管理 ─────────────────────────────────────────────────────

def load_log() -> list:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    return []

def save_log(log: list):
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

def load_style_guide() -> dict:
    if STYLE_GUIDE.exists():
        return json.loads(STYLE_GUIDE.read_text(encoding="utf-8"))
    return {"top_patterns": [], "avoid_patterns": [], "tone_notes": ""}


# ── 角度選択 ─────────────────────────────────────────────────────

def next_angle(log: list, guide: dict) -> dict:
    recent_names  = [e.get("angle") for e in log[-11:]]
    avoid         = guide.get("avoid_patterns", [])
    top           = guide.get("top_patterns", [])

    # 優先パターンから未使用を選ぶ
    for name in top:
        if name not in recent_names:
            for a in ANGLES:
                if a["name"] == name:
                    return a

    # 回避パターンを除いた未使用を選ぶ
    for angle in ANGLES:
        if angle["name"] not in recent_names and angle["name"] not in avoid:
            return angle

    # 全部使い切ったら最も古いものへ
    return ANGLES[len(log) % len(ANGLES)]


# ── コンテンツ生成 ────────────────────────────────────────────────

def generate_post(angle: dict, guide: dict, stats: dict) -> str:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    tone_instruction = guide.get("tone_notes") or "話し言葉・フランク・体験を語る感じ・宣伝っぽくしない"

    # Build in Public角度はStats情報を付与
    hint = angle["hint"]
    if angle["name"] == "build_in_public":
        hint += f"\n\n今週のデータ: UU={stats['weekly_uu']}人（目標{stats['target_uu']}人）, 累計ユーザー={stats['total_users']}人"

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Betashipの日本語投稿（X / Threads 両用）を1つ書いてください。

投稿の角度・ヒント:
{hint}

URL（末尾に必ず含める）: {BETASHIP_URL}

トーン指示（エンゲージメントデータからの学習）:
{tone_instruction}

条件:
- URLを除く本文は80文字以内
- ハッシュタグは #AIツール か #個人開発 のどちらか1つだけ
- URLは最後

本文テキストのみ出力。説明・前置き不要。"""
        }]
    )
    return resp.content[0].text.strip()


# ── Threads投稿 ──────────────────────────────────────────────────

def post_to_threads(text: str) -> str:
    """Threads APIに投稿してmedia_idを返す。"""
    base = "https://graph.threads.net/v1.0"

    # Step 1: コンテナ作成
    r1 = requests.post(
        f"{base}/{THREADS_USER_ID}/threads",
        params={
            "media_type": "TEXT",
            "text": text,
            "access_token": THREADS_ACCESS_TOKEN,
        },
        timeout=15,
    )
    r1.raise_for_status()
    creation_id = r1.json()["id"]

    time.sleep(3)  # 公式推奨の待機

    # Step 2: 公開
    r2 = requests.post(
        f"{base}/{THREADS_USER_ID}/threads_publish",
        params={"creation_id": creation_id, "access_token": THREADS_ACCESS_TOKEN},
        timeout=15,
    )
    r2.raise_for_status()
    media_id = r2.json()["id"]
    return media_id


# ── X下書き保存 ──────────────────────────────────────────────────

def save_x_draft(text: str, angle_name: str):
    drafts = []
    if X_DRAFTS.exists():
        drafts = json.loads(X_DRAFTS.read_text(encoding="utf-8"))
    drafts.append({
        "at": datetime.now().isoformat(),
        "angle": angle_name,
        "text": text,
        "posted": False,
    })
    X_DRAFTS.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")


# ── メイン ────────────────────────────────────────────────────────

def main(dry_run: bool = False):
    log   = load_log()
    guide = load_style_guide()
    stats = get_weekly_stats()
    angle = next_angle(log, guide)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 角度: {angle['name']}")

    post_text = generate_post(angle, guide, stats)
    print(f"\n--- 生成されたポスト ---\n{post_text}\n------------------------\n")

    if dry_run:
        print("DRY RUN — Threads投稿・X下書き保存はスキップしました")
        return

    # Threads 全自動投稿
    media_id = post_to_threads(post_text)
    threads_url = f"https://www.threads.net/t/{media_id}"
    print(f"Threads投稿完了: {threads_url}")

    # X 下書き保存（手動投稿用）
    save_x_draft(post_text, angle["name"])
    print(f"X下書き保存完了: {X_DRAFTS}")

    log.append({
        "at": datetime.now().isoformat(),
        "angle": angle["name"],
        "text": post_text,
        "threads_media_id": media_id,
        "threads_url": threads_url,
    })
    save_log(log)


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    main(dry_run=dry)
