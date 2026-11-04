# Udyam Digital

Digital-first acquisition and onboarding for small businesses (Accel Business, YTL Hackathon 2026 – Enterprise Track A).
A small-business owner chats with an advisor in their language, gets a bundle with one transparent monthly
price, completes KYC in minutes, and tracks installation without calling support.

**Design rule:** the LLM handles conversation; deterministic code decides eligibility, price and KYC verdicts.

## Layout

```
data/                 case CSVs + specimen KYC documents (synthetic)
services/api/         FastAPI backend
  app/engine/         eligibility, pricing, recommendation (pure functions)
  app/ids/            GSTIN (checksum) and Udyam validators
  app/mocks/          mock GSTIN / Udyam registry APIs
  tests/              pytest suite
```

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
| 2 | GenAI advisor: tool-calling loop, multilingual, output guard, eval harness | |
| 3 | Owner web app: chat, quote & checkout with toggles | |
| 4 | Smart KYC: consent, OCR, layered checks, verdicts | |
| 5 | Order tracker: state machine, ETAs, notifications | |
| 6 | Back office: lead console, propensity score | |

## Key engine facts (tested)

- Rejects all 49 rule-breaking line items (48 leads) that were actually sold in Q2 2026.
- Every one of the 5,000 lead profiles gets three valid bundle tiers (property test).
- GSTIN checksum validated across all 3,534 registry entries; cancelled/suspended GSTINs block GST-only products.

Today's date for all date checks is fixed at **2026-07-15** (per the case data README).
