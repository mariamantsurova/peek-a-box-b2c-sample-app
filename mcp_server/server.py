"""
Peek-A-Box UCP MCP Server
Implements the Universal Commerce Protocol (UCP) checkout + catalog capabilities
via FastMCP with Descope authentication.

Spec: https://ucp.dev/specification/checkout-mcp/
"""

import base64
import json as _json
import os
import time
import uuid
from typing import Optional

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth.providers.descope import DescopeProvider
from fastmcp.server.dependencies import get_access_token
from starlette.requests import Request
from starlette.responses import JSONResponse

load_dotenv()

UCP_VERSION = "2026-04-08"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))

# ── Descope management client (for embedded link generation) ──────────────────
# Only initialized when DESCOPE_MANAGEMENT_KEY is set. If absent, continue_url
# is returned without an embedded token and users sign in normally.
_descope_mgmt = None
try:
    _mgmt_key = os.environ.get("DESCOPE_MANAGEMENT_KEY", "")
    _proj_id  = os.environ.get("DESCOPE_PROJECT_ID", "")
    if _mgmt_key and _proj_id:
        from descope import DescopeClient as _DescopeClient
        _descope_mgmt = _DescopeClient(project_id=_proj_id, management_key=_mgmt_key)
except Exception:
    pass

# ── Auth ──────────────────────────────────────────────────────────────────────

auth = DescopeProvider(
    config_url=os.environ["DESCOPE_CONFIG_URL"],
    base_url=os.environ.get("MCP_BASE_URL", f"http://localhost:{MCP_PORT}"),
)

mcp = FastMCP(
    name="peek-a-box-ucp",
    instructions=(
        "You are connected to the Peek-A-Box mystery box store. "
        "Use the catalog tools to search products and the checkout tools "
        "to create and manage checkout sessions on behalf of users."
    ),
    auth=auth,
)

# ── Product catalog (mirrors lib/products.ts) ─────────────────────────────────

PRODUCTS = [
    {"id": "box-14291", "name": "Box #14291", "description": "Mildly Concerning",             "price": 9.99,  "category": "bestsellers", "badge": "Bestseller"},
    {"id": "box-50003", "name": "Box #50003", "description": "Definitely Haunted",            "price": 13.99, "category": "new",         "badge": None},
    {"id": "box-7",     "name": "Box #7",     "description": "Suspiciously Light",            "price": 7.77,  "category": "bestsellers", "badge": None},
    {"id": "box-666",   "name": "Box #666",   "description": "Legally We Cannot Discuss This","price": 6.66,  "category": "new",         "badge": None},
    {"id": "box-42",    "name": "Box #42",    "description": "The Answer To Everything",      "price": 42.00, "category": "premium",     "badge": None},
    {"id": "box-99999", "name": "Box #99999", "description": "Too Many Nines",                "price": 9.99,  "category": "bestsellers", "badge": None},
    {"id": "box-67",    "name": "Box #67",    "description": "This Makes Our CEO Laugh",      "price": 67.00, "category": "premium",     "badge": "CEO Pick"},
    {"id": "box-0",     "name": "Box #0",     "description": "The First One. Or Is It?",      "price": 0.01,  "category": "new",         "badge": None},
    {"id": "box-pi",    "name": "Box #π",     "description": "Irrational Value",              "price": 3.14,  "category": "premium",     "badge": None},
]

def _to_ucp_item(p: dict) -> dict:
    item = {
        "id": p["id"],
        "title": p["name"],
        "description": p["description"],
        "price": round(p["price"] * 100),  # cents
        "currency": "USD",
        "images": [{"url": f"{BASE_URL}/placeholder.svg?height=400&width=400", "alt": p["name"]}],
        "category": p["category"],
        "available": True,
    }
    if p.get("badge"):
        item["badge"] = p["badge"]
    return item

# ── Auth helpers ─────────────────────────────────────────────────────────────

def _decode_jwt_claims(token: str) -> dict:
    """Decode claims from a JWT payload without signature verification.

    The token has already been cryptographically verified by DescopeProvider
    before any tool is invoked. We only read claims here.
    """
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        return _json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


