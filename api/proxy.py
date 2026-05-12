"""
Betaship APIプロキシ
各プロダクトはこのエンドポイント経由でClaudeを呼び出す。
クレジット残高を確認→消費→Claude API呼び出し→結果を返す。
"""
import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
from supabase import create_client, Client
import stripe

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": os.environ.get("ALLOWED_ORIGINS", "*")}})

# --- クライアント初期化 ---
_anthropic = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_sb: Client = create_client(
    os.environ["BETASHIP_SUPABASE_URL"],
    os.environ["BETASHIP_SUPABASE_SERVICE_KEY"]
)
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

# クレジット換算レート（tokens → cr）
# 1cr = 800 input tokens 相当（Haiku基準で原価約$0.0003/cr、余裕を持たせた設定）
TOKENS_PER_CR = 800

STRIPE_PRICE_IDS = {
    "maker": os.environ.get("STRIPE_PRICE_MAKER", ""),   # $5/月
    "pro":   os.environ.get("STRIPE_PRICE_PRO", ""),     # $15/月
}
TOPUP_PRICE_IDS = {
    os.environ.get("STRIPE_PRICE_TOPUP_300", ""): 300,   # $3=300cr
    os.environ.get("STRIPE_PRICE_TOPUP_1200", ""): 1200, # $10=1200cr
}


# --------------------------------------------------------
# ヘルパー：リクエストのJWTからuser_idを取得
# --------------------------------------------------------
def _get_user_id(req) -> str | None:
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        resp = _sb.auth.get_user(token)
        return resp.user.id if resp.user else None
    except Exception:
        return None


# --------------------------------------------------------
# GET /api/credits  — 残高・使用率を返す
# --------------------------------------------------------
@app.route("/api/credits", methods=["GET"])
def get_credits():
    uid = _get_user_id(request)
    if not uid:
        return jsonify({"error": "unauthorized"}), 401

    cr_row = _sb.schema("betaship").table("credits").select("*").eq("user_id", uid).maybe_single().execute()
    sub_row = _sb.schema("betaship").table("subscriptions").select("plan").eq("user_id", uid).maybe_single().execute()
    plan_row = _sb.schema("betaship").table("plan_config").select("monthly_cr").eq(
        "plan", (sub_row.data or {}).get("plan", "free")
    ).maybe_single().execute()

    cr = cr_row.data or {}
    monthly_cr  = cr.get("monthly_cr", 0)
    topup_cr    = cr.get("topup_cr", 0)
    plan_limit  = (plan_row.data or {}).get("monthly_cr", 50)
    plan        = (sub_row.data or {}).get("plan", "free")

    return jsonify({
        "plan":        plan,
        "monthly_cr":  monthly_cr,
        "topup_cr":    topup_cr,
        "total_cr":    monthly_cr + topup_cr,
        "plan_limit":  plan_limit,
        "usage_pct":   round((1 - monthly_cr / plan_limit) * 100, 1) if plan_limit else 100,
    })


