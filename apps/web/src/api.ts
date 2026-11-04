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

// ------------------------------------------------------------------ KYC
export type DocType = "gst_certificate" | "udyam_certificate" | "signatory_id" | "address_proof";
export type CheckStatus = "pass" | "info" | "action" | "review" | "block";
export interface KycCheck {
  code: string; layer: string; status: CheckStatus; title: string; message: string;
  doc_type: DocType | null; action: "retake" | "upload" | "confirm_udyam" | "digilocker" | "none";
}
export interface KycDoc {
  id: string; doc_type: DocType; label: string; source: "upload" | "digilocker" | "registry" | "sample";
  filename: string | null; quality: Record<string, any>; fields: Record<string, any>; raw_deleted: boolean;
}
export interface KycCase {
  id: string; order_id: string | null; lang: Lang; consent_id: string | null;
  verdict: "pending" | "approved" | "needs_action" | "review" | "blocked";
  verified_at: string | null; esigned_at: string | null; documents: Partial<Record<DocType, KycDoc>>;
  required: DocType[]; checks: KycCheck[]; demo_otp: string;
}
export interface Notice {
  version: string; title: string; intro: string; collect: string[]; use: string; how: string; keep: string;
  rights: string; purposes: Record<string, string>; agree: string;
}

async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api${path}`, { method: "POST", body: form });
  if (!res.ok) {
    let detail: any;
    try { detail = await res.json(); } catch { /* ignore */ }
    throw new ApiError(res.status, typeof detail?.detail === "string" ? detail.detail : `Upload failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const kyc = {
  notice: (lang: Lang) => call<Notice>(`/kyc/notice?lang=${lang}`),
  create: (order_id: string | null, lang: Lang) => call<KycCase>("/kyc/cases", { method: "POST", body: JSON.stringify({ order_id, lang }) }),
  get: (id: string) => call<KycCase>(`/kyc/cases/${id}`),
  consent: (id: string, purposes: string[], lang: Lang) =>
    call<{ case: KycCase }>(`/kyc/cases/${id}/consent`, { method: "POST", body: JSON.stringify({ purposes, lang }) }),
  withdraw: (id: string) => call<KycCase>(`/kyc/cases/${id}/consent`, { method: "DELETE" }),
  upload: (id: string, file: File, docType: DocType) => {
    const f = new FormData();
    f.append("file", file);
    f.append("doc_type", docType);
    return upload<{ document_type: DocType; case: KycCase }>(`/kyc/cases/${id}/documents`, f);
  },
  sample: (id: string, applicant: string) => call<KycCase>(`/kyc/cases/${id}/sample/${applicant}`, { method: "POST" }),
  digilocker: (id: string, gstin: string | null) =>
    call<KycCase>(`/kyc/cases/${id}/digilocker`, { method: "POST", body: JSON.stringify({ gstin }) }),
  confirmUdyam: (id: string) => call<KycCase>(`/kyc/cases/${id}/confirm-udyam`, { method: "POST" }),
  verify: (id: string) => call<KycCase>(`/kyc/cases/${id}/verify`, { method: "POST" }),
  esign: (id: string, otp: string) => call<KycCase>(`/kyc/cases/${id}/esign`, { method: "POST", body: JSON.stringify({ otp }) }),
};

// ------------------------------------------------------------------ tracking
export interface TrackStep { state: string; label: string; status: "done" | "current" | "upcoming"; at: string | null }
export interface TrackLine { product_id: string; name: string; qty: number; install_days: number; state: string; eta: string | null }
export interface Track {
  order_id: string; state: string; label: string; steps: TrackStep[]; lines: TrackLine[]; eta: string | null;
  promised_by: string | null; install_slot: string | null; sla_breach: boolean; rerouted: boolean;
  mandate: { upi_id_masked: string; max_amount: number } | null;
  quote: { monthly_total: number; setup_total: number; earliest_activation_days: number }; contract: string;
  business: { trade_name?: string; business_type?: string; city?: string };
  events: { at: string; state: string; note: string | null }[];
  notifications: { id: string; event: string; text: string; at: string; delivery: string }[];
  owner_action: { type: "kyc" | "mandate"; amount?: number; kyc_case_id?: string | null } | null;
  activated_at: string | null; lang: Lang;
}

export const orders = {
  track: (oid: string) => call<Track>(`/orders/${oid}/track`),
  mandate: (oid: string, upi_id: string) => call<Track>(`/orders/${oid}/mandate`, { method: "POST", body: JSON.stringify({ upi_id }) }),
  advance: (oid: string, fibre_feasible = true) =>
    call<Track>(`/orders/${oid}/advance`, { method: "POST", body: JSON.stringify({ fibre_feasible }) }),
  delay: (oid: string) => call<Track>(`/orders/${oid}/delay`, { method: "POST" }),
};

export function fmtDate(iso: string | null, lang: Lang, withTime = false): string {
  if (!iso) return "";
  const d = new Date(iso);
  const opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" };
  if (withTime) Object.assign(opts, { hour: "numeric", minute: "2-digit" });
  return d.toLocaleString(lang === "hi" ? "hi-IN" : "en-IN", opts);
}

// ------------------------------------------------------------------ console
export type Role = "sales" | "partner";
async function ccall<T>(role: Role, path: string, init?: RequestInit): Promise<T> {
  return call<T>(path, { ...init, headers: { "X-Console-Role": role, ...(init?.headers || {}) } });
}
export interface Driver { factor: string; effect: "up" | "down"; weight: number }
export const consoleApi = {
  summary: (r: Role) => ccall<any>(r, "/console/summary"),
  leads: (r: Role) => ccall<any[]>(r, "/console/leads"),
  reengage: (r: Role) => ccall<any>(r, "/console/reengage?limit=25"),
  model: (r: Role) => ccall<any>(r, "/console/model"),
  reviews: (r: Role) => ccall<any[]>(r, "/console/kyc-reviews"),
  decide: (r: Role, id: string, decision: string, note: string) =>
    ccall<any>(r, `/console/kyc-reviews/${id}`, { method: "POST", body: JSON.stringify({ decision, note }) }),
  assist: (r: Role, sid: string) => ccall<{ demo_code: string }>(r, `/console/leads/${sid}/assist`, { method: "POST" }),
  assistConfirm: (r: Role, sid: string, code: string, partner: string) =>
    ccall<{ continue_url: string }>(r, `/console/leads/${sid}/assist/confirm`, { method: "POST", body: JSON.stringify({ code, partner }) }),
};

// Indian digit grouping: 1,23,456
export function inr(n: number): string {
  return "₹" + Math.round(n).toLocaleString("en-IN");
}