def _get_token_scopes() -> set[str]:
    """Return the set of scopes granted in the current access token."""
    try:
        access_token = get_access_token()
        if access_token and access_token.token:
            claims = _decode_jwt_claims(access_token.token)
            scope_str = claims.get("scope", "") or ""
            return set(scope_str.split())
    except Exception:
        pass
    return set()


def _require_scope(scope: str) -> None:
    """Raise AuthorizationError (→ HTTP 403) if the required scope is not present."""
    if scope not in _get_token_scopes():
        raise AuthorizationError(f"The '{scope}' scope is required for this action.")


# ── In-memory checkout store ──────────────────────────────────────────────────

_checkouts: dict[str, dict] = {}

def _compute_totals(line_items: list[dict], has_shipping: bool) -> list[dict]:
    subtotal = 0
    for li in line_items:
        product = next((p for p in PRODUCTS if p["id"] == li["item"]["id"]), None)
        unit_price = round(product["price"] * 100) if product else li["item"].get("price", 0)
        subtotal += unit_price * li["quantity"]
    shipping = 599 if has_shipping else 0
    totals = [{"type": "subtotal", "amount": subtotal}]
    if shipping:
        totals.append({"type": "fulfillment", "display_text": "Standard Shipping", "amount": shipping})
    totals.append({"type": "total", "amount": subtotal + shipping})
    return totals

def _enrich_line_items(line_items: list[dict]) -> tuple[list[dict], list[dict]]:
    enriched, messages = [], []
    for li in line_items:
        product = next((p for p in PRODUCTS if p["id"] == li["item"]["id"]), None)
        if not product:
            messages.append({
                "type": "error", "code": "item_unavailable",
                "content": f"Item {li['item']['id']} is not available",
                "severity": "unrecoverable",
            })
            enriched.append(li)
        else:
            enriched.append({**li, "item": {"id": product["id"], "title": product["name"], "price": round(product["price"] * 100)}})
    return enriched, messages

def _ucp_envelope() -> dict:
    return {
        "version": UCP_VERSION,
        "capabilities": {
            "dev.ucp.shopping.checkout": [{"version": UCP_VERSION}],
            "dev.ucp.shopping.catalog":  [{"version": UCP_VERSION}],
            # Identity Linking — OAuth endpoints are discovered by the platform via
            # /.well-known/oauth-authorization-server (RFC 8414). Only scopes are
            # declared here; OAuth URLs do NOT belong in this config block.
            "dev.ucp.common.identity_linking": [{
                "version": UCP_VERSION,
                "config": {
                    "scopes": {
                        "openid":        {},
                        "profile":       {"description": {"plain": "Pre-fill buyer name from the user's profile"}},
                        "email":         {"description": {"plain": "Pre-fill buyer email address"}},
                        "catalog:read":   {"description": {"plain": "Browse and search the product catalog"}},
                        "cart:write":     {"description": {"plain": "Create, update, and cancel checkout sessions"}},
                        "checkout:write": {"description": {"plain": "Complete a checkout session and place an order"}},
                    },
                },
            }],
        },
    }

# ── Catalog tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def lookup_catalog(
    query: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """
    Search for products in the Peek-A-Box catalog.
    Returns a list of matching items with IDs, prices (in cents), and descriptions.

    Args:
        query: Optional free-text search string matched against name and description.
        category: Filter by category — one of 'bestsellers', 'new', or 'premium'.
        limit: Maximum number of results to return (default 20).
    """
    results = PRODUCTS
    if category:
        results = [p for p in results if p["category"] == category]
    if query:
        q = query.lower()
        results = [p for p in results if q in p["name"].lower() or q in p["description"].lower()]
    results = results[:limit]
    items = [_to_ucp_item(p) for p in results]
    return {"ucp": _ucp_envelope(), "items": items, "total": len(items)}


@mcp.tool()
def get_product(id: str) -> dict:
    """
    Look up a specific product by its ID.

    Args:
        id: The product ID (e.g. 'box-42').
    """
    product = next((p for p in PRODUCTS if p["id"] == id), None)
    if not product:
        return {
            "ucp": {"version": UCP_VERSION, "status": "error"},
            "messages": [{"type": "error", "code": "item_unavailable",
                          "content": f"Product '{id}' not found", "severity": "unrecoverable"}],
        }
    return {"ucp": _ucp_envelope(), "item": _to_ucp_item(product)}


