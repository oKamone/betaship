-- Betaship 共通クレジット管理スキーマ
-- KazuO Supabase（kphfolcpguniaaefcgcw）の SQL Editor で実行する
-- Mossimoの既存テーブルには一切触れない

-- --------------------------------------------------------
-- betaship スキーマを作成
-- --------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS betaship;

-- --------------------------------------------------------
-- 1. プラン設定（固定値）
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS betaship.plan_config (
  plan        TEXT PRIMARY KEY,
  monthly_cr  INT  NOT NULL,
  price_usd   NUMERIC(6,2)
);

INSERT INTO betaship.plan_config (plan, monthly_cr, price_usd) VALUES
  ('free',   50,    0.00),
  ('plus',   600,   5.00),
  ('pro',    2500,  15.00)
ON CONFLICT (plan) DO NOTHING;

-- --------------------------------------------------------
-- 2. サブスクリプション（プラン管理）
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS betaship.subscriptions (
  user_id                TEXT PRIMARY KEY,
  plan                   TEXT NOT NULL DEFAULT 'free',
  stripe_customer_id     TEXT,
  stripe_subscription_id TEXT,
  current_period_end     TIMESTAMPTZ,
  created_at             TIMESTAMPTZ DEFAULT now(),
  updated_at             TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE betaship.subscriptions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_read_own_subscription" ON betaship.subscriptions;
DROP POLICY IF EXISTS "service_role_full_subscriptions" ON betaship.subscriptions;
CREATE POLICY "users_read_own_subscription" ON betaship.subscriptions
  FOR SELECT USING (auth.uid()::text = user_id);

CREATE POLICY "service_role_full_subscriptions" ON betaship.subscriptions
  FOR ALL TO service_role USING (true);

-- --------------------------------------------------------
-- 3. クレジット残高
--    monthly_cr: 月次付与分（毎月リセット）
--    topup_cr:   トップアップ分（繰り越し）
--    消費順: monthly_cr → topup_cr
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS betaship.credits (
  user_id      TEXT PRIMARY KEY,
  monthly_cr   INT NOT NULL DEFAULT 0,
  topup_cr     INT NOT NULL DEFAULT 0,
  period_start DATE,
  updated_at   TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE betaship.credits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_read_own_credits" ON betaship.credits;
DROP POLICY IF EXISTS "service_role_full_credits" ON betaship.credits;
CREATE POLICY "users_read_own_credits" ON betaship.credits
  FOR SELECT USING (auth.uid()::text = user_id);

CREATE POLICY "service_role_full_credits" ON betaship.credits
  FOR ALL TO service_role USING (true);

-- --------------------------------------------------------
-- 4. 利用ログ（サービス・ツール別）
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS betaship.usage_log (
  id          BIGSERIAL PRIMARY KEY,
  user_id     TEXT,
  service     TEXT NOT NULL,   -- 'moshimo' | 'wearld' | 'tagine' ...
  tool        TEXT,
  cr_used     INT  NOT NULL DEFAULT 0,
  tokens_in   INT  DEFAULT 0,
  tokens_out  INT  DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE betaship.usage_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_read_own_usage" ON betaship.usage_log;
DROP POLICY IF EXISTS "service_role_full_usage" ON betaship.usage_log;
CREATE POLICY "users_read_own_usage" ON betaship.usage_log
  FOR SELECT USING (auth.uid()::text = user_id);

CREATE POLICY "service_role_full_usage" ON betaship.usage_log
  FOR ALL TO service_role USING (true);

-- --------------------------------------------------------
-- 5. RPC: クレジット消費（monthly → topup の順）
-- --------------------------------------------------------
CREATE OR REPLACE FUNCTION betaship.deduct_credits(
  p_user_id    TEXT,
  p_amount     INT,
  p_service    TEXT,
  p_tool       TEXT DEFAULT NULL,
  p_tokens_in  INT  DEFAULT 0,
  p_tokens_out INT  DEFAULT 0
)
RETURNS INT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_monthly INT;
  v_topup   INT;
  v_total   INT;
  v_dm      INT;
  v_dt      INT;
BEGIN
  SELECT monthly_cr, topup_cr
    INTO v_monthly, v_topup
    FROM betaship.credits
   WHERE user_id = p_user_id
   FOR UPDATE;

  v_monthly := COALESCE(v_monthly, 0);
  v_topup   := COALESCE(v_topup, 0);
  v_total   := v_monthly + v_topup;

  IF v_total < p_amount THEN
    RETURN -1;
  END IF;

  v_dm := LEAST(p_amount, v_monthly);
  v_dt := p_amount - v_dm;

  UPDATE betaship.credits
     SET monthly_cr = monthly_cr - v_dm,
         topup_cr   = topup_cr   - v_dt,
         updated_at = now()
   WHERE user_id = p_user_id;

  INSERT INTO betaship.usage_log (user_id, service, tool, cr_used, tokens_in, tokens_out)
  VALUES (p_user_id, p_service, p_tool, p_amount, p_tokens_in, p_tokens_out);

  RETURN v_total - p_amount;
END;
$$;

-- --------------------------------------------------------
-- 6. RPC: 月次クレジット付与（Stripe Webhook / 月初バッチ）
-- --------------------------------------------------------
CREATE OR REPLACE FUNCTION betaship.grant_monthly_credits(
  p_user_id TEXT,
  p_plan    TEXT
)
RETURNS INT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_amount INT;
BEGIN
  SELECT monthly_cr INTO v_amount
    FROM betaship.plan_config
   WHERE plan = p_plan;

  INSERT INTO betaship.credits (user_id, monthly_cr, topup_cr, period_start)
  VALUES (p_user_id, v_amount, 0, CURRENT_DATE)
  ON CONFLICT (user_id)
  DO UPDATE SET
    monthly_cr   = v_amount,
    period_start = CURRENT_DATE,
    updated_at   = now();

  RETURN v_amount;
END;
$$;

-- --------------------------------------------------------
-- 7. RPC: トップアップ追加（Stripe Webhook）
-- --------------------------------------------------------
-- --------------------------------------------------------
-- 8. 製品設定（プロダクト別コントロール）
-- Betaship Admin からリアルタイム変更可能
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS betaship.product_config (
  product_id        TEXT     PRIMARY KEY,
  free_daily_limit  INT      NOT NULL DEFAULT 5,
  free_mode         BOOLEAN  NOT NULL DEFAULT false,  -- ONで全ユーザー無料
  billing_active    BOOLEAN  NOT NULL DEFAULT false,  -- ONでクレジット課金有効
  maintenance_mode  BOOLEAN  NOT NULL DEFAULT false,  -- ONで全アクセス遮断
  campaign_active   BOOLEAN  NOT NULL DEFAULT false,
  campaign_note     TEXT              DEFAULT '',
  product_url       TEXT              DEFAULT '',     -- プロダクトのベースURL
  updated_at        TIMESTAMPTZ       DEFAULT now()
);

-- billing_active / product_url を後から追加する場合（既にテーブルが存在する場合）
ALTER TABLE betaship.product_config ADD COLUMN IF NOT EXISTS billing_active BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE betaship.product_config ADD COLUMN IF NOT EXISTS product_url TEXT DEFAULT '';

-- Level 2: hosted chat 対応（既にテーブルが存在する場合）
ALTER TABLE betaship.product_config ADD COLUMN IF NOT EXISTS display_name    TEXT    DEFAULT '';
ALTER TABLE betaship.product_config ADD COLUMN IF NOT EXISTS description     TEXT    DEFAULT '';
ALTER TABLE betaship.product_config ADD COLUMN IF NOT EXISTS system_prompt   TEXT    DEFAULT '';
ALTER TABLE betaship.product_config ADD COLUMN IF NOT EXISTS welcome_message TEXT    DEFAULT '';
ALTER TABLE betaship.product_config ADD COLUMN IF NOT EXISTS model           TEXT    DEFAULT 'claude-haiku-4-5-20251001';
ALTER TABLE betaship.product_config ADD COLUMN IF NOT EXISTS hosted          BOOLEAN NOT NULL DEFAULT false;

-- Moshimo・Await を hosted に設定（system_prompt はオーナーが後で更新する）
UPDATE betaship.product_config SET
  display_name    = 'Moshimo（もしも）',
  description     = '思考にAIメンターを入れる',
  welcome_message = 'こんにちは。「もしも〇〇だったら？」から始めてみてください。',
  hosted          = true
WHERE product_id = 'moshimo';

UPDATE betaship.product_config SET
  display_name    = 'Await（アウェイト）',
  description     = '会う前に、気になる相手のことをAIと話す',
  welcome_message = 'これから会う人のこと、一緒に考えましょう。どんな人ですか？',
  hosted          = true
WHERE product_id = 'await';

INSERT INTO betaship.product_config (product_id, free_daily_limit, product_url) VALUES
  ('moshimo', 5, 'https://moshimo.onrender.com'),
  ('wearld',  5, 'https://wearld.vercel.app'),
  ('reverie', 5, 'https://reverie-music.vercel.app'),
  ('await',   5, ''),
  ('gait',    5, '')
ON CONFLICT (product_id) DO NOTHING;


-- --------------------------------------------------------
CREATE OR REPLACE FUNCTION betaship.add_topup_credits(
  p_user_id TEXT,
  p_amount  INT
)
RETURNS INT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  v_new INT;
BEGIN
  INSERT INTO betaship.credits (user_id, monthly_cr, topup_cr, period_start)
  VALUES (p_user_id, 0, p_amount, CURRENT_DATE)
  ON CONFLICT (user_id)
  DO UPDATE SET
    topup_cr   = betaship.credits.topup_cr + p_amount,
    updated_at = now()
  RETURNING topup_cr INTO v_new;

  RETURN v_new;
END;
$$;
