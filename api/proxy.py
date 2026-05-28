"""
Betaship APIプロキシ
各プロダクトはこのエンドポイント経由でClaudeを呼び出す。
クレジット残高を確認→消費→Claude API呼び出し→結果を返す。
"""
import os
import json
import functools
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_file
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

# モデル別クレジット換算レート（tokens → cr）
# Anthropic 料金比率に基づく: Haiku $0.8/MTok, Sonnet $3/MTok, Opus $15/MTok
TOKENS_PER_CR = {
    "claude-haiku":  800,   # 基準
    "claude-sonnet": 200,   # Haikuの3.75倍高い → 1/4のトークンで1cr
    "claude-opus":    40,   # Haikuの18倍高い → 1/20のトークンで1cr
}

def _tokens_per_cr(model: str) -> int:
    for prefix, rate in TOKENS_PER_CR.items():
        if prefix in model:
            return rate
    return TOKENS_PER_CR["claude-haiku"]

STRIPE_PRICE_IDS = {
    "plus": os.environ.get("STRIPE_PRICE_MAKER", ""),   # ¥680/月 / 600cr
    "pro":   os.environ.get("STRIPE_PRICE_PRO", ""),     # ¥1,980/月 / 2,000cr
}
TOPUP_PRICE_IDS = {
    os.environ.get("STRIPE_PRICE_TOPUP_300", ""): 300,   # ¥300=300cr
    os.environ.get("STRIPE_PRICE_TOPUP_1200", ""): 1200, # ¥1,000=1200cr
}

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

def _require_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not ADMIN_TOKEN:
            return jsonify({"error": "admin not configured"}), 503
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if token != ADMIN_TOKEN:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


# --------------------------------------------------------
# ヘルパー：リクエストのJWTからuser_idを取得
# --------------------------------------------------------
def _get_client_ip(req) -> str:
    forwarded = req.headers.get("X-Forwarded-For", "")
    for ip in [i.strip() for i in forwarded.split(",")]:
        if ip and not (ip.startswith("10.") or ip.startswith("172.") or ip.startswith("127.") or ip == "::1"):
            return ip
    return req.remote_addr or "unknown"


def _anon_rate_ok(ip: str, product_id: str, limit: int) -> bool:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        result = _sb.schema("betaship").rpc("increment_anon_usage", {
            "p_ip": ip, "p_date": f"{product_id}:{today}"
        }).execute()
        count = result.data if isinstance(result.data, int) else int(result.data or 0)
        return count <= limit
    except Exception:
        return True  # テーブル未作成などのエラー時は通す


