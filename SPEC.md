# Betaship MVP 仕様書

updated: 2026-05-27

## Phase 0 の検証目標

| 仮説 | 指標 | 合格ライン |
|------|------|---------|
| 一覧から試しに行く人がいる | 各ツールへのクリック数 | 週10クリック以上 × 2週連続 |
| 複数ツールを使う人がいる | 複数ツール使用率 | 30% 以上 |
| 有料意向がある | DMや感想の中で支払い意思を示す人 | 5人以上 |
| 「自分も載せたい」という声が来る | DM・リプライ | 1件でも来たら次フェーズへ |

→ これが揃うまでバックエンド実装禁止。「誰も来ない広場を整備するリスク」を避ける。

## 現在の構成（Phase 1 進行中）

```
output/betaship/
├── index.html         ← プラットフォームトップ（MVP本体）
├── strategy.html      ← 方向性・GTM戦略ドキュメント
├── launch-kit.html    ← X投稿テンプレート
├── SPEC.md            ← このファイル
├── DEPLOY.md          ← GitHub Pages + Render 手順書
└── api/               ← Betaship APIプロキシ（Render デプロイ対象）
    ├── proxy.py       ← Flask アプリ本体
    ├── schema_betaship.sql ← Supabase スキーマ定義
    ├── grant_betaship.sql  ← Supabase 権限付与
    ├── admin.html     ← 管理画面（/admin で配信）
    ├── render.yaml    ← Render デプロイ設定
    ├── requirements.txt
    └── .env.render    ← Render 環境変数（Stripe/Supabase設定済み）
```

## 公開プロダクト状況

| プロダクト | ステータス | URL |
|-----------|----------|-----|
| Reverie | 試せる | https://reverie-music.vercel.app |
| Wearld | 試せる | https://wearld.vercel.app |
| Moshimo | 準備中（Renderスリープ中） | https://moshimo.onrender.com |
| Await | 準備中 | — |
| Gait | 準備中 | — |

## デプロイ方法（コスト0）

→ `DEPLOY.md` を参照
→ 公開URL: https://betaship.web.app/

## フィードバック収集

- カード直結モーダル（各ツールカードの「感想を送る」ボタン）
- Google Apps Script 経由でスプレッドシートに蓄積
- フローティングボタン・メアド収集は NG

## Phase 1 移行条件

以下がすべて揃ったら Betaship を本格構築する：
1. 週次UU 50以上が2週連続
2. 複数ツール使用率 30%以上  
3. 有料意向を示す人が5人以上

## マネタイズ設計（2026-05-12 確定）

### コアコンセプト
「クリエイターはコードとアイデアだけ出せばいい。課金・APIコスト・分配はBetashipが全部やる。」

ユーザーはBetashipに1箇所課金すれば、全プロダクトのAPIを統一クレジットで使える（Poe.com構造）。

### クレジットプラン（確定）

| プラン | 月額 | 付与cr/月 | 備考 |
|---|---|---|---|
| Free | 無料 | 50cr | 試用 |
| Maker | $5 | 600cr | Moshimo Pro ¥680/月と同等 |
| Pro | $15 | 2,500cr | ヘビーユーザー向け |

**トップアップ（使い切った時の追加購入）：**
- $3 → 300cr
- $10 → 1,200cr（割安）

**クレジット消費レート（目安）：**
- テキスト系ツール1回（Send Nudge・Moshimo等）→ 5cr
- 重め処理1回（画像・長文解析）→ 20cr

### 個別課金との統合設計（A方式）

既存の個別課金はそのまま維持しつつ、Betashipクレジットに橋渡しする。

| 既存課金 | Betaship換算 | 対応プラン |
|---|---|---|
| Moshimo Pro ¥680/月 | 600cr/月 自動付与 | Maker相当 |
| Wearld $9 買い切り | 900cr に変換 | トップアップ相当 |

- 個別課金ユーザー → Betashipアカウントが自動リンク → クレジット付与
- 各サービスのUIに「Betashipクレジット残高：450/600」を表示
- 他プロダクトでも同じクレジットが使える旨をリンク付きで案内

### 3フェーズロードマップ

| フェーズ | 内容 | 開始条件 |
|---------|------|---------|
| Phase 0 | コンセプト検証（現在） | — |
| Phase 1 | 統合クレジット実装（プロキシAPI + Supabase共通化 + Stripe） | 10クリック/週 + 1件支払い |
| Phase 2 | 外部クリエイター受け入れ（Stripe Connect） | Phase 1でコスト回収証明 |

### Phase 1 実装仕様（確定）

1. **Betaship APIプロキシ**（`/api/ai`）
   - 各プロダクトがClaude APIを直接叩く代わりにプロキシ経由に切り替え
   - Token消費量を計測 → Supabaseのcreditsを減算

2. **Supabase 共通DB**
   - テーブル：`users` `credits` `usage_log`
   - 全プロダクトが同一Supabaseプロジェクトを参照

3. **認証共通化**
   - Supabase Auth を全プロダクトで統一
   - 個別課金ユーザーは自動リンク処理

4. **各サービス改修**
   - `anthropic.messages.create()` → Betaship プロキシAPIに差し替え
   - 優先順位：Moshimo → Wearld → その他

### 先行事例
- Poe.com（最も近い構造）/ Replicate（従量課金）

## Phase 1 実装状況（2026-05-27）

| 項目 | 状態 |
|------|------|
| APIプロキシ（proxy.py）| ✅ 実装済み |
| Supabaseスキーマ（schema_betaship.sql）| ✅ 設計済み・手動実行待ち |
| Stripe商品・価格ID | ✅ 設定済み（テストモード） |
| Render デプロイ | ⏸ 手動でデプロイ必要 |
| Stripe Webhook 登録 | ⏸ Render URL確定後 |
| 管理画面（admin.html）| ✅ 実装済み |

## ネクストアクション（手動が必要）

- [ ] Supabase SQL Editor で `schema_betaship.sql` → `grant_betaship.sql` を順番に実行
- [ ] Render で新規 Web Service を作成（`api/` フォルダをルートに指定）
- [ ] `.env.render` の内容を Render の環境変数に貼り付け（ADMIN_TOKENは任意の文字列を設定）
- [ ] Render デプロイ後、`https://betaship-api.onrender.com/health` で疎通確認
- [ ] Stripe Dashboard → Developers → Webhooks → Add endpoint（`/api/stripe/webhook`）
- [ ] Stripe を live モードに切り替えて価格IDを更新（テスト検証後）
