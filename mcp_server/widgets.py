"""
MCP UI components (widgets) for the Peek-A-Box UCP server.

These render an interactive buying experience inside MCP hosts that support UI
resources — both ChatGPT (OpenAI Apps SDK) and Claude / other MCP Apps hosts
(SEP-1865) — from a single implementation:

  * Each widget is a self-contained inline HTML document (no build step, no CDN).
  * A tiny bridge (`window.PAB`) normalizes the two host APIs:
      - ChatGPT: `window.openai.toolOutput` / `.callTool` / `.sendFollowUpMessage`
        / `.openExternal`, and the `openai:set_globals` event.
      - MCP Apps (Claude): JSON-RPC over `postMessage` — `ui/initialize` handshake,
        `ui/notifications/tool-result`, and the classic mcp-ui `{type,payload}`
        actions that `@mcp-ui/client` bridges (`tool`, `prompt`, `link`).
  * Widgets read their data from the tool result's `structuredContent`, so the
    HTML template is static and shared across calls.

Each widget is registered twice — once as `text/html+skybridge` (what ChatGPT
consumes) and once as `text/html;profile=mcp-app` (what MCP Apps hosts negotiate)
— and the tool descriptor advertises both via `openai/outputTemplate` and
`ui.resourceUri`.

Spec references:
  * OpenAI Apps SDK: https://developers.openai.com/apps-sdk/reference
  * MCP Apps (SEP-1865): https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/
"""

# ── Shared styles (Peek-A-Box warm/taupe + teal brand, light + dark) ──────────
_CSS = r"""
:root{
  --bg: oklch(0.98 0.01 70);
  --fg: oklch(0.25 0.03 55);
  --card: oklch(1 0 0);
  --muted: oklch(0.5 0.03 55);
  --primary: oklch(0.62 0.09 55);
  --primary-fg: oklch(0.99 0.01 70);
  --accent: oklch(0.5 0.12 175);
  --border: oklch(0.85 0.04 60);
  --soft: oklch(0.94 0.02 70);
  --danger: oklch(0.55 0.2 25);
  --shadow: 0 1px 2px rgba(0,0,0,.06), 0 8px 24px rgba(0,0,0,.05);
}
:root[data-theme="dark"]{
  --bg: oklch(0.18 0.02 55);
  --fg: oklch(0.92 0.02 70);
  --card: oklch(0.23 0.025 55);
  --muted: oklch(0.72 0.03 70);
  --primary: oklch(0.74 0.09 55);
  --primary-fg: oklch(0.18 0.02 55);
  --accent: oklch(0.7 0.12 175);
  --border: oklch(0.36 0.03 55);
  --soft: oklch(0.27 0.025 55);
  --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color:var(--fg); background:transparent; padding:4px; line-height:1.45;
  -webkit-font-smoothing:antialiased;
}
.brandbar{display:flex;align-items:center;gap:8px;margin:2px 4px 12px}
.brandbar .logo{font-size:18px}
.brandbar .name{font-weight:700;letter-spacing:-.01em}
.brandbar .tag{color:var(--muted);font-size:12px;margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.card{
  background:var(--card);border:1px solid var(--border);border-radius:14px;
  overflow:hidden;display:flex;flex-direction:column;box-shadow:var(--shadow);
}
.thumb{aspect-ratio:1/1;background:var(--soft);display:flex;align-items:center;justify-content:center;position:relative}
.thumb img{width:100%;height:100%;object-fit:cover}
.thumb .emoji{font-size:40px;opacity:.85}
.badge{
  position:absolute;top:8px;left:8px;background:var(--accent);color:var(--primary-fg);
  font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  padding:3px 7px;border-radius:999px;
}
.body{padding:10px 12px 12px;display:flex;flex-direction:column;gap:4px;flex:1}
.title{font-weight:650;font-size:14px}
.desc{color:var(--muted);font-size:12px;flex:1}
.price{font-weight:750;font-size:15px;margin-top:4px}
.btn{
  appearance:none;border:0;cursor:pointer;border-radius:10px;font-weight:650;
  font-size:13px;padding:9px 12px;background:var(--primary);color:var(--primary-fg);
  transition:filter .15s ease, transform .05s ease;width:100%;
}
.btn:hover{filter:brightness(1.05)}
.btn:active{transform:translateY(1px)}
.btn[disabled]{opacity:.6;cursor:default}
.btn.ghost{background:var(--soft);color:var(--fg);border:1px solid var(--border)}
.btn.accent{background:var(--accent)}
.panel{background:var(--card);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:16px;max-width:520px}
.rows{display:flex;flex-direction:column;gap:2px;margin:6px 0}
.row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px dashed var(--border);font-size:14px}
.row:last-child{border-bottom:0}
.row .q{color:var(--muted);font-size:12px}
.totals{margin-top:8px;border-top:1px solid var(--border);padding-top:10px;display:flex;flex-direction:column;gap:6px}
.totals .line,.totals .grand{display:flex;justify-content:space-between;font-size:14px}
.totals .line{color:var(--muted)}
.totals .grand{color:var(--fg);font-weight:800;font-size:17px;margin-top:2px}
.buyer{font-size:12px;color:var(--muted);margin-top:10px}
.actions{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}
.actions .btn{width:auto;flex:1;min-width:140px}
.note{font-size:12.5px;color:var(--muted);margin-top:10px;background:var(--soft);border-radius:10px;padding:9px 11px}
.err{border-left:3px solid var(--danger);background:var(--soft);padding:10px 12px;border-radius:8px;font-size:13px;margin:6px 0}
.empty{color:var(--muted);text-align:center;padding:28px;font-size:14px}
.hero{display:flex;align-items:center;gap:12px}
.hero .mark{width:44px;height:44px;border-radius:12px;background:var(--accent);color:var(--primary-fg);display:flex;align-items:center;justify-content:center;font-size:22px}
.hero h2{margin:0;font-size:18px}
.hero p{margin:2px 0 0;color:var(--muted);font-size:13px}
.pill{display:inline-block;font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;background:var(--soft);color:var(--muted)}
.pill.ok{background:oklch(0.9 0.09 150);color:oklch(0.32 0.1 150)}
:root[data-theme="dark"] .pill.ok{background:oklch(0.35 0.08 150);color:oklch(0.9 0.09 150)}
"""