def _get_user_id(req) -> str | None:
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        print("[auth] Authorization header missing or not Bearer", flush=True)
        return None
    token = auth[7:]
    try:
        resp = _sb.auth.get_user(token)
        return resp.user.id if resp.user else None
    except Exception as e:
        print(f"[auth] get_user failed: {e}", flush=True)
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

    body = request.get_json(force=True)
    service    = body.get("service", "unknown")
    tool       = body.get("tool")
    messages   = body.get("messages", [])
    system     = body.get("system", "")
    model      = body.get("model", "claude-haiku-4-5-20251001")
    max_tokens = int(body.get("max_tokens", 1024))

    if not messages:
        return jsonify({"error": "messages required"}), 400

    # product_config 取得
    cfg_data = {}
    try:
        cfg_row = _sb.schema("betaship").table("product_config").select(
            "free_mode,billing_active,free_daily_limit,system_prompt,model,hosted"
        ).eq("product_id", service).maybe_single().execute()
        cfg_data = cfg_row.data or {}
    except Exception:
        pass

    free_mode       = cfg_data.get("free_mode", False)
    billing_active  = cfg_data.get("billing_active", False)
    free_daily_limit = int(cfg_data.get("free_daily_limit") or 10)
    skip_credits    = free_mode or not billing_active

    # hosted tool: system_prompt を DB から自動注入（クライアントには渡さない）
    if not system and cfg_data.get("hosted") and cfg_data.get("system_prompt"):
        system = cfg_data["system_prompt"]

    # hosted tool のデフォルトモデルを適用
    if not body.get("model") and cfg_data.get("model"):
        model = cfg_data["model"]

    if not uid:
        # 非ログイン → IPレート制限
        ip = _get_client_ip(request)
        if not _anon_rate_ok(ip, service, free_daily_limit):
            return jsonify({
                "error": "daily_limit_exceeded",
                "message": f"本日の無料利用回数（{free_daily_limit}回）に達しました。"
            }), 429

    cr_row = None
    if not skip_credits and uid:
        # 残高チェック（最低1crあれば続行）
        cr_row = _sb.schema("betaship").table("credits").select("monthly_cr,topup_cr").eq("user_id", uid).maybe_single().execute()
        if not (cr_row and cr_row.data):
            # 初回利用: freeプランとして自動プロビジョニング
            _sb.schema("betaship").table("subscriptions").upsert({"user_id": uid, "plan": "free"}).execute()
            plan_row = _sb.schema("betaship").table("plan_config").select("monthly_cr").eq("plan", "free").maybe_single().execute()
            init_cr = (plan_row.data or {}).get("monthly_cr", 50)
            from datetime import date
            _sb.schema("betaship").table("credits").upsert({
                "user_id": uid, "monthly_cr": init_cr, "topup_cr": 0,
                "period_start": date.today().replace(day=1).isoformat()
            }).execute()
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

    # Token → cr 換算して消費（モデル別レート適用）
    tokens_in  = resp.usage.input_tokens
    tokens_out = resp.usage.output_tokens
    cr_used    = max(1, (tokens_in + tokens_out * 3) // _tokens_per_cr(model))

    current_plan = "free"
    if not skip_credits and uid and cr_row:
        # monthly_cr → topup_cr の順に消費
        cr = (cr_row.data or {})
        monthly = cr.get("monthly_cr", 0)
        topup   = cr.get("topup_cr", 0)
        if monthly >= cr_used:
            _sb.schema("betaship").table("credits").update({"monthly_cr": monthly - cr_used}).eq("user_id", uid).execute()
        elif monthly > 0:
            _sb.schema("betaship").table("credits").update({"monthly_cr": 0, "topup_cr": topup - (cr_used - monthly)}).eq("user_id", uid).execute()
        else:
            _sb.schema("betaship").table("credits").update({"topup_cr": topup - cr_used}).eq("user_id", uid).execute()
        try:
            sub = _sb.schema("betaship").table("subscriptions").select("plan").eq("user_id", uid).maybe_single().execute()
            current_plan = (sub.data or {}).get("plan", "free")
        except Exception:
            pass

    # 呼び出しログ（失敗しても無視）
    try:
        _sb.schema("betaship").table("ai_calls").insert({
            "user_id":    uid,
            "service":    service,
            "tool":       tool,
            "model":      model,
            "tokens_in":  tokens_in,
            "tokens_out": tokens_out,
            "cr_used":    cr_used,
            "plan":       current_plan,
        }).execute()
    except Exception:
        pass

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
            plan = next((p for p, pid in STRIPE_PRICE_IDS.items() if pid == price_id), "plus")
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

    base_url = os.environ.get("APP_BASE_URL", "https://betaship.web.app")
    session = stripe.checkout.Session.create(
        mode=mode,
        line_items=[{"price": price_id, "quantity": 1}],
        metadata={"user_id": uid, "price_id": price_id},
        success_url=f"{base_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/",
    )
    return jsonify({"url": session.url})


# --------------------------------------------------------
# GET /api/admin/health-check  — ローンチ準備チェック
# --------------------------------------------------------
@app.route("/api/admin/health-check", methods=["GET"])
@_require_admin
def admin_health_check():
    import urllib.request as _ur2
    import json as _json
    product_id = request.args.get("product")
    if not product_id:
        return jsonify({"error": "product required"}), 400

    c: dict = {}

    # Betaship DB
    try:
        _sb.schema("betaship").table("plan_config").select("plan").limit(1).execute()
        c["betaship_db"] = True
    except Exception:
        c["betaship_db"] = False

    # Product config
    product_url = ""
    try:
        row = _sb.schema("betaship").table("product_config").select("*").eq(
            "product_id", product_id
        ).maybe_single().execute()
        cfg = row.data or {}
        c["product_config"]    = bool(cfg)
        c["free_daily_limit"]  = int(cfg.get("free_daily_limit", 0)) > 0
        c["billing_active"]    = bool(cfg.get("billing_active", False))
        c["free_mode"]         = bool(cfg.get("free_mode", False))
        product_url            = cfg.get("product_url", "")
    except Exception:
        c["product_config"] = c["free_daily_limit"] = c["billing_active"] = c["free_mode"] = False

    # Product self-report (/api/status)
    ps: dict = {}
    if product_url:
        try:
            req = _ur2.Request(
                f"{product_url}/api/status",
                headers={"Accept": "application/json"},
            )
            with _ur2.urlopen(req, timeout=8) as resp:
                ps = _json.loads(resp.read().decode())
        except Exception:
            pass
    c["product_reachable"]           = bool(ps)
    c["product_stripe_live"]         = ps.get("stripe_mode") == "live"
    c["product_webhook_configured"]  = bool(ps.get("webhook_configured"))
    c["product_supabase_ok"]         = bool(ps.get("supabase_db_reachable"))

    # Stripe portal
    try:
        configs = stripe.billing_portal.Configuration.list(limit=5)
        c["stripe_portal"] = any(cfg.active for cfg in (configs.data or []))
    except Exception:
        c["stripe_portal"] = False

    # Stripe webhook endpoint
    if product_url:
        try:
            webhooks = stripe.WebhookEndpoint.list(limit=20)
            c["stripe_webhook"] = any(
                product_url in (wh.url or "") and wh.status == "enabled"
                for wh in (webhooks.data or [])
            )
        except Exception:
            c["stripe_webhook"] = False
    else:
        c["stripe_webhook"] = None

    return jsonify(c)


# --------------------------------------------------------
# POST /api/admin/activate-billing  — 課金を有効化
# --------------------------------------------------------
@app.route("/api/admin/activate-billing", methods=["POST"])
@_require_admin
def admin_activate_billing():
    body = request.get_json(force=True) or {}
    product_id = body.get("product_id")
    if not product_id:
        return jsonify({"error": "product_id required"}), 400
    _sb.schema("betaship").table("product_config").upsert({
        "product_id":     product_id,
        "billing_active": True,
        "free_mode":      False,
        "updated_at":     datetime.now(timezone.utc).isoformat(),
    }).execute()
    return jsonify({"ok": True})


# --------------------------------------------------------
# GET /api/config  — プロダクトが設定を読む公開エンドポイント
# --------------------------------------------------------
@app.route("/api/config", methods=["GET"])
def get_product_config():
    product_id = request.args.get("product")
    if not product_id:
        return jsonify({"error": "product required"}), 400
    try:
        row = _sb.schema("betaship").table("product_config").select(
            "product_id,free_mode,billing_active,maintenance_mode,free_daily_limit,"
            "display_name,description,welcome_message,model,hosted"
        ).eq("product_id", product_id).maybe_single().execute()
        if row.data:
            return jsonify(row.data)
    except Exception:
        pass
    return jsonify({
        "product_id": product_id, "free_daily_limit": 5, "free_mode": False,
        "maintenance_mode": False, "billing_active": False,
        "display_name": "", "description": "", "welcome_message": "",
        "model": "claude-haiku-4-5-20251001", "hosted": False,
    })


# --------------------------------------------------------
# GET /api/admin/status  — 全体状態
# --------------------------------------------------------
@app.route("/api/admin/status", methods=["GET"])
@_require_admin
def admin_status():
    plans = _sb.schema("betaship").table("plan_config").select("*").execute()
    products = _sb.schema("betaship").table("product_config").select("*").execute()

    sub_rows = _sb.schema("betaship").table("subscriptions").select("plan").execute()
    plan_counts: dict = {}
    for row in (sub_rows.data or []):
        p = row.get("plan", "free")
        plan_counts[p] = plan_counts.get(p, 0) + 1

    try:
        stripe.Account.retrieve()
        stripe_ok = True
    except Exception:
        stripe_ok = False

    return jsonify({
        "plans": plans.data or [],
        "products": products.data or [],
        "stripe_ok": stripe_ok,
        "user_count": len(sub_rows.data or []),
        "plan_counts": plan_counts,
    })


# --------------------------------------------------------
# PATCH /api/admin/plan-config  — プラン設定変更
# --------------------------------------------------------
@app.route("/api/admin/plan-config", methods=["PATCH"])
@_require_admin
def admin_update_plan():
    body = request.get_json(force=True) or {}
    plan = body.get("plan")
    if not plan:
        return jsonify({"error": "plan required"}), 400
    updates = {}
    if body.get("monthly_cr") is not None:
        updates["monthly_cr"] = int(body["monthly_cr"])
    if body.get("price_usd") is not None:
        updates["price_usd"] = float(body["price_usd"])
    if not updates:
        return jsonify({"error": "nothing to update"}), 400
    _sb.schema("betaship").table("plan_config").update(updates).eq("plan", plan).execute()
    return jsonify({"ok": True})


# --------------------------------------------------------
# PATCH /api/admin/product-config  — プロダクト設定変更
# --------------------------------------------------------
@app.route("/api/admin/product-config", methods=["PATCH"])
@_require_admin
def admin_update_product():
    body = request.get_json(force=True) or {}
    product_id = body.get("product_id")
    if not product_id:
        return jsonify({"error": "product_id required"}), 400
    updates = {k: v for k, v in body.items() if k != "product_id"}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    _sb.schema("betaship").table("product_config").upsert(
        {"product_id": product_id, **updates}
    ).execute()
    return jsonify({"ok": True})


# --------------------------------------------------------
# POST /api/admin/coupon  — Stripeクーポン発行
# --------------------------------------------------------
@app.route("/api/admin/coupon", methods=["POST"])
@_require_admin
def admin_create_coupon():
    body = request.get_json(force=True) or {}
    percent_off = body.get("percent_off")
    duration = body.get("duration", "once")
    name = body.get("name", "キャンペーン割引")
    if not percent_off:
        return jsonify({"error": "percent_off required"}), 400
    try:
        coupon = stripe.Coupon.create(
            percent_off=int(percent_off),
            duration=duration,
            name=name,
        )
        return jsonify({"ok": True, "coupon_id": coupon.id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------------
# GET /api/admin/analytics  — アナリティクスデータ
# --------------------------------------------------------
@app.route("/api/admin/analytics", methods=["GET"])
@_require_admin
def admin_analytics():
    days = int(request.args.get("days", 7))
    since = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)).isoformat()

    rows = _sb.schema("betaship").table("ai_calls").select(
        "service,model,plan,tokens_in,tokens_out,cr_used,user_id,ts"
    ).gte("ts", since).execute()
    data = rows.data or []

    by_service: dict = {}
    for r in data:
        svc = r.get("service", "unknown")
        s = by_service.setdefault(svc, {"calls": 0, "cr": 0, "users": set()})
        s["calls"] += 1
        s["cr"]    += r.get("cr_used", 0)
        if r.get("user_id"):
            s["users"].add(r["user_id"])
    for v in by_service.values():
        v["users"] = len(v["users"])

    by_model: dict = {}
    for r in data:
        m = r.get("model", "unknown")
        by_model[m] = by_model.get(m, 0) + 1

    by_plan: dict = {}
    for r in data:
        p = r.get("plan", "free")
        by_plan[p] = by_plan.get(p, 0) + 1

    daily: dict = {}
    for r in data:
        d = (r.get("ts") or "")[:10]
        if d:
            daily[d] = daily.get(d, 0) + 1

    return jsonify({
        "days": days,
        "total_calls":   len(data),
        "total_cr":      sum(r.get("cr_used", 0) for r in data),
        "unique_users":  len({r["user_id"] for r in data if r.get("user_id")}),
        "by_service":    by_service,
        "by_model":      by_model,
        "by_plan":       by_plan,
        "daily":         dict(sorted(daily.items())),
    })


# --------------------------------------------------------
# GET /tools/<product_id>  — hosted chat UI 配信
# --------------------------------------------------------
@app.route("/tools/<product_id>")
def tool_page(product_id):
    return send_file(os.path.join(os.path.dirname(__file__), "tool.html"))


# --------------------------------------------------------
# GET /admin  — 管理画面HTML配信
# --------------------------------------------------------
@app.route("/")
def index_page():
    import os
    return send_file(os.path.join(os.path.dirname(__file__), "index.html"))


@app.route("/widget.js")
def widget_js():
    import os
    from flask import Response
    path = os.path.join(os.path.dirname(__file__), "widget.js")
    with open(path) as f:
        code = f.read()
    return Response(code, mimetype="application/javascript",
                    headers={"Cache-Control": "public, max-age=300", "Access-Control-Allow-Origin": "*"})


@app.route("/admin")
def admin_page():
    import os
    token = request.args.get("token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        return "Unauthorized", 401
    return send_file(os.path.join(os.path.dirname(__file__), "admin.html"))


# --------------------------------------------------------
# GET /health  /api/ping
# --------------------------------------------------------
@app.route("/health")
@app.route("/api/ping")
def health():
    return jsonify({"ok": True})


def _start_keepalive():
    keepalive_url = os.environ.get("KEEPALIVE_URL", "")
    if not keepalive_url:
        return
    import time, threading, urllib.request as _ur
    def _ping():
        while True:
            time.sleep(8 * 60)
            try:
                _ur.urlopen(keepalive_url + "/api/ping", timeout=10)
            except Exception:
                pass
    threading.Thread(target=_ping, daemon=True).start()

_start_keepalive()

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5099)), debug=False)