# --------------------------------------------------------
# POST /api/ai  — Claude呼び出しプロキシ
# --------------------------------------------------------
@app.route("/api/ai", methods=["POST"])
def ai_proxy():
    uid = _get_user_id(request)
    if not uid:
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(force=True)
    service  = body.get("service", "unknown")   # 呼び出し元サービス名
    tool     = body.get("tool")
    messages = body.get("messages", [])
    system   = body.get("system", "")
    model    = body.get("model", "claude-haiku-4-5-20251001")
    max_tokens = int(body.get("max_tokens", 1024))

    if not messages:
        return jsonify({"error": "messages required"}), 400

    # 残高チェック（最低1crあれば続行。実際の消費は後で計算）
    cr_row = _sb.schema("betaship").table("credits").select("monthly_cr,topup_cr").eq("user_id", uid).maybe_single().execute()
    if not cr_row.data:
        # 初回利用: freeプランとして自動プロビジョニング
        _sb.schema("betaship").table("subscriptions").upsert({"user_id": uid, "plan": "free"}).execute()
        _sb.schema("betaship").rpc("grant_monthly_credits", {"p_user_id": uid, "p_plan": "free"}).execute()
        cr_row = _sb.schema("betaship").table("credits").select("monthly_cr,topup_cr").eq("user_id", uid).maybe_single().execute()
    cr = cr_row.data or {}
    if (cr.get("monthly_cr", 0) + cr.get("topup_cr", 0)) < 1:
        return jsonify({"error": "insufficient_credits"}), 402

    # Claude API呼び出し
    try:
        kwargs = dict(model=model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs["system"] = system
        resp = _anthropic.messages.create(**kwargs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Token → cr 換算して消費
    tokens_in  = resp.usage.input_tokens
    tokens_out = resp.usage.output_tokens
    cr_used    = max(1, (tokens_in + tokens_out * 3) // TOKENS_PER_CR)

    _sb.schema("betaship").rpc("deduct_credits", {
        "p_user_id":   uid,
        "p_amount":    cr_used,
        "p_service":   service,
        "p_tool":      tool,
        "p_tokens_in": tokens_in,
        "p_tokens_out": tokens_out,
    }).execute()

    return jsonify({
        "content":    resp.content[0].text if resp.content else "",
        "cr_used":    cr_used,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "stop_reason": resp.stop_reason,
    })


# --------------------------------------------------------
# POST /api/stripe/webhook  — Stripe課金完了 → cr付与
# --------------------------------------------------------
@app.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, os.environ["STRIPE_WEBHOOK_SECRET"]
        )
    except Exception:
        return jsonify({"error": "invalid signature"}), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        uid     = session.get("metadata", {}).get("user_id")
        mode    = session.get("mode")
        if not uid:
            return jsonify({"ok": True})

        if mode == "subscription":
            # プラン購入 → プラン更新 + 月次cr付与
            price_id = session.get("metadata", {}).get("price_id", "")
            plan = next((p for p, pid in STRIPE_PRICE_IDS.items() if pid == price_id), "maker")
            _sb.schema("betaship").table("subscriptions").upsert({
                "user_id": uid,
                "plan": plan,
                "stripe_customer_id": session.get("customer"),
                "stripe_subscription_id": session.get("subscription"),
            }).execute()
            _sb.schema("betaship").rpc("grant_monthly_credits", {"p_user_id": uid, "p_plan": plan}).execute()

        elif mode == "payment":
            # トップアップ購入 → cr加算
            price_id = session.get("metadata", {}).get("price_id", "")
            amount = TOPUP_PRICE_IDS.get(price_id, 0)
            if amount:
                _sb.schema("betaship").rpc("add_topup_credits", {"p_user_id": uid, "p_amount": amount}).execute()

    elif event["type"] == "invoice.paid":
        # サブスクリプション更新 → 月次cr付与
        invoice = event["data"]["object"]
        sub_id  = invoice.get("subscription")
        if sub_id:
            sub_row = _sb.schema("betaship").table("subscriptions").select("user_id,plan").eq(
                "stripe_subscription_id", sub_id
            ).maybe_single().execute()
            if sub_row.data:
                _sb.schema("betaship").rpc("grant_monthly_credits", {
                    "p_user_id": sub_row.data["user_id"],
                    "p_plan":    sub_row.data["plan"],
                }).execute()

    return jsonify({"ok": True})


# --------------------------------------------------------
# POST /api/stripe/checkout  — Checkout Session作成
# --------------------------------------------------------
@app.route("/api/stripe/checkout", methods=["POST"])
def create_checkout():
    uid = _get_user_id(request)
    if not uid:
        return jsonify({"error": "unauthorized"}), 401

    body     = request.get_json(force=True)
    price_id = body.get("price_id")
    mode     = body.get("mode", "subscription")  # 'subscription' | 'payment'

    if not price_id:
        return jsonify({"error": "price_id required"}), 400

    base_url = os.environ.get("APP_BASE_URL", "https://okamone.github.io/betaship")
    session = stripe.checkout.Session.create(
        mode=mode,
        line_items=[{"price": price_id, "quantity": 1}],
        metadata={"user_id": uid, "price_id": price_id},
        success_url=f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/cancel",
    )
    return jsonify({"url": session.url})


# --------------------------------------------------------
# GET /health  /api/ping
# --------------------------------------------------------
@app.route("/health")
@app.route("/api/ping")
def health():
    return jsonify({"ok": True})


def _start_keepalive():
    import time, threading, urllib.request as _ur
    def _ping():
        while True:
            time.sleep(8 * 60)
            try:
                _ur.urlopen("https://betaship-api.onrender.com/api/ping", timeout=10)
            except Exception:
                pass
    threading.Thread(target=_ping, daemon=True).start()

_start_keepalive()

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5099)), debug=False)
