// Fetches a UCP checkout session from the Python MCP server and returns
// line items in CartItem format for the cart page to hydrate from.
import type { CartItem } from "@/components/cart-provider"
import { products } from "@/lib/products"

const MCP_SERVER_URL = process.env.MCP_SERVER_URL ?? "http://localhost:8000"

type CheckoutPayload = {
  id?: string
  status?: string
  line_items?: { item: { id: string; title?: string; price?: number }; quantity: number }[]
  messages?: { type: string; severity?: string; code?: string; content?: string }[]
  buyer?: { name?: string; email?: string; first_name?: string; last_name?: string } | null
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const { id } = await params

  let mcpRes: Response
  try {
    mcpRes = await fetch(`${MCP_SERVER_URL}/checkout-sessions/${encodeURIComponent(id)}`)
  } catch {
    return Response.json({ error: "Could not reach MCP server" }, { status: 502 })
  }

  if (!mcpRes.ok) {
    const err = await mcpRes.json().catch(() => null) as {
      messages?: { content?: string }[]
    } | null
    const message =
      err?.messages?.[0]?.content ??
      (mcpRes.status === 404 ? "Session not found or expired" : "MCP server error")
    return Response.json({ error: message }, { status: mcpRes.status === 404 ? 404 : 502 })
  }

  const checkout = await mcpRes.json() as CheckoutPayload

  if (!checkout.line_items?.length) {
    return Response.json({ error: "Session not found or empty" }, { status: 404 })
  }

  const fatal = checkout.messages?.some(
    (m) => m.type === "error" && m.severity === "unrecoverable"
  )
  if (fatal) {
    return Response.json({ error: "Checkout session has errors" }, { status: 400 })
  }

  const cartItems: CartItem[] = checkout.line_items.map((li) => {
    const local = products.find((p) => p.id === li.item.id)
    return {
      id: li.item.id,
      name: local?.name ?? li.item.title ?? li.item.id,
      price: local?.price ?? (li.item.price ?? 0) / 100,
      image: local?.image ?? "/placeholder.svg?height=400&width=400",
      quantity: li.quantity,
    }
  })

  return Response.json({
    sessionId: checkout.id,
    status: checkout.status,
    cartItems,
    buyer: checkout.buyer ?? null,
  })
}
