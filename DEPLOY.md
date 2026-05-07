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

## Ko-fi リンクの差し替え

`index.html` の以下を差し替える：

```html
<!-- 変更前 -->
<a href="https://ko-fi.com" ...>

<!-- 変更後 -->
<a href="https://ko-fi.com/[your-id]" ...>
```

## X（Twitter）でのシェア

→ `launch-kit.html` を開いて投稿文をコピーする
