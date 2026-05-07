# Betaship MVP 仕様書

updated: 2026-05-07

## 何を検証するか

| 仮説 | 指標 | 合格ライン |
|------|------|---------|
| 「プロダクト一覧ページ」から実際に試しに行く人がいる | 各プロダクトへのクリック数 | 1週間で10クリック以上 |
| pay-what-you-want で払う人がいる | Ko-fi / Gumroad の収益 | 1件でも入金があれば仮説成立 |
| クリエイターとして「自分も載せてほしい」声が来る | DMやリプライ | 1件でも来たら次フェーズへ |

## 現在の構成（Phase 0）

```
output/betaship/
├── index.html   ← プラットフォームトップ（これがMVP）
├── SPEC.md      ← このファイル
└── DEPLOY.md    ← GitHub Pages 手順書
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

## 収益設計（Phase 0）

- 全プロダクト無料試用
- pay-what-you-want（Ko-fi リンク）
- 目標：MRR $0 → まず1件の入金を確認する

## Phase 1 移行条件

以下がすべて揃ったら Betaship を本格構築する：
1. 週10クリック以上が2週連続
2. 1件以上の支払い（金額不問）
3. ドメイン betaship.io を取得する

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