# ── Host bridge: normalizes ChatGPT (window.openai) and MCP Apps (postMessage) ─
_BRIDGE = r"""
(function () {
  var seq = 0;
  function nid(p){ return p + '-' + Date.now() + '-' + (++seq); }
  var PAB = window.PAB = {};
  var latest = null;

  function oai(){ return window.openai; }

  PAB.getData = function () {
    if (oai() && oai().toolOutput) return oai().toolOutput;
    return latest;
  };
  PAB.theme = function () {
    if (oai() && oai().theme) return oai().theme;
    var attr = document.documentElement.getAttribute('data-theme');
    if (attr) return attr;
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  };
  PAB.callTool = function (name, args) {
    if (oai() && typeof oai().callTool === 'function') return oai().callTool(name, args || {});
    window.parent.postMessage({ type:'tool', messageId:nid(name), payload:{ toolName:name, params:args || {} } }, '*');
    return Promise.resolve();
  };
  PAB.sendPrompt = function (prompt) {
    if (oai() && typeof oai().sendFollowUpMessage === 'function') return oai().sendFollowUpMessage({ prompt: prompt });
    window.parent.postMessage({ type:'prompt', messageId:nid('prompt'), payload:{ prompt: prompt } }, '*');
    return Promise.resolve();
  };
  PAB.openLink = function (url) {
    if (!url) return;
    if (oai() && typeof oai().openExternal === 'function') return oai().openExternal({ href: url });
    window.parent.postMessage({ type:'link', messageId:nid('link'), payload:{ url: url } }, '*');
  };

  function applyTheme(){ document.documentElement.setAttribute('data-theme', PAB.theme()); }
  PAB.emit = function () { applyTheme(); window.dispatchEvent(new CustomEvent('pab:data')); };

  // ChatGPT — globals updates (theme, toolOutput, displayMode, ...)
  window.addEventListener('openai:set_globals', PAB.emit);

  // MCP Apps (Claude) — JSON-RPC over postMessage
  window.addEventListener('message', function (e) {
    var m = e && e.data;
    if (!m || typeof m !== 'object') return;
    var method = m.method || '';
    if (method.indexOf('tool-result') !== -1 || method.indexOf('tool-input') !== -1) {
      var p = m.params || {};
      var d = p.structuredContent || p.structured_content ||
              (p.result && (p.result.structuredContent || p.result.structured_content)) ||
              p.result || p.toolOutput || null;
      if (d) { latest = d; PAB.emit(); }
    }
    if (method.indexOf('host-context-changed') !== -1 && m.params && m.params.hostContext) {
      if (m.params.hostContext.theme) document.documentElement.setAttribute('data-theme', m.params.hostContext.theme);
      PAB.emit();
    }
    if (m.result && m.result.hostContext && m.result.hostContext.theme) {
      document.documentElement.setAttribute('data-theme', m.result.hostContext.theme);
      PAB.emit();
    }
  });

  // MCP Apps handshake — announce readiness so the host delivers the tool result.
  try {
    window.parent.postMessage({ jsonrpc:'2.0', id:nid('init'), method:'ui/initialize',
      params:{ protocolVersion:'2026-01-26', capabilities:{}, clientInfo:{ name:'peek-a-box-widget', version:'1.0.0' } } }, '*');
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/initialized', params:{} }, '*');
  } catch (e) {}

  PAB.money = function (cents, cur) {
    cur = cur || 'USD';
    var v = (Number(cents) || 0) / 100;
    if (cur === 'USD') return '$' + v.toFixed(2);
    return v.toFixed(2) + ' ' + cur;
  };
  PAB.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c];
    });
  };
  PAB.errorsOf = function (d) {
    var msgs = (d && d.messages) || [];
    return msgs.filter(function (m) { return m && m.type === 'error'; });
  };

  applyTheme();
  if (document.readyState !== 'loading') PAB.emit();
  else document.addEventListener('DOMContentLoaded', PAB.emit);
})();
"""

