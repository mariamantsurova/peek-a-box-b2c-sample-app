// Proxies the MCP server's OAuth Protected Resource Metadata (RFC 9728) so auth
// discovery resolves under the public domain (peek-a-box.shop) instead of the
// internal MCP server host.
const MCP_SERVER_URL = process.env.MCP_SERVER_URL ?? "http://localhost:8000"

// Always proxy fresh; never statically evaluate at build time.
export const dynamic = "force-dynamic"

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
}

export async function GET(): Promise<Response> {
  let upstream: Response
  try {
    upstream = await fetch(
      `${MCP_SERVER_URL}/.well-known/oauth-protected-resource/mcp`,
      { headers: { Accept: "application/json" } }
    )
  } catch {
    return Response.json(
      { error: "Could not reach MCP server" },
      { status: 502, headers: CORS_HEADERS }
    )
  }

  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Cache-Control": upstream.headers.get("cache-control") ?? "public, max-age=3600",
      ...CORS_HEADERS,
    },
  })
}

export async function OPTIONS(): Promise<Response> {
  return new Response(null, { status: 204, headers: CORS_HEADERS })
}
