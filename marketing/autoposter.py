#!/usr/bin/env python3
"""
Betaship X自動投稿スクリプト
週3回（月・水・金 9:00 JST）crontab から実行される
crontab: 0 0 * * 1,3,5 /opt/homebrew/bin/python3 /path/to/autoposter.py >> /path/to/cron.log 2>&1
"""
import os, json, sys, tweepy
from anthropic import Anthropic
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

TWITTER_API_KEY      = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET   = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET= os.getenv("TWITTER_ACCESS_SECRET")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")

BETASHIP_URL = "https://betaship.web.app/"
LOG_FILE     = BASE_DIR / "posted_log.json"

# ローテーションする投稿角度（12種）
# 直近11件で重複しないよう管理される
ANGLES = [
    {
        "name": "moshimo",
        "hint": "Moshimo（もしも）の紹介。AIメンターを思考にインストールするツール。チャットを重ねるたびに自分の思考パターンが見えてくる。無料で使える。"
    },
    {
        "name": "reverie",
        "hint": "Reverie（レヴリー）の紹介。今の気分・場所・天気を伝えると、ゲーム・映画・アニメからBGMを提案してくれる。1分で試せる。"
    },
    {
        "name": "wearld",
        "hint": "Wearld（ウェアルド）の紹介。どんなWebサイトも別の世界観に変えるChrome拡張。深海・廃墟VHS・魔女のノートなど12種収録。"
    },
    {
        "name": "platform_user",
        "hint": "Betashipというプラットフォームの紹介。登録不要・ログイン不要で今すぐ試せるAIツールが集まっている場所。"
    },
    {
        "name": "platform_creator",
        "hint": "クリエイター向けBetashipの訴求。AIで作ったツール、APIコストが怖くて公開できていない人向け。Betashipがコスト・課金・配信を全部担う。"
    },
    {
        "name": "story",
        "hint": "個人で8本のAIツールを作って公開している話。なぜ作るのか、何を目指しているか。作った人間の話。"
    },
    {
        "name": "scene",
        "hint": "AIツールを使う具体的な場面・シーンの紹介。仕事の合間、眠れない夜、気分転換したいとき、など。"
    },
    {
        "name": "fail",
        "hint": "AIツールを作るうえで失敗した話・詰まった話のリアル。「うまくいかなかった」「想定と全然違った」という正直な経験談。自虐でも卑下でもなく、淡々と。"
    },
    {
        "name": "question",
        "hint": "フォロワーへの問いかけ型投稿。「こういうとき何のツール使ってる？」「AIに頼んで一番びっくりしたのって何？」など。返答を促す。宣伝感ゼロで。"
    },
    {
        "name": "compare",
        "hint": "比較型投稿。「ChatGPTで試すより、こっちの方が向いてるケースがある」「普通のプレイリストと違う点は…」など、ユーザーが知ってるものと比較して差を語る。"
    },
    {
        "name": "coming_soon",
        "hint": "次に公開予定のAIツールの予告。具体的なツール名は出さず「こういう体験ができるものを作ってる」という期待値醸成。「もうすぐ」感を出す。"
    },
    {
        "name": "making",
        "hint": "制作プロセスの公開。コードや技術の話より、「なぜこれを作ろうと思ったか」「どんな感情・体験が原点にあるか」を語る人間的な投稿。"
    },
]


def load_log() -> list:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    return []


def save_log(log: list):
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def next_angle(log: list) -> dict:
    # 直近11件で使っていないインデックスを選ぶ（12種対応）
    recent_names = [e.get("angle") for e in log[-11:]]
    for angle in ANGLES:
        if angle["name"] not in recent_names:
            return angle
    # 全部使い切ったら最も古いものへ
    return ANGLES[len(log) % len(ANGLES)]


def generate_post(angle: dict) -> str:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Betashipの日本語Xポスト（ツイート）を1つ書いてください。

投稿の角度・ヒント:
{angle['hint']}

URL（末尾に必ず含める）: {BETASHIP_URL}

条件:
- URLを除く本文は80文字以内
- 話し言葉・フランク・体験を語る感じ
- 宣伝っぽくしない
- ハッシュタグは #AIツール か #個人開発 のどちらか1つだけ
- URLは最後

本文テキストのみ出力。説明・前置き不要。"""
        }]
    )
    return resp.content[0].text.strip()


def post_to_x(text: str) -> str:
    client = tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET,
    )
    res = client.create_tweet(text=text)
    return str(res.data["id"])


def main(dry_run: bool = False):
    log = load_log()
    angle = next_angle(log)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 角度: {angle['name']}")

    post_text = generate_post(angle)
    print(f"\n--- 生成されたポスト ---\n{post_text}\n------------------------\n")

    if dry_run:
        print("🔍 DRY RUN — X への投稿はスキップしました")
        return

    tweet_id = post_to_x(post_text)
    url = f"https://x.com/i/web/status/{tweet_id}"
    print(f"✅ 投稿完了: {url}")

    log.append({
        "at": datetime.now().isoformat(),
        "angle": angle["name"],
        "text": post_text,
        "tweet_id": tweet_id,
        "url": url,
    })
    save_log(log)


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    main(dry_run=dry)