# ── Per-widget render scripts ─────────────────────────────────────────────────

_CATALOG_JS = r"""
function card(it){
  var badge = it.badge ? '<span class="badge">'+PAB.esc(it.badge)+'</span>' : '';
  var img = (it.images && it.images[0] && it.images[0].url) ? it.images[0].url : (it.image || '');
  var thumb = img
    ? '<img src="'+PAB.esc(img)+'" alt="'+PAB.esc(it.title)+'" onerror="this.replaceWith(Object.assign(document.createElement(\'div\'),{className:\'emoji\',textContent:\'\\uD83D\\uDCE6\'}))">'
    : '<div class="emoji">📦</div>';
  return ''
    + '<div class="card">'
    +   '<div class="thumb">'+badge+thumb+'</div>'
    +   '<div class="body">'
    +     '<div class="title">'+PAB.esc(it.title)+'</div>'
    +     '<div class="desc">'+PAB.esc(it.description||'')+'</div>'
    +     '<div class="price">'+PAB.money(it.price, it.currency)+'</div>'
    +     '<button class="btn" data-add="'+PAB.esc(it.id)+'" data-name="'+PAB.esc(it.title)+'">Add to checkout</button>'
    +   '</div>'
    + '</div>';
}
function render(){
  var d = PAB.getData() || {};
  var root = document.getElementById('root');
  var errs = PAB.errorsOf(d);
  if (errs.length){ root.innerHTML = '<div class="err">'+PAB.esc(errs[0].content||'Something went wrong.')+'</div>'; return; }
  var items = d.items || [];
  if (!items.length){ root.innerHTML = '<div class="empty">No boxes match that search. Try &ldquo;haunted&rdquo;, &ldquo;premium&rdquo;, or browse the whole shelf.</div>'; return; }
  root.innerHTML = '<div class="grid">'+items.map(card).join('')+'</div>';
  root.querySelectorAll('[data-add]').forEach(function(b){
    b.addEventListener('click', function(){
      var name = b.getAttribute('data-name'), id = b.getAttribute('data-add');
      b.disabled = true; b.textContent = 'Adding…';
      PAB.sendPrompt('Create a checkout for ' + name + ' (' + id + '), quantity 1, and show me the cart.');
    });
  });
}
window.addEventListener('pab:data', render);
"""

