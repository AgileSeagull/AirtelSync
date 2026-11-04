# AirtelSync

**Project Udyam Digital** prototype (YTL Hackathon 2026, Enterprise Track A).

Digital-first acquisition and onboarding for small businesses, built for the fictional operator Accel Business.
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

- **LLM mode**: put `GEMINI_API_KEY` in `services/api/.env` (template: `.env.example`; the file is git-ignored and
  loaded automatically). Default model `gemini-2.5-flash` (override with `GEMINI_MODEL`); when it is busy or
  rate-limited (503/429) the turn moves to `GEMINI_FALLBACK_MODELS` (default `gemini-flash-lite-latest`,
  `gemini-flash-latest`). The free tier allows about 5 requests per minute per model, and one chat turn can use
  2–4 (tool calls), so the fallback chain matters on a free key. Claude is also
  supported (`ANTHROPIC_API_KEY`, `claude-opus-5-5`); `UDYAM_LLM_PROVIDER` picks one when both keys are set.
  The model talks; tools (`lookup_gstin`, `update_profile`, `recommend_bundle`, `check_product`,
  `handoff_to_human`) call the engine. An output guard rejects any rupee amount or product id not returned by a
  tool (one corrective retry, then fallback).
- **Scripted mode** (no key needed): rule-based English/Hindi/Hinglish slot filling over the same tools. It also
  answers any single turn the LLM cannot (error, or no reply within `UDYAM_LLM_TURN_TIMEOUT`, default 35 s); that
  exchange is added to the LLM's history and the next turn goes back to the LLM. Only a bad key or bad request
  switches the LLM off for the rest of the session, so a live demo never dead-ends.
- **Language follows the owner** turn by turn: Hindi (Devanagari) or another Indic script switches the app and
  the advisor to it, clearly English text switches back, and Hinglish, numbers, names or a GSTIN leave it as is.

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

## Sales & partner console (`/#/console`)

Demo sign-in by role (Accel staff / channel partner; header `X-Console-Role`).

- **Leads to call**: advisor conversations that did not convert, scored and ranked by P(activation) × monthly
  value, with the top three drivers, where the owner stopped, and routing (field sales for multi-site/manufacturers
  or ≥ ₹25k/month, channel partner for tier-2 micro, inside sales otherwise). Partners only see their leads.
  Identifiers typed into chat are masked.
- **Assisted mode**: "Offer help" sends the owner a one-time code; only when the owner shares it can the
  partner continue the owner's own journey (same rules, same prices). Every step is audit-logged.
- **Re-engage Q2**: 3,026 Q2 leads lost before a needs assessment, best first, with a suggested channel
  (WhatsApp link to the self-serve advisor where the loss was "no time for a visit" or "unreachable").
- **KYC reviews**: specialist approve/reject with a mandatory, audit-logged reason (staff only).
- **Lead score model**: logistic regression on facts known when a lead arrives (no outcome leakage), trained on
  Apr–May and tested on June: AUC 0.70, top-decile activation 18.2% vs 7.4% base (2.45×), top 30% of leads hold
  54% of activations.

## Business case deck

`docs/deck/AirtelSync_Business_Case.pptx` (10 slides on the official SYNC template, with entrance animations and
fade transitions; PDF copy alongside). Rebuild after changing numbers or screenshots:

```bash
pip install -r docs/deck/requirements.txt
python docs/deck/build_deck.py "../Submission Template_Sync.pptx" docs/deck/AirtelSync_Business_Case.pptx
```

Slides use Montserrat (available in Google Slides; install it locally for PowerPoint).

## Solution architecture

`docs/architecture/AirtelSync_Solution_Architecture.pdf`: one A3 landscape page with the main components (channels,
PWA screens, FastAPI services, external services, data layer) and the five numbered data flows (discover, quote,
verify, activate, learn & route). The source is `docs/architecture/architecture.html`; re-render with
`services/api/.venv/bin/python docs/architecture/render.py` (Playwright + installed Chrome).

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
| 6 | Back office: lead console, propensity score | done |

## Key engine facts (tested)

- Rejects all 49 rule-breaking line items (48 leads) that were actually sold in Q2 2026.
- Every one of the 5,000 lead profiles gets three valid bundle tiers (property test).
- GSTIN checksum validated across all 3,534 registry entries; cancelled/suspended GSTINs block GST-only products.

Today's date for all date checks is fixed at **2026-07-15** (per the case data README).
