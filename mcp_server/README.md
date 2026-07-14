# Peek-A-Box UCP MCP server

A [FastMCP](https://github.com/jlowin/fastmcp) server implementing the
[Universal Commerce Protocol](https://ucp.dev/specification/checkout-mcp/) (catalog +
checkout + orders) with Descope authentication, plus **MCP UI components** that render
an interactive buying experience in hosts that support them (ChatGPT and Claude).

## Tools

| Tool | Capability | Scope | Widget |
| --- | --- | --- | --- |
| `lookup_catalog` | catalog | public | Catalog grid |
| `get_product` | catalog | public | — |
| `create_checkout` | checkout | `checkout:manage` | Checkout review |
| `get_checkout` | checkout | `checkout:manage` | Checkout review |
| `update_checkout` | checkout | `checkout:manage` | Checkout review |
| `complete_checkout` | checkout | `checkout:manage` | Order confirmation |
| `cancel_checkout` | checkout | `checkout:manage` | — |
| `get_orders` | order | `order:read` | — |

## MCP UI components

The catalog, checkout, and order-confirmation widgets are self-contained inline HTML
served from `ui://` resources (see [`widgets.py`](widgets.py)). One implementation
serves **both** ecosystems:

- **ChatGPT (OpenAI Apps SDK)** — tools carry `_meta["openai/outputTemplate"]`; the
  widget is served as `text/html+skybridge` and reads data via `window.openai.toolOutput`.
- **Claude / MCP Apps (SEP-1865)** — tools carry `_meta.ui.resourceUri`; the widget is
  also served as `text/html;profile=mcp-app` and talks JSON-RPC over `postMessage`.

A small in-widget bridge (`window.PAB`) normalizes the two host APIs, so the same HTML
renders, themes (light/dark), and wires buttons on both platforms.

The widgets mirror the storefront's design (see `components/product-card.tsx` and
`app/styles/globals.css`): the box-logo + `#number` tile, dark foreground-pill badges,
italic descriptions, `tabular-nums` prices, and the cart's order-summary rows. Because
the sandboxed iframe can't reach the app's font pipeline, Geist is embedded (subsetted)
in `_fonts.py` — regenerate it with `python scripts/subset_fonts.py` after `npm install`.

## Run locally

```bash
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in DESCOPE_CONFIG_URL (see below)
python server.py              # serves MCP on http://localhost:8000/mcp
```

`DESCOPE_CONFIG_URL` comes from **Descope Console → MCP Servers → your server →
Well-Known URL**. `STRIPE_SECRET_KEY` and `DATABASE_URL` are optional — without them the
server simulates charges and stores state in memory.

The Next.js app proxies `/mcp` → this server (`MCP_SERVER_URL`, default
`http://localhost:8000`), so agents connect to the storefront's public `/mcp` endpoint.

## Verify

Protocol + widget rendering are covered without a live Descope project:

```bash
cd mcp_server && source .venv/bin/activate
python test_server.py   # 41 checks: tool _meta, ui:// resources, storefront parity, buying flow
```

The widgets can be viewed in any browser by injecting a mock `window.openai` with sample
`toolOutput` (see the render-test harness). Both light and dark themes and all button
callbacks (`sendFollowUpMessage`, `openExternal`) are exercised.

### Live in-client test

A true end-to-end render requires a live Descope project connected to a host:

1. Run this server with a real `DESCOPE_CONFIG_URL` and expose it publicly (e.g. the
   Next.js proxy at `https://<your-domain>/mcp`).
2. **ChatGPT** — Settings → Connectors → add your `/mcp` URL, complete the OAuth
   (identity-linking) flow, then ask *"show me the Peek-A-Box catalog"*.
3. **Claude** — add the MCP server (Settings → Connectors / `claude mcp add`), authorize,
   then ask the same. Widgets render inline; buying actions call back through the host.

> Note: MCP Apps rendering in Claude is still maturing
> ([ext-apps#671](https://github.com/modelcontextprotocol/ext-apps/issues/671)). The
> MCP Inspector and the `@modelcontextprotocol/ext-apps` `basic-host` are reliable
> ground-truth harnesses if a widget doesn't render in a given client build.