_CHECKOUT_JS = r"""
function uuid(){
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,function(c){
    var r = Math.random()*16|0, v = c==='x'?r:(r&0x3|0x8); return v.toString(16);
  });
}
function lineRow(li){
  var it = li.item || {};
  return '<div class="row"><div>'+PAB.esc(it.title||it.id)
    +'<div class="q">Qty '+(li.quantity||1)+'</div></div>'
    +'<div>'+PAB.money((it.price||0)*(li.quantity||1))+'</div></div>';
}
function totalRow(t){
  var label = t.display_text || ({subtotal:'Subtotal', fulfillment:'Shipping', total:'Total', tax:'Tax'}[t.type] || t.type);
  var cls = t.type === 'total' ? 'grand' : 'line';
  return '<div class="'+cls+'"><span>'+PAB.esc(label)+'</span><span>'+PAB.money(t.amount)+'</span></div>';
}
function render(){
  var c = PAB.getData() || {};
  var root = document.getElementById('root');
  var errs = PAB.errorsOf(c);
  if (errs.length){
    var e = errs[0];
    var needLogin = (e.code||'').match(/identity|insufficient_scope|unauthor/i);
    root.innerHTML = '<div class="panel"><div class="hero"><div class="mark">🔐</div>'
      + '<div><h2>'+(needLogin?'Sign-in needed':'Checkout error')+'</h2>'
      + '<p>'+PAB.esc(e.content||'This checkout could not be prepared.')+'</p></div></div></div>';
    return;
  }
  var items = c.line_items || [];
  var totals = c.totals || [];
  var buyer = c.buyer || null;
  var qty = items.reduce(function(a,li){return a+(li.quantity||1);},0);
  var multi = qty > 1;

  var buyerHtml = buyer && (buyer.name || buyer.email)
    ? '<div class="buyer">For '+PAB.esc(buyer.name||'')+(buyer.email?(' &middot; '+PAB.esc(buyer.email)):'')+'</div>'
    : '';

  root.innerHTML = ''
    + '<div class="panel">'
    +   '<div class="hero"><div class="mark">🛍️</div><div><h2>Review your order</h2>'
    +     '<p>Peek-A-Box &middot; '+items.length+' item'+(items.length===1?'':'s')+'</p></div></div>'
    +   '<div class="rows">'+items.map(lineRow).join('')+'</div>'
    +   '<div class="totals">'+totals.map(totalRow).join('')+'</div>'
    +   buyerHtml
    +   (multi ? '<div class="note">Carts with more than one item are confirmed in the browser for your security.</div>' : '')
    +   '<div class="actions">'
    +     (multi
        ? '<button class="btn" data-open>Review &amp; pay in browser</button>'
        : '<button class="btn" data-complete>Complete purchase</button>'
          + '<button class="btn ghost" data-open>Open in browser</button>')
    +   '</div>'
    + '</div>';

  var openBtn = root.querySelector('[data-open]');
  if (openBtn) openBtn.addEventListener('click', function(){ PAB.openLink(c.continue_url); });

  var payBtn = root.querySelector('[data-complete]');
  if (payBtn) payBtn.addEventListener('click', function(){
    payBtn.disabled = true; payBtn.textContent = 'Placing order…';
    PAB.sendPrompt('Complete checkout ' + c.id + ' and place the order.');
  });
}
window.addEventListener('pab:data', render);
"""

_CONFIRM_JS = r"""
function totalOf(c){
  var t = (c.totals||[]).filter(function(x){return x.type==='total';})[0];
  return t ? PAB.money(t.amount, c.currency) : '';
}
function render(){
  var c = PAB.getData() || {};
  var root = document.getElementById('root');

  var errs = PAB.errorsOf(c);
  if (errs.length){
    var e = errs[0];
    root.innerHTML = '<div class="panel"><div class="hero"><div class="mark">⚠️</div>'
      + '<div><h2>Payment didn’t go through</h2><p>'+PAB.esc(e.content||'')+'</p></div></div>'
      + (c.continue_url?'<div class="actions"><button class="btn" data-open>Try in browser</button></div>':'')
      + '</div>';
    var ob = root.querySelector('[data-open]'); if (ob) ob.addEventListener('click', function(){PAB.openLink(c.continue_url);});
    return;
  }

  // Not finished yet — review/auth required.
  if (c.status && c.status !== 'completed'){
    root.innerHTML = '<div class="panel"><div class="hero"><div class="mark">🔐</div>'
      + '<div><h2>One more step</h2><p>'+PAB.esc((c.messages&&c.messages[0]&&c.messages[0].content)||'Finish this order in your browser.')+'</p></div></div>'
      + '<div class="actions"><button class="btn" data-open>Continue in browser</button></div></div>';
    root.querySelector('[data-open]').addEventListener('click', function(){PAB.openLink(c.continue_url);});
    return;
  }

  var order = c.order || {};
  var link = order.permalink_url || c.permalink_url;
  var simulated = c.payment && c.payment.simulated;
  root.innerHTML = ''
    + '<div class="panel">'
    +   '<div class="hero"><div class="mark">🎉</div><div>'
    +     '<h2>Order confirmed</h2><p>Thanks for shopping at Peek-A-Box</p></div></div>'
    +   '<div class="rows"><div class="row"><div>Order</div><div>'+PAB.esc(order.id||c.id||'')+'</div></div>'
    +     '<div class="row"><div>Total charged</div><div>'+totalOf(c)+'</div></div>'
    +     '<div class="row"><div>Status</div><div><span class="pill ok">Completed</span></div></div></div>'
    +   (simulated ? '<div class="note">Demo mode: no Stripe key configured, so the charge was simulated.</div>' : '')
    +   (link ? '<div class="actions"><button class="btn accent" data-view>View your order</button></div>' : '')
    + '</div>';
  var vb = root.querySelector('[data-view]');
  if (vb) vb.addEventListener('click', function(){ PAB.openLink(link); });
}
window.addEventListener('pab:data', render);
"""


