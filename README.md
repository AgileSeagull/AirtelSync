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
| 4 | Smart KYC: consent, OCR, layered checks, verdicts | |
| 5 | Order tracker: state machine, ETAs, notifications | |
| 6 | Back office: lead console, propensity score | |

## Key engine facts (tested)

- Rejects all 49 rule-breaking line items (48 leads) that were actually sold in Q2 2026.
- Every one of the 5,000 lead profiles gets three valid bundle tiers (property test).
- GSTIN checksum validated across all 3,534 registry entries; cancelled/suspended GSTINs block GST-only products.

Today's date for all date checks is fixed at **2026-07-15** (per the case data README).
