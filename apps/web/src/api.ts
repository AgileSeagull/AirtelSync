// Typed client for the Udyam Digital API.

export type Lang = "en" | "hi" | "mr" | "ta" | "te" | "kn" | "gu" | "bn" | "pa" | "ml";

export interface Turn { role: "user" | "assistant"; text: string; mode?: string | null }

export interface TierItem {
  product_id: string; name: string; category: string; qty: number; unit: string;
  reasons: string[]; why: string; optional: boolean;
}

export interface QuoteLine {
  product_id: string; name: string; qty: number; unit: string; contract_months: number;
  unit_price: number; monthly: number; setup: number; install_days: number;
}

export interface Violation { product_id: string; rule: string; message: string }

export interface Quote {
  lines: QuoteLine[]; contract: Contract; subtotal_monthly: number; bundle_discount_pct: number;
  bundle_discount: number; monthly_ex_gst: number; gst: number; monthly_total: number;
  setup_ex_gst: number; setup_waived: number; setup_total: number; earliest_activation_days: number;
  current_spend: number | null; monthly_difference: number | null; violations: Violation[]; notes: string[];
}

export interface Tier { tier: "essential" | "recommended" | "complete"; items: TierItem[]; quote: Quote }

export interface Recommendation {
  segment: string; tiers: Tier[]; notes: string[];
  excluded: Violation[]; profile: Record<string, unknown>;
}

export interface SessionView {
  session_id: string; lang: Lang; status: string; last_asked: string | null;
  profile: Record<string, any>; missing: string[]; recommendation: Recommendation | null;
  handoff: { reason: string } | null; transcript: Turn[]; llm_enabled: boolean;
  reply?: string; mode?: string;
}

export type Contract = "flexible" | "12" | "24";
export interface LineItem { product_id: string; qty: number }

export interface Fix { violation: Violation; action: "add" | "remove"; product_id: string; name: string; qty?: number }
export interface Addon {
  product_id: string; name: string; category: string; description: string; unit: string;
  price_from: number; price_to: number; setup_fee: number; eligible: boolean;
  locked_reason: string | null; locked_rule: string | null; default_qty: number; needs_one_of: string[];
}
export interface QuoteResponse { quote: Quote | null; fixes: Fix[]; addons: Addon[] }

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail: any = undefined;
    try { detail = await res.json(); } catch { /* not json */ }
    const msg = typeof detail?.detail === "string" ? detail.detail : detail?.detail?.message || `Request failed (${res.status})`;
    throw new ApiError(res.status, msg, detail?.detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  startSession: (lang: Lang) => call<SessionView>("/advisor/sessions", { method: "POST", body: JSON.stringify({ lang }) }),
  getSession: (sid: string) => call<SessionView>(`/advisor/sessions/${sid}`),
  send: (sid: string, text: string) =>
    call<SessionView>(`/advisor/sessions/${sid}/messages`, { method: "POST", body: JSON.stringify({ text }) }),
  quote: (sid: string, items: LineItem[], contract: Contract) =>
    call<QuoteResponse>(`/checkout/${sid}/quote`, { method: "POST", body: JSON.stringify({ items, contract }) }),
  accept: (sid: string, items: LineItem[], contract: Contract) =>
    call<{ order_id: string; state: string; quote: Quote }>(`/checkout/${sid}/accept`, {
      method: "POST", body: JSON.stringify({ items, contract }),
    }),
  order: (oid: string) => call<any>(`/checkout/orders/${oid}`),
};

// Indian digit grouping: 1,23,456
export function inr(n: number): string {
  return "₹" + Math.round(n).toLocaleString("en-IN");
}
