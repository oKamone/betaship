(function () {
  'use strict';

  var SB_URL = 'https://kphfolcpguniaaefcgcw.supabase.co';
  var SB_KEY = 'sb_publishable_-mJ-zO_4n5ZKqjP53WDXFg_ZkHcdiwe';
  var BS_URL = 'https://betaship.web.app';
  var PLAN_LABEL = { free: 'Free', plus: 'Plus', pro: 'Pro' };
  var PLAN_COLOR  = { free: '#6a90a8', plus: '#c8a84b', pro: '#a78bfa' };

  var _session = null;

  // ── Public API（DOM構築前から呼べる）────────────────────────
  window.bsGetToken = function () { return _session ? _session.access_token : null; };

  window.bsGate = function () {
    var m = document.getElementById('_bs-gate');
    if (m) { m.style.display = 'flex'; }
  };

  // ── 底部バッジ（ブランドリンク）──────────────────────────────
  function createBadge() {
    var el = document.createElement('a');
    el.id = '_bs-badge';
    el.href = BS_URL;
    el.target = '_blank';
    el.rel = 'noopener noreferrer';
    el.setAttribute('aria-label', 'Betaship');
    el.setAttribute('style', [
      'position:fixed',
      'bottom:max(16px,env(safe-area-inset-bottom,16px))',
      'left:16px',
      'z-index:2147483647',
      'display:inline-flex',
      'align-items:center',
      'gap:5px',
      'padding:5px 10px',
      'border-radius:99px',
      'background:rgba(5,13,26,0.82)',
      'border:1px solid rgba(13,148,136,0.25)',
      'backdrop-filter:blur(10px)',
      '-webkit-backdrop-filter:blur(10px)',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
      'font-size:11px',
      'font-weight:600',
      'color:#6a90a8',
      'text-decoration:none',
      'cursor:pointer',
      'box-shadow:0 2px 12px rgba(0,0,0,0.4)',
      'transition:opacity 0.2s',
      'opacity:0',
      'pointer-events:none',
    ].join(';'));
    el.innerHTML = '<span style="font-size:12px">🧭</span><span id="_bs-label"></span>';
    document.body.appendChild(el);
    return el;
  }

  function showBadge(el, plan) {
    var label = document.getElementById('_bs-label');
    if (label) {
      label.textContent = plan ? (PLAN_LABEL[plan] || plan) : 'Betaship';
      label.style.color = plan ? (PLAN_COLOR[plan] || '#6a90a8') : '#6a90a8';
    }
    el.style.opacity = '0.85';
    el.style.pointerEvents = 'auto';
  }

  // ── 右上認証チップ ─────────────────────────────────────────
  function createChip() {
    var el = document.createElement('div');
    el.id = '_bs-chip';
    el.setAttribute('style', [
      'position:fixed',
      'top:max(12px,env(safe-area-inset-top,12px))',
      'right:16px',
      'z-index:2147483647',
      'display:inline-flex',
      'align-items:center',
      'gap:6px',
      'padding:6px 14px',
      'border-radius:99px',
      'background:rgba(5,13,26,0.82)',
      'border:1px solid rgba(13,148,136,0.25)',
      'backdrop-filter:blur(10px)',
      '-webkit-backdrop-filter:blur(10px)',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
      'font-size:12px',
      'font-weight:600',
      'cursor:pointer',
      'box-shadow:0 2px 12px rgba(0,0,0,0.4)',
      'transition:opacity 0.2s',
      'opacity:0',
      'pointer-events:none',
      'user-select:none',
      '-webkit-user-select:none',
    ].join(';'));
    document.body.appendChild(el);
    return el;
  }

  function showChipLoggedOut(chip) {
    chip.innerHTML = '<span style="color:#e2e8f0;letter-spacing:0.01em">ログイン</span>';
    chip.style.opacity = '0.9';
    chip.style.pointerEvents = 'auto';
    chip.onclick = function () {
      location.href = BS_URL + '/?return_to=' + encodeURIComponent(location.href);
    };
  }

  function showChipLoggedIn(chip, totalCr, plan) {
    var color = PLAN_COLOR[plan] || '#6a90a8';
    chip.innerHTML =
      '<span style="color:' + color + ';font-size:8px;line-height:1">●</span>' +
      '<span style="color:#e2e8f0">' +
      (totalCr !== null ? totalCr + 'cr' : PLAN_LABEL[plan] || plan) +
      '</span>';
    chip.style.opacity = '0.9';
    chip.style.pointerEvents = 'auto';
    chip.onclick = function () { window.open(BS_URL, '_blank', 'noopener'); };
  }

  // ── クレジットゲートモーダル ────────────────────────────────
  function createGateModal() {
    var overlay = document.createElement('div');
    overlay.id = '_bs-gate';
    overlay.setAttribute('style', [
      'display:none',
      'position:fixed',
      'inset:0',
      'z-index:2147483646',
      'background:rgba(0,0,0,0.65)',
      'backdrop-filter:blur(6px)',
      '-webkit-backdrop-filter:blur(6px)',
      'align-items:center',
      'justify-content:center',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
    ].join(';'));

    overlay.innerHTML = [
      '<div style="',
        'background:rgb(5,13,26);',
        'border:1px solid rgba(13,148,136,0.3);',
        'border-radius:20px;',
        'padding:36px 28px 28px;',
        'max-width:300px;',
        'width:calc(100% - 48px);',
        'text-align:center;',
        'box-shadow:0 24px 80px rgba(0,0,0,0.7);',
      '">',
        '<div style="font-size:28px;margin-bottom:14px">✦</div>',
        '<div style="font-size:16px;font-weight:700;color:#e2e8f0;margin-bottom:8px">クレジットが切れました</div>',
        '<div style="font-size:13px;color:#6a90a8;line-height:1.7;margin-bottom:24px">',
          'Betashipでクレジットを補充すると<br>引き続きご利用いただけます。',
        '</div>',
        '<a href="' + BS_URL + '" target="_blank" rel="noopener" style="',
          'display:block;padding:12px 20px;border-radius:99px;',
          'background:linear-gradient(135deg,#0d9488,#7c3aed);',
          'color:#fff;font-size:14px;font-weight:700;text-decoration:none;',
          'margin-bottom:10px;',
        '">クレジットを補充する</a>',
        '<button id="_bs-gate-close" style="',
          'display:block;width:100%;padding:10px;border:none;background:none;',
          'color:#6a90a8;font-size:13px;cursor:pointer;',
        '">閉じる</button>',
      '</div>',
    ].join('');

    document.body.appendChild(overlay);
    document.getElementById('_bs-gate-close').addEventListener('click', function () {
      overlay.style.display = 'none';
    });
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) overlay.style.display = 'none';
    });
  }

  // ── 初期化 ──────────────────────────────────────────────────
  async function init() {
    var badge = createBadge();
    var chip  = createChip();
    createGateModal();

    async function getSupabase() {
      if (window.supabase && window.supabase.createClient) return window.supabase;
      await new Promise(function (res, rej) {
        var sc = document.createElement('script');
        sc.src = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js';
        sc.onload = res; sc.onerror = rej;
        document.head.appendChild(sc);
      });
      return window.supabase;
    }

    try {
      var sb = await getSupabase();
      var client = sb.createClient(SB_URL, SB_KEY, {
        auth: { persistSession: true, detectSessionInUrl: false }
      });

      // SSO: bs_token が URL にあればセッションを確立してから URL をクリーン
      var _p = new URLSearchParams(location.search);
      var _bt = _p.get('bs_token'), _br = _p.get('bs_refresh');
      if (_bt && _br) {
        try {
          await client.auth.setSession({ access_token: _bt, refresh_token: _br });
          var _u = new URL(location.href);
          _u.searchParams.delete('bs_token'); _u.searchParams.delete('bs_refresh');
          history.replaceState({}, '', _u);
        } catch (_) {}
      }

      var { data } = await client.auth.getSession();
      var session = data && data.session;
      _session = session;

      if (!session) {
        showBadge(badge, null);
        showChipLoggedOut(chip);
        return;
      }

      try {
        var r = await fetch(BS_URL + '/api/credits', {
          headers: { 'Authorization': 'Bearer ' + session.access_token }
        });
        if (r.ok) {
          var d = await r.json();
          var plan = d.plan || 'free';
          var totalCr = typeof d.total_cr === 'number' ? d.total_cr : null;
          showBadge(badge, plan);
          showChipLoggedIn(chip, totalCr, plan);
          return;
        }
      } catch (_) {}
      showBadge(badge, 'free');
      showChipLoggedIn(chip, null, 'free');
    } catch (_) {
      showBadge(badge, null);
      showChipLoggedOut(chip);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
