# Udyam Digital

Digital-first acquisition and onboarding for small businesses (Accel Business, YTL Hackathon 2026 – Enterprise Track A).
A small-business owner chats with an advisor in their language, gets a bundle with one transparent monthly
price, completes KYC in minutes, and tracks installation without calling support.

**Design rule:** the LLM handles conversation; deterministic code decides eligibility, price and KYC verdicts.

## Layout

```
data/                 case CSVs + specimen KYC documents (synthetic)
apps/web/             React + Vite PWA (owner journey)
services/api/         FastAPI backend
  app/engine/         eligibility, pricing, recommendation (pure functions)
  app/ids/            GSTIN (checksum) and Udyam validators
  app/mocks/          mock GSTIN / Udyam registry APIs
  tests/              pytest suite
```

## Advisor modes

- **LLM mode** (Claude, `claude-opus-5-5` at low effort): set `ANTHROPIC_API_KEY` (see `services/api/.env.example`).
  The model talks; tools (`lookup_gstin`, `update_profile`, `recommend_bundle`, `check_product`, `handoff_to_human`)
  call the engine. An output guard rejects any rupee amount or product id not returned by a tool. Server-side
  refusal fallback is enabled (`fallbacks: "default"`).
- **Scripted mode** (no key needed): rule-based English/Hindi/Hinglish slot filling over the same tools. Also the
  automatic fallback if the LLM errors mid-session, so a live demo never dead-ends.

```bash
cd services/api
.venv/bin/python -m evals.run_advisor_evals          # 30 scenarios, scripted
.venv/bin/python -m evals.run_advisor_evals --llm    # same scenarios through Claude
```

## Smart KYC

Consent notice (DPDP: purpose-wise, no pre-ticked optional purposes, versioned, withdrawable) → documents by
photo/upload or **DigiLocker (mock)** → local OCR (Tesseract; red-channel watermark removal, deskew, blur score)
→ five layers of checks → verdict: `approved` · `needs_action` (owner can fix in-app) · `review` (specialist) ·
`blocked` (e.g. cancelled GSTIN) → Aadhaar e-sign (mock, demo OTP `123456`) → order moves to `KYCVerified`.

| Layer | Checks |
|---|---|
| Quality | blur (Laplacian variance), skew auto-correction, unreadable fields |
| Completeness | GST/Udyam, signatory ID, address proof; missing Udyam offered from the registry |
| Format | GSTIN repaired from OCR via structure + checksum + registry (accepted only if the name agrees); Udyam number |
| Registry | GSTIN exists and is **Active**; legal/trade name, constitution, address vs GST records; Udyam number, name, city |
| Consistency / recency | business name across all documents; address proof vs registered address; proprietor = signatory; bill ≤ 90 days; ID validity |

Raw images are encrypted at rest (Fernet) and deleted as soon as a decision is made (kept ≤ 7 days only for a
manual review); IDs are masked in every API response; every consent and document event is written to an audit log.

```bash
cd services/api && .venv/bin/python -m evals.run_kyc_evals -v    # 12/12 specimen applicants vs our answer key
```

| Applicant | Verdict | Why |
|---|---|---|
| K01 | blocked | GSTIN cancelled in GST records; Udyam certificate has no number and no registration exists |
| K02 | approved | photo tilted 7°, straightened automatically |
| K04 | needs_action | GST certificate too blurry → retake or fetch from DigiLocker |
| K05 | needs_action | Udyam certificate missing → registry match offered for one-tap confirmation |
| K07 | review | legal name on certificate altered ("Shri Physio Clinic" vs registry "Neelgiri Physio Clinic") |
| K11 | needs_action | electricity bill dated 31 Oct 2025, older than 90 days |
| K03, K06, K08, K09, K10, K12 | approved | clean (GSTIN OCR errors corrected) |

## Order tracker

`QuoteAccepted → KYCVerified → MandateSet (UPI AutoPay, mock) → InstallScheduled → Installed → Activated`, with
per-product ETAs from `typical_install_days` (products install in parallel), a promised date, SLA-breach flag and
proactive escalation on delay. If fibre is not feasible, fibre lines are rerouted to 5G AirFiber (P04) before the
owner waits, the quote is recalculated, and add-ons that need fibre are removed with an explanation. Every state
change sends an owner message (en/hi) to an outbox shown on the tracker; set `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` and `UDYAM_DEMO_WHATSAPP_TO` to also send them via the Twilio WhatsApp
sandbox (adapter not tested without credentials). The tracker polls every 5 s; a "Demo controls" panel simulates
the back office (next step, fibre not available, install delay). Activated orders show a referral card
(referrals convert at 14.8%, the best channel in the data).

## Run everything

```bash
# one-time setup
cd services/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ../..
cd apps/web && npm install && cd ../..

# development: API on :8000, web app on http://localhost:5173
./scripts/dev.sh

# demo / single process: build the web app, FastAPI serves it at http://localhost:8000
cd apps/web && npm run build && cd ../../services/api && .venv/bin/uvicorn app.main:app --port 8000
```

The owner app is a mobile-first PWA in 10 languages (full UI strings in English and Hindi): language picker →
advisor chat (text or voice via the browser's speech recognition) → three plan cards → quote builder with
item toggles, quantities, plan length (flexible / 12 / 24 months), one-tap fixes for broken dependencies,
locked add-ons with the reason → accepted quote with an application number.

## Run the API

```bash
cd services/api
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000     # docs at http://localhost:8000/docs
.venv/bin/pytest                                         # tests
```

## Build phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Core engine: catalogue, eligibility, dependencies, pricing, recommendation, mock GSTIN/Udyam APIs | done |
| 2 | GenAI advisor: tool-calling loop, multilingual, output guard, eval harness | done |
| 3 | Owner web app: chat, quote & checkout with toggles | done |
| 4 | Smart KYC: consent, OCR, layered checks, verdicts | done |
| 5 | Order tracker: state machine, ETAs, notifications | done |
| 6 | Back office: lead console, propensity score | |

## Key engine facts (tested)

- Rejects all 49 rule-breaking line items (48 leads) that were actually sold in Q2 2026.
- Every one of the 5,000 lead profiles gets three valid bundle tiers (property test).
- GSTIN checksum validated across all 3,534 registry entries; cancelled/suspended GSTINs block GST-only products.

Today's date for all date checks is fixed at **2026-07-15** (per the case data README).
