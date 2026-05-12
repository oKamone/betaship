"""
Moshimo既存ユーザー → Betaship共通DB 移行スクリプト
実行タイミング：Betaship Supabaseプロジェクト作成後・本番切り替え前に1回だけ実行

処理内容：
1. Moshimo subscriptionsテーブルからProユーザーを取得
2. Betaship DBにsubscriptions + credits（Maker相当）を付与してスタート
3. 実行結果をCSVに出力（確認用）
"""
import os
import csv
from datetime import date
from supabase import create_client

MOSHIMO_URL = os.environ["MOSHIMO_SUPABASE_URL"]
MOSHIMO_KEY = os.environ["MOSHIMO_SUPABASE_SERVICE_KEY"]

BETASHIP_URL = os.environ["BETASHIP_SUPABASE_URL"]
BETASHIP_KEY = os.environ["BETASHIP_SUPABASE_SERVICE_KEY"]

MAKER_CR = 600  # Moshimo Pro → Betaship Maker相当

def main():
    moshimo = create_client(MOSHIMO_URL, MOSHIMO_KEY)
    betaship = create_client(BETASHIP_URL, BETASHIP_KEY)

    # Moshimoの課金ユーザーを取得
    rows = moshimo.table("subscriptions").select("user_id,plan,stripe_customer_id,stripe_subscription_id").execute()
    pro_users = [r for r in (rows.data or []) if r.get("plan") == "pro"]

    print(f"Moshimo Proユーザー: {len(pro_users)}件")

    results = []
    for u in pro_users:
        uid = u["user_id"]
        try:
            # Betaship subscriptionsに登録（betashipスキーマ）
            betaship.schema("betaship").table("subscriptions").upsert({
                "user_id": uid,
                "plan": "maker",
                "stripe_customer_id": u.get("stripe_customer_id"),
                "stripe_subscription_id": u.get("stripe_subscription_id"),
            }).execute()

            # 月次クレジットをフルで付与（移行日にリセット）
            betaship.schema("betaship").table("credits").upsert({
                "user_id":      uid,
                "monthly_cr":   MAKER_CR,
                "topup_cr":     0,
                "period_start": str(date.today()),
            }).execute()

            results.append({"user_id": uid, "status": "ok", "cr": MAKER_CR})
            print(f"  ✓ {uid}")
        except Exception as e:
            results.append({"user_id": uid, "status": "error", "cr": 0, "error": str(e)})
            print(f"  ✗ {uid}: {e}")

    # 結果CSV出力
    out = "migrate_result.csv"
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["user_id", "status", "cr", "error"])
        writer.writeheader()
        writer.writerows(results)

    ok  = sum(1 for r in results if r["status"] == "ok")
    err = len(results) - ok
    print(f"\n完了: {ok}件成功 / {err}件エラー → {out}")

if __name__ == "__main__":
    main()