# ── Checkout tools ────────────────────────────────────────────────────────────

@mcp.tool()
def create_checkout(
    line_items: list[dict],
    currency: str = "USD",
    buyer: Optional[dict] = None,
    fulfillment: Optional[dict] = None,
) -> dict:
    """
    Create a new UCP checkout session.

    Args:
        line_items: List of items to purchase. Each must have:
            - id (str): line item ID (e.g. 'li_1')
            - item.id (str): product ID (e.g. 'box-42')
            - quantity (int): number of units
        currency: ISO 4217 currency code (default 'USD').
        buyer: Optional buyer info with email, first_name, last_name.
        fulfillment: Optional fulfillment with shipping destinations.
    """
    _require_scope("checkout:write")
    if not line_items:
        return {
            "ucp": {"version": UCP_VERSION, "status": "error"},
            "messages": [{"type": "error", "code": "invalid_request",
                          "content": "line_items must not be empty", "severity": "unrecoverable"}],
        }

    enriched, messages = _enrich_line_items(line_items)
    fatal = [m for m in messages if m.get("severity") == "unrecoverable"]
    if len(fatal) == len(line_items):
        return {"ucp": {"version": UCP_VERSION, "status": "error"}, "messages": messages, "continue_url": BASE_URL}

    has_shipping = bool(
        fulfillment and any(
            m.get("type") == "shipping" and m.get("destinations")
            for m in fulfillment.get("methods", [])
        )
    )
    totals = _compute_totals(enriched, has_shipping)

    # If the agent completed the Identity Linking OAuth flow, the token will
    # carry user claims (email, name). Use them to pre-fill buyer info and skip
    # the identity_optional hint — identity is already linked.
    user_claims: dict = {}
    try:
        access_token = get_access_token()
        if access_token and access_token.token:
            user_claims = _decode_jwt_claims(access_token.token)
    except Exception:
        pass

    user_sub: Optional[str] = user_claims.get("sub") or None
    user_email: Optional[str] = user_claims.get("email") or None
    user_name: Optional[str] = (
        user_claims.get("name") or user_claims.get("given_name") or None
    )

    # Auto-populate buyer from Identity Linking claims when not already provided
    if not buyer and (user_email or user_name):
        buyer = {}
        if user_email:
            buyer["email"] = user_email
        if user_name:
            buyer["name"] = user_name

    checkout_id = f"checkout_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

    # If we know the user's identity (from Identity Linking), generate a
    # one-time embedded link token so the continue_url auto-logs them in —
    # regardless of which device or browser they use to follow the link.
    #
    # Descope access tokens don't include 'email' by default, so when it's
    # absent we resolve the user's login ID (email) from their sub via the
    # management API before calling generate_embedded_link.
    continue_url = f"{BASE_URL}/cart?session={checkout_id}"
    if _descope_mgmt and user_sub:
        login_id = user_email  # use JWT email if present
        if not login_id:
            try:
                user_resp = _descope_mgmt.mgmt.user.load_by_user_id(user_sub)
                login_ids = user_resp.get("user", {}).get("loginIds", [])
                login_id = login_ids[0] if login_ids else None
            except Exception:
                pass
        if login_id:
            try:
                embedded_token = _descope_mgmt.mgmt.user.generate_embedded_link(login_id)
                if embedded_token:
                    continue_url += f"&t={embedded_token}"
            except Exception:
                pass

    checkout = {
        "id": checkout_id,
        "status": "incomplete",
        "buyer": buyer,
        "line_items": enriched,
        "currency": currency,
        "totals": totals,
        "fulfillment": fulfillment,
        "links": [
            {"type": "privacy_policy",  "url": f"{BASE_URL}/privacy"},
            {"type": "terms_of_service","url": f"{BASE_URL}/terms"},
        ],
        "continue_url": continue_url,
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 1800)),
    }
    # Suggest Identity Linking only when the agent hasn't done it yet.
    # Use sub as the signal — it's present in any user-authenticated token.
    if not user_sub:
        messages.append({
            "type": "info",
            "code": "identity_optional",
            "content": (
                "Link user identity to pre-fill saved addresses, apply member pricing, "
                "and access order history."
            ),
        })
    if messages:
        checkout["messages"] = messages
    _checkouts[checkout_id] = checkout
    return {"ucp": _ucp_envelope(), **checkout}


