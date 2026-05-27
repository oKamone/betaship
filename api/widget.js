(function () {
  'use strict';

  var SB_URL = 'https://kphfolcpguniaaefcgcw.supabase.co';
  var SB_KEY = 'sb_publishable_-mJ-zO_4n5ZKqjP53WDXFg_ZkHcdiwe';
  var BS_URL = 'https://betaship.web.app';
  var PLAN_LABEL = { free: 'Free', plus: 'Plus', pro: 'Pro' };
  var PLAN_COLOR  = { free: '#6a90a8', plus: '#c8a84b', pro: '#a78bfa' };

  function create() {
    var el = document.createElement('a');
    el.id = '_bs-badge';
    el.href = BS_URL;
    el.target = '_blank';
    el.rel = 'noopener noreferrer';
    el.setAttribute('aria-label', 'Betaship');

    var style = [
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
    ].join(';');
    el.setAttribute('style', style);

    el.innerHTML = '<span style="font-size:12px">🧭</span><span id="_bs-label"></span>';
    document.body.appendChild(el);
    return el;
  }

  function show(el, plan) {
    var label = document.getElementById('_bs-label');
    if (label) {
      label.textContent = plan ? (PLAN_LABEL[plan] || plan) : 'Betaship';
      label.style.color = plan ? (PLAN_COLOR[plan] || '#6a90a8') : '#6a90a8';
    }
    el.style.opacity = '0.85';
    el.style.pointerEvents = 'auto';
  }

  async function init() {
    var el = create();

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
      var { data } = await client.auth.getSession();
      var session = data && data.session;

      if (!session) {
        show(el, null);
        return;
      }

      try {
        var r = await fetch(BS_URL + '/api/credits', {
          headers: { 'Authorization': 'Bearer ' + session.access_token }
        });
        if (r.ok) {
          var d = await r.json();
          show(el, d.plan || 'free');
          return;
        }
      } catch (_) {}
      show(el, 'free');
    } catch (_) {
      show(el, null);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