def _doc(title: str, render_js: str) -> str:
    """Assemble a full, self-contained widget HTML document."""
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>" + title + "</title><style>" + _CSS + "</style></head><body>"
        "<div class=\"brandbar\"><span class=\"logo\">\U0001F4E6</span>"
        "<span class=\"name\">Peek-A-Box</span>"
        "<span class=\"tag\">mystery box store</span></div>"
        "<div id=\"root\"><div class=\"empty\">Loading…</div></div>"
        "<script>" + _BRIDGE + "</script>"
        "<script>" + render_js + "</script>"
        "</body></html>"
    )


# ── Widget registry ───────────────────────────────────────────────────────────

WIDGETS = {
    "catalog": {
        "title": "Peek-A-Box catalog",
        "description": "A grid of Peek-A-Box mystery boxes with prices and an add-to-checkout button.",
        "invoking": "Opening the Peek-A-Box shelf",
        "invoked": "Here are the boxes",
        "html": _doc("Peek-A-Box catalog", _CATALOG_JS),
    },
    "checkout": {
        "title": "Peek-A-Box checkout",
        "description": "A checkout review card showing line items, totals, and buttons to complete the purchase or continue in the browser.",
        "invoking": "Preparing your checkout",
        "invoked": "Your checkout is ready",
        "html": _doc("Peek-A-Box checkout", _CHECKOUT_JS),
    },
    "confirmation": {
        "title": "Peek-A-Box order",
        "description": "An order confirmation receipt with the order id, total charged, and a link to view the order.",
        "invoking": "Placing your order",
        "invoked": "Order confirmed",
        "html": _doc("Peek-A-Box order", _CONFIRM_JS),
    },
}


def _skybridge_uri(key: str) -> str:
    return f"ui://widget/{key}.html"


def _mcp_app_uri(key: str) -> str:
    return f"ui://widget/{key}.mcp-app.html"


def widget_meta(key: str) -> dict:
    """Build the tool-descriptor `_meta` that advertises this widget to both
    ChatGPT (openai/*) and MCP Apps hosts (ui.*)."""
    w = WIDGETS[key]
    return {
        "openai/outputTemplate": _skybridge_uri(key),
        "openai/toolInvocation/invoking": w["invoking"],
        "openai/toolInvocation/invoked": w["invoked"],
        "openai/widgetAccessible": True,
        "openai/widgetDescription": w["description"],
        "ui": {
            "resourceUri": _mcp_app_uri(key),
            "prefersBorder": True,
        },
    }


def register_widgets(mcp) -> None:
    """Register every widget as two resources: `text/html+skybridge` (ChatGPT)
    and `text/html;profile=mcp-app` (MCP Apps / Claude), serving identical HTML."""
    def _make(html):
        def _res():
            return html
        return _res

    for key, w in WIDGETS.items():
        html = w["html"]
        meta = widget_meta(key)
        mcp.resource(
            _skybridge_uri(key),
            name=w["title"],
            description=w["description"],
            mime_type="text/html+skybridge",
            meta=meta,
        )(_make(html))
        mcp.resource(
            _mcp_app_uri(key),
            name=w["title"] + " (MCP Apps)",
            description=w["description"],
            mime_type="text/html;profile=mcp-app",
            meta=meta,
        )(_make(html))