def _get_checkout_response(id: str) -> dict:
    checkout = _checkouts.get(id)
    if not checkout:
        return {
            "ucp": {"version": UCP_VERSION, "status": "error"},
            "messages": [{"type": "error", "code": "not_found",
                          "content": f"Checkout '{id}' not found", "severity": "unrecoverable"}],
        }
    public = {k: v for k, v in checkout.items() if not k.startswith("_")}
    return {"ucp": _ucp_envelope(), **public}


@mcp.tool()
def get_checkout(id: str) -> dict:
    """
    Retrieve an existing checkout session by ID.

    Args:
        id: The checkout session ID returned by create_checkout.
    """
    _require_scope("cart:write")
    return _get_checkout_response(id)


@mcp.custom_route("/checkout-sessions/{id}", methods=["GET"])
async def get_checkout_session(request: Request) -> JSONResponse:
    """Public REST endpoint for the Next.js cart to hydrate agent checkout links."""
    checkout_id = request.path_params["id"]
    checkout = _checkouts.get(checkout_id)
    if not checkout:
        return JSONResponse(
            {"messages": [{"type": "error", "code": "not_found",
                           "content": f"Checkout '{checkout_id}' not found",
                           "severity": "unrecoverable"}]},
            status_code=404,
        )
    return JSONResponse({"ucp": _ucp_envelope(), **checkout})


@mcp.tool()
def update_checkout(
    id: str,
    line_items: Optional[list[dict]] = None,
    buyer: Optional[dict] = None,
    fulfillment: Optional[dict] = None,
    currency: Optional[str] = None,
) -> dict:
    """
    Update an existing checkout session.

    Args:
        id: The checkout session ID to update.
        line_items: Replacement line items (optional).
        buyer: Updated buyer info (optional).
        fulfillment: Updated fulfillment / shipping details (optional).
        currency: Updated currency code (optional).
    """
    _require_scope("cart:write")
    checkout = _checkouts.get(id)
    if not checkout:
        return {
            "ucp": {"version": UCP_VERSION, "status": "error"},
            "messages": [{"type": "error", "code": "not_found",
                          "content": f"Checkout '{id}' not found", "severity": "unrecoverable"}],
        }

    items = line_items or checkout["line_items"]
    enriched, _ = _enrich_line_items(items)
    merged_fulfillment = fulfillment if fulfillment is not None else checkout.get("fulfillment")
    has_shipping = bool(
        merged_fulfillment and any(
            m.get("type") == "shipping" and m.get("destinations")
            for m in merged_fulfillment.get("methods", [])
        )
    )
    totals = _compute_totals(enriched, has_shipping)

    checkout.update({
        "line_items": enriched,
        "totals": totals,
        "buyer": buyer if buyer is not None else checkout.get("buyer"),
        "fulfillment": merged_fulfillment,
        "currency": currency or checkout["currency"],
    })
    return {"ucp": _ucp_envelope(), **checkout}


