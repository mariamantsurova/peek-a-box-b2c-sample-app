"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useEffect, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { X, ArrowLeft, Bot } from "lucide-react"
import { useSession, useDescope } from "@descope/nextjs-sdk/client"
import { useCart, type CartItem } from "@/components/cart-provider"
import { AppNav } from "@/components/app-nav"
import { Button } from "@/components/ui/button"

export default function CartPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { items, addToCart, removeFromCart, clearCart, totalPrice } = useCart()
  const { isAuthenticated, isSessionLoading } = useSession()
  const sdk = useDescope()
  const [agentSession, setAgentSession] = useState<string | null>(null)
  const [sessionLoading, setSessionLoading] = useState(false)
  const [sessionError, setSessionError] = useState<string | null>(null)
  // True while we're verifying an embedded link token — prevents the
  // "Sign in to checkout" button from flashing before auth resolves.
  const [magicLinkVerifying, setMagicLinkVerifying] = useState(
    () => typeof window !== "undefined" && new URLSearchParams(window.location.search).has("t")
  )

  // Verify an embedded link token from the continue_url (?t=...).
  // The MCP server embeds this when Identity Linking is complete so the user
  // is auto-logged in regardless of which device or browser they use.
  useEffect(() => {
    const token = searchParams.get("t")
    if (!token) return

    // Remove the token from the URL immediately — it's one-time use.
    const params = new URLSearchParams(searchParams.toString())
    params.delete("t")
    const qs = params.size > 0 ? `?${params.toString()}` : ""
    router.replace(`/cart${qs}`, { scroll: false })

    sdk.magicLink.verify(token).finally(() => setMagicLinkVerifying(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Hydrate cart from a UCP checkout session created by an agent
  useEffect(() => {
    const sessionId = searchParams.get("session")
    if (!sessionId) return

    setSessionLoading(true)
    setSessionError(null)

    fetch(`/api/ucp/session/${encodeURIComponent(sessionId)}`)
      .then(async (res) => {
        const data = await res.json().catch(() => null) as {
          error?: string
          cartItems?: Omit<CartItem, "quantity">[]
        } | null
        if (!res.ok || data?.error) {
          setSessionError(data?.error ?? "Failed to load agent session")
          return
        }
        if (!data?.cartItems?.length) {
          setSessionError("Session not found or empty")
          return
        }
        clearCart()
        for (const item of data.cartItems) {
          addToCart(item)
        }
        setAgentSession(sessionId)
      })
      .catch(() => setSessionError("Failed to load agent session"))
      .finally(() => setSessionLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleCheckout = () => {
    if (!isAuthenticated) {
      // Identity Linking OAuth gives the AGENT a token for user-authenticated
      // MCP calls — the code/token flow terminates at the agent's redirect_uri,
      // not here. The business storefront session is completely independent.
      // Users always need to sign in to this site to place an order, regardless
      // of whether the agent did Identity Linking, and regardless of which
      // device or browser they use to follow the continue_url.
      const returnTo = agentSession
        ? `/cart?session=${encodeURIComponent(agentSession)}`
        : "/cart"
      router.push(`/login?returnTo=${encodeURIComponent(returnTo)}`)
      return
    }
    if (items.length >= 2) {
      router.push("/cart/step-up")
    } else {
      router.push("/cart/confirm")
    }
  }

  const isEmpty = items.length === 0

  const navItems = [{ name: "Shop", link: "/" }]

  const boxNumber = (name: string, id: string) => {
    const match = name.match(/#(\S+)/)
    return match ? match[1] : id.replace(/^box-/, "")
  }

  return (
    <div className="min-h-screen bg-background">
      <AppNav navItems={navItems} />

      <main className="mx-auto max-w-5xl px-6 pb-24 pt-28">
        <Link href="/" className="inline-flex items-center gap-2 text-base text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft className="h-4 w-4 shrink-0" />
          Back to store
        </Link>

        <h1 className="mt-8 text-4xl font-semibold tracking-tight sm:text-5xl">Your cart</h1>

        {/* Agent session banner */}
        {sessionLoading && (
          <div className="mt-6 flex items-center gap-3 rounded-xl border border-border bg-muted/50 px-5 py-4 text-base text-muted-foreground">
            <Bot className="h-5 w-5 shrink-0 animate-pulse" />
            Loading your agent-prepared cart…
          </div>
        )}
        {sessionError && (
          <div className="mt-6 rounded-xl border border-destructive/30 bg-destructive/5 px-5 py-4 text-base text-destructive">
            Could not load agent session: {sessionError}
          </div>
        )}
        {agentSession && !sessionLoading && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-6 flex items-start gap-3 rounded-xl border border-border bg-muted/50 px-5 py-4 text-base"
          >
            <Bot className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
            <p className="text-muted-foreground">
              Your cart was prepared by an AI agent.{" "}
              <span className="text-foreground">Review and confirm below.</span>
            </p>
          </motion.div>
        )}

        <AnimatePresence mode="wait">
          {isEmpty ? (
            <motion.div
              key="empty"
              className="mt-20 flex flex-col items-center py-16"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="flex h-20 w-20 items-center justify-center rounded-full bg-muted">
                <img
                  src="/Peek-A-Box_icon-light.svg"
                  alt=""
                  className="h-12 w-12 object-contain dark:hidden"
                  aria-hidden
                />
                <img
                  src="/Peek-A-Box_icon-dark.svg"
                  alt=""
                  className="hidden h-12 w-12 object-contain dark:block"
                  aria-hidden
                />
              </div>
              <p className="mt-6 text-2xl font-semibold text-foreground sm:text-3xl">Your cart is empty.</p>
              <p className="mt-3 text-xl text-muted-foreground sm:text-2xl">
                Add items from the store to get started.
              </p>
              <Button asChild size="lg" className="mt-8 rounded-full border-2 border-foreground/20 px-8 text-base sm:text-lg">
                <Link href="/">Continue shopping</Link>
              </Button>
            </motion.div>
          ) : (
            <motion.div
              key="cart"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-12 lg:grid lg:grid-cols-12 lg:gap-16"
            >
              <div className="lg:col-span-7">
                <div className="divide-y divide-border">
                  {items.map((item, index) => (
                    <motion.div
                      key={item.id}
                      className="flex gap-5 py-6"
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.1 }}
                    >
                      <div className="relative flex h-28 w-28 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-muted">
                        <div className="relative flex h-[68%] w-[68%] max-h-20 max-w-20 items-center justify-center">
                          <img
                            src="/Peek-A-Box_icon-light.svg"
                            alt=""
                            className="absolute inset-0 h-full w-full object-contain dark:hidden"
                            aria-hidden
                          />
                          <img
                            src="/Peek-A-Box_icon-dark.svg"
                            alt=""
                            className="absolute inset-0 hidden h-full w-full object-contain dark:block"
                            aria-hidden
                          />
                          <span className="absolute bottom-[12%] left-1/2 z-10 -translate-x-1/2 text-sm font-bold tabular-nums text-foreground drop-shadow-sm">
                            #{boxNumber(item.name, item.id)}
                          </span>
                        </div>
                      </div>
                      <div className="flex flex-1 flex-col justify-between">
                        <div className="flex justify-between">
                          <div>
                            <h3 className="text-base font-medium sm:text-lg">{item.name}</h3>
                            <p className="mt-1 text-base text-muted-foreground">
                              ${item.price.toFixed(2)} each
                            </p>
                          </div>
                          <div className="flex items-center gap-4">
                            <p className="text-base font-medium tabular-nums sm:text-lg">
                              ${item.price.toFixed(2)}
                            </p>
                            <button
                              onClick={() => removeFromCart(item.id)}
                              className="flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                              aria-label="Remove item"
                            >
                              <X className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>

              <div className="mt-12 lg:col-span-5 lg:mt-0">
                <motion.div
                  className="rounded-2xl bg-muted/50 p-6"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 }}
                >
                  <h2 className="text-base font-medium sm:text-lg">Order summary</h2>
                  <dl className="mt-6 space-y-4 text-base">
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">Items</dt>
                      <dd className="tabular-nums">{items.length}</dd>
                    </div>
                    <div className="flex justify-between border-t border-border pt-4 text-base font-medium">
                      <dt>Total</dt>
                      <dd className="tabular-nums">${totalPrice.toFixed(2)}</dd>
                    </div>
                  </dl>
                  <button
                    onClick={handleCheckout}
                    disabled={isSessionLoading || magicLinkVerifying}
                    className="mt-6 w-full rounded-full bg-foreground py-3.5 text-base font-medium text-background transition-colors hover:bg-foreground/90 disabled:opacity-50 sm:text-lg"
                  >
                    {isSessionLoading || magicLinkVerifying
                      ? "Signing you in…"
                      : isAuthenticated
                        ? "Place order"
                        : "Sign in to checkout"}
                  </button>
                  {items.length >= 2 && isAuthenticated && !isSessionLoading && !magicLinkVerifying && (
                    <p className="mt-4 text-center text-base text-muted-foreground sm:text-lg">
                      Due to the high value of items in your cart, you'll be asked to re-verify your identity before your order is confirmed.
                    </p>
                  )}
                  {!isAuthenticated && !isSessionLoading && !magicLinkVerifying && (
                    <p className="mt-4 text-center text-base text-muted-foreground sm:text-lg">
                      Sign in to complete your purchase.
                    </p>
                  )}
                </motion.div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  )
}
