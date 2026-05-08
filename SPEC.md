# Betaship MVP 仕様書

updated: 2026-05-08

## Phase 0 の検証目標

| 仮説 | 指標 | 合格ライン |
|------|------|---------|
| 一覧から試しに行く人がいる | 各ツールへのクリック数 | 週10クリック以上 × 2週連続 |
| 複数ツールを使う人がいる | 複数ツール使用率 | 30% 以上 |
| 有料意向がある | DMや感想の中で支払い意思を示す人 | 5人以上 |
| 「自分も載せたい」という声が来る | DM・リプライ | 1件でも来たら次フェーズへ |

→ これが揃うまでバックエンド実装禁止。「誰も来ない広場を整備するリスク」を避ける。

## 現在の構成（Phase 0）

```
output/betaship/
├── index.html       ← プラットフォームトップ（MVP本体）
├── launch-kit.html  ← X投稿テンプレート（12角度・週3投稿）
├── SPEC.md          ← このファイル
├── DEPLOY.md        ← GitHub Pages 手順書
└── screen-design.html ← UX設計書（7画面・3フロー）
```

## 公開プロダクト状況

| プロダクト | ステータス | URL |
|-----------|----------|-----|
| Moshimo | ✅ Live | https://moshimo.onrender.com |
| Reverie | ✅ Live | https://reverie-music.vercel.app |
| Wearld | 🟡 Beta | https://wearld.vercel.app |
| Gait | 🔵 In dev | — |
| Send Nudge | 🔵 In dev | — |
| Brain Switch | 🔵 In dev | — |
| Qliq | 🔵 In dev | — |
| Saki | 🔵 In dev | — |

## デプロイ方法（コスト0）

→ `DEPLOY.md` を参照
→ 公開URL: https://okamone.github.io/betaship/

## フィードバック収集

- カード直結モーダル（各ツールカードの「感想を送る」ボタン）
- Google Apps Script 経由でスプレッドシートに蓄積
- フローティングボタン・メアド収集は NG

## Phase 1 移行条件

以下がすべて揃ったら Betaship を本格構築する：
1. 週次UU 50以上が2週連続
2. 複数ツール使用率 30%以上  
3. 有料意向を示す人が5人以上

## マネタイズ設計（panel決定 2026-05-07）

### コアコンセプト
「クリエイターはコードとアイデアだけ出せばいい。課金・APIコスト・分配はBetashipが全部やる。」

### 3フェーズロードマップ
| フェーズ | 内容 | 開始条件 |
|---------|------|---------|
| Phase 0 | コンセプト検証（現在） | — |
| Phase 1 | 自己実証（8ツールでAPIプロキシ+Stripe） | 10クリック/週 + 1件支払い |
| Phase 2 | 外部クリエイター受け入れ（Stripe Connect） | Phase 1でコスト回収証明 |

### 課金モデル（確定）
- **クレジット制**（定額サブスクは却下 → ヘビーユーザーのAPIコスト赤字リスク）
- ユーザー単位のAPIコスト上限キャップ必須
- 分配モデル仮決め：Betaship 50% / クリエイター 50%

### 先行事例
- Poe.com（最も近い構造）/ Replicate（従量課金）

## ネクストアクション（人間が必要）

- [ ] Ko-fi アカウント作成 → index.html のリンクを差し替え
- [ ] GitHub Pages にデプロイ → 公開URLを取得
- [ ] X（Twitter）でシェア → launch-kit.html のツイートを使う
- [ ] 1週間後に クリック数・支払い数を確認する