@mcp.tool()
def complete_checkout(
    id: str,
    idempotency_key: str,
    payment: Optional[dict] = None,
) -> dict:
    """
    Finalize a checkout session and place the order.

    Args:
        id: The checkout session ID to complete.
        idempotency_key: A UUID for retry safety (required by UCP spec).
        payment: Payment credentials / token (optional for sample app).
    """
    _require_scope("checkout:write")
    checkout = _checkouts.get(id)
    if not checkout:
        return {
            "ucp": {"version": UCP_VERSION, "status": "error"},
            "messages": [{"type": "error", "code": "not_found",
                          "content": f"Checkout '{id}' not found", "severity": "unrecoverable"}],
        }
    if checkout["status"] == "canceled":
        return {
            "ucp": {"version": UCP_VERSION, "status": "error"},
            "messages": [{"type": "error", "code": "checkout_canceled",
                          "content": "Checkout has been canceled", "severity": "unrecoverable"}],
        }

    # Carts with more than one item require the user to review and confirm
    # in the storefront before completing. Return the cart link instead.
    total_quantity = sum(li.get("quantity", 1) for li in checkout.get("line_items", []))
    if total_quantity > 1:
        return {
            "ucp": _ucp_envelope(),
            "status": "requires_action",
            "messages": [{
                "type": "info",
                "code": "review_required",
                "content": (
                    "This cart has more than one item and must be reviewed by the user "
                    "before it can be completed. Share the cart link with the user."
                ),
            }],
            "continue_url": checkout["continue_url"],
        }

    # Extract user identity from the token (if Identity Linking was done).
    # Use it to fill any missing buyer fields and generate an embedded link
    # so the permalink_url auto-logs the user in on any device.
    user_claims: dict = {}
    try:
        access_token = get_access_token()
        if access_token and access_token.token:
            user_claims = _decode_jwt_claims(access_token.token)
    except Exception:
        pass

    user_sub: Optional[str] = user_claims.get("sub") or None
    user_email: Optional[str] = user_claims.get("email") or None
    user_name: Optional[str] = (
        user_claims.get("name") or user_claims.get("given_name") or None
    )

    # Back-fill buyer if not already set on the checkout
    existing_buyer = checkout.get("buyer") or {}
    if user_email and not existing_buyer.get("email"):
        existing_buyer["email"] = user_email
    if user_name and not existing_buyer.get("name"):
        existing_buyer["name"] = user_name
    if existing_buyer:
        checkout["buyer"] = existing_buyer

    # Generate embedded link for the confirmation URL
    confirm_url = f"{BASE_URL}/cart/confirm?session={checkout['id']}"
    if _descope_mgmt and user_sub:
        login_id = user_email
        if not login_id:
            try:
                user_resp = _descope_mgmt.mgmt.user.load_by_user_id(user_sub)
                login_ids = user_resp.get("user", {}).get("loginIds", [])
                login_id = login_ids[0] if login_ids else None
            except Exception:
                pass
        if login_id:
            try:
                embedded_token = _descope_mgmt.mgmt.user.generate_embedded_link(login_id)
                if embedded_token:
                    confirm_url += f"&t={embedded_token}"
            except Exception:
                pass

    order_id = f"order_{int(time.time() * 1000)}"
    checkout.update({
        "status": "completed",
        "payment": payment,
        "order": {"id": order_id, "permalink_url": confirm_url},
    })
    return {"ucp": _ucp_envelope(), **checkout}


@mcp.tool()
def cancel_checkout(id: str, idempotency_key: str) -> dict:
    """
    Cancel an existing checkout session.

    Args:
        id: The checkout session ID to cancel.
        idempotency_key: A UUID for retry safety (required by UCP spec).
    """
    _require_scope("cart:write")
    checkout = _checkouts.get(id)
    if not checkout:
        return {
            "ucp": {"version": UCP_VERSION, "status": "error"},
            "messages": [{"type": "error", "code": "not_found",
                          "content": f"Checkout '{id}' not found", "severity": "unrecoverable"}],
        }
    checkout["status"] = "canceled"
    return {"ucp": _ucp_envelope(), **checkout}


# ── Entry point ───────────────────────────────────────────────────────────────

# Make transport-level auth optional so unauthenticated clients can connect and
# call catalog tools. The BearerAuthBackend middleware still runs and populates
# the token context when a Bearer token is present, so per-tool _require_scope()
# checks on cart/checkout tools work correctly for authenticated requests.
import fastmcp.server.http as _fmcp_http


class _OptionalBearerMiddleware:
    """Passthrough replacement for RequireAuthMiddleware.

    Allows unauthenticated MCP connections. Tools that require auth enforce it
    themselves via _require_scope(), which raises AuthorizationError (HTTP 403)
    when the token is missing or lacks the required scope.
    """

    def __init__(self, app, required_scopes=None, resource_metadata_url=None):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


_fmcp_http.RequireAuthMiddleware = _OptionalBearerMiddleware

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=MCP_PORT)
