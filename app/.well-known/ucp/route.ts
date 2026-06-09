// UCP discovery endpoint — advertises supported capabilities and MCP transport.
// MCP requests are proxied from /mcp to the Python FastMCP app in /mcp_server.
// Set MCP_SERVER_URL in .env.local to the internal MCP server address.
// Spec: https://ucp.dev/specification/checkout-mcp/#discovery
const UCP_VERSION = "2026-04-08"

export async function GET(request: Request): Promise<Response> {
  const host = request.headers.get("host") ?? "localhost:3000"
  const proto = request.headers.get("x-forwarded-proto") ?? "http"
  const base = `${proto}://${host}`

  const profile = {
    ucp: {
      version: UCP_VERSION,
      services: {
        "dev.ucp.shopping": [
          {
            version: UCP_VERSION,
            spec: `https://ucp.dev/${UCP_VERSION}/specification/overview`,
            transport: "mcp",
            schema: `https://ucp.dev/${UCP_VERSION}/services/shopping/mcp.openrpc.json`,
            endpoint: `${base}/mcp`,
          },
        ],
      },
      capabilities: {
        "dev.ucp.shopping.checkout": [
          {
            version: UCP_VERSION,
            spec: `https://ucp.dev/${UCP_VERSION}/specification/checkout`,
            schema: `https://ucp.dev/${UCP_VERSION}/schemas/shopping/checkout.json`,
          },
        ],
        "dev.ucp.shopping.catalog": [
          {
            version: UCP_VERSION,
            spec: `https://ucp.dev/${UCP_VERSION}/specification/catalog`,
            schema: `https://ucp.dev/${UCP_VERSION}/schemas/shopping/catalog.json`,
          },
        ],
        // Identity Linking — OAuth 2.0 Authorization Code + PKCE flow for agents
        // to act on behalf of a user. When linked, the agent's token carries user
        // claims so buyer info is pre-filled automatically.
        // OAuth endpoints are discovered via /.well-known/oauth-authorization-server
        // (RFC 8414) — NOT listed here per spec.
        // Spec: https://ucp.dev/specification/identity-linking/
        "dev.ucp.common.identity_linking": [
          {
            version: UCP_VERSION,
            config: {
              scopes: {
                openid:           {},
                profile:          { description: { plain: "Pre-fill buyer name from the user's profile" } },
                email:            { description: { plain: "Pre-fill buyer email address" } },
                "catalog:read":   { description: { plain: "Browse and search the product catalog" } },
                "cart:write":     { description: { plain: "Create, update, and cancel checkout sessions" } },
                "checkout:write": { description: { plain: "Complete a checkout session and place an order" } },
              },
            },
          },
        ],
      },
      business: {
        name: "Peek-A-Box",
        description: "Mystery box retail store",
        links: [
          { type: "privacy_policy", url: `${base}/privacy` },
          { type: "terms_of_service", url: `${base}/terms` },
        ],
      },
    },
  }

  return Response.json(profile, {
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  })
}
