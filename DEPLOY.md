# Betaship — GitHub Pages デプロイ手順

**所要時間: 5分 / コスト: 無料**

## 手順

### 1. GitHub リポジトリを作成

```
リポジトリ名: betaship
公開設定: Public（GitHub Pages の無料利用に必要）
```

### 2. ファイルをプッシュ

```bash
cd output/betaship
git init
git add index.html
git commit -m "feat: Betaship MVP landing page"
git remote add origin https://github.com/[your-username]/betaship.git
git push -u origin main
```

### 3. GitHub Pages を有効化

```
リポジトリ → Settings → Pages
Source: Deploy from a branch
Branch: main / (root)
→ Save
```

### 4. 公開URL

```
https://[your-username].github.io/betaship/
```

約1〜2分で公開される。

---

## カスタムドメインを後から当てる場合

betaship.io を取得後：

```
1. Cloudflare DNS に CNAME レコード追加
   betaship.io → [your-username].github.io
   
2. GitHub Pages の Custom domain 欄に betaship.io を入力

3. Enforce HTTPS にチェック
```

## X（Twitter）でのシェア

→ `launch-kit.html` を開いて投稿文をコピーする

---

# Phase 1 — APIプロキシ + クレジット統合

`api/` フォルダに実装済み。以下を順番に実行する。

## ステップ1：KazuO Supabase に betaship スキーマを追加（手動）

1. https://supabase.com → KazuO プロジェクト（kphfolcpguniaaefcgcw）を開く
2. SQL Editor を開く
3. `api/schema_betaship.sql` の中身をコピペして Run
4. Mossimoの既存テーブルには一切影響なし

## ステップ2：Stripe 設定（手動）

Stripeダッシュボードで以下を作成し、price_id を `.env` に記入する：

| 商品名 | 種別 | 金額 |
|---|---|---|
| Betaship Maker | サブスクリプション | $5/月 |
| Betaship Pro | サブスクリプション | $15/月 |
| トップアップ 300cr | 一括払い | $3 |
| トップアップ 1200cr | 一括払い | $10 |

## ステップ3：APIプロキシを Render にデプロイ

```bash
cd output/betaship/api
# .env.example をコピーして .env を作成・記入
cp .env.example .env

# Render に新規 Web Service を作成
# Build: pip install -r requirements.txt
# Start: gunicorn proxy:app
# 環境変数を .env の内容で設定
```

## ステップ4：Moshimo既存ユーザーを移行（手動確認後に実行）

```bash
cd output/betaship/api
python migrate_moshimo.py
# → migrate_result.csv で結果確認
```

## ステップ5：各サービスのAPI呼び出しをプロキシに差し替え

Mossimoを例とした差し替え方：

```python
# 変更前（各サービスで直接呼んでいる箇所）
resp = anthropic_client.messages.create(
    model="claude-haiku-4-5-20251001",
    messages=messages,
    max_tokens=1024
)

# 変更後（Betashipプロキシ経由）
import requests
resp = requests.post("https://betaship-api.onrender.com/api/ai", json={
    "service": "moshimo",
    "messages": messages,
    "max_tokens": 1024,
}, headers={"Authorization": f"Bearer {user_jwt}"})
result = resp.json()
content = result["content"]
```

## ステップ6：Webhook登録（手動）

Stripe → Developers → Webhooks → Add endpoint

- URL: `https://betaship-api.onrender.com/api/stripe/webhook`
- イベント: `checkout.session.completed`, `invoice.paid`
