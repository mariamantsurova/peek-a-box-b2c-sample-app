// Public proxy to the Python FastMCP server (mcp_server/server.py).
// Advertised in /.well-known/ucp as the MCP transport endpoint.
const MCP_SERVER_URL = process.env.MCP_SERVER_URL ?? "http://localhost:8000"

const HOP_BY_HOP = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
])

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
  "Access-Control-Allow-Headers":
    "Content-Type, Authorization, Mcp-Session-Id, Mcp-Protocol-Version",
}

async function proxyToMcp(request: Request): Promise<Response> {
  const headers = new Headers()
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      headers.set(key, value)
    }
  })

  // Buffer the request body instead of streaming it, so the upstream's 401 returns cleanly.
  const hasBody = request.method !== "GET" && request.method !== "HEAD"
  const body = hasBody ? await request.arrayBuffer() : undefined

  let upstream: Response
  try {
    upstream = await fetch(`${MCP_SERVER_URL}/mcp`, {
      method: request.method,
      headers,
      body,
    })
  } catch (err) {
    console.error("MCP proxy: could not reach MCP server:", err)
    return Response.json(
      { error: "Could not reach MCP server" },
      { status: 502, headers: CORS_HEADERS }
    )
  }

  const responseHeaders = new Headers(upstream.headers)
  for (const [key, value] of Object.entries(CORS_HEADERS)) {
    responseHeaders.set(key, value)
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

export async function GET(request: Request): Promise<Response> {
  return proxyToMcp(request)
}

export async function POST(request: Request): Promise<Response> {
  return proxyToMcp(request)
}

export async function DELETE(request: Request): Promise<Response> {
  return proxyToMcp(request)
}

export async function OPTIONS(): Promise<Response> {
  return new Response(null, { status: 204, headers: CORS_HEADERS })
}
