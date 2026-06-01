# TalkToBook — web MVP

Thin web wrapper around the `scripts/build.py` transcript→EPUB engine. Paste or
upload a transcript → free preview EPUB → `$9` unlock → clean, branded
**EPUB + PDF + Kindle**. No accounts; jobs live on disk, paid files gated behind
a separate download token.

See [`../PRD.local.md`](../PRD.local.md) for the product rationale, pricing, and
validation plan.

## What it does

| | Free preview | Paid unlock |
|---|---|---|
| Clean reading text | ✅ | ✅ |
| Cover | plain auto cover | your image / accent |
| Branding | "Made with TalkToBook" colophon | removed |
| Formats | EPUB | EPUB + PDF + Kindle (AZW3) |

## Run locally

```bash
cd webapp
./run.sh                 # creates .venv, installs deps, serves on :8000
# or manually:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000.

**System deps:** `pandoc` (EPUB, required). For paid formats: `weasyprint` (PDF,
in `requirements.txt` but needs pango/cairo system libs) and `calibre`'s
`ebook-convert` (Kindle AZW3). Missing tools degrade gracefully — `GET
/api/config` reports `capabilities`. The Dockerfile installs all three.

## Payments

- **No Stripe keys** → *intent-capture mode*: the unlock button records the
  creator's email as a demand signal (`jobs/events.jsonl`) and shows a
  "payments launching soon" message. This is the PRD's validate-before-wiring
  path.
- **Stripe keys set** → one-time Checkout. On `checkout.session.completed` the
  webhook builds and unlocks the paid edition. Configure the webhook to
  `POST /api/webhook`.
- **`ALLOW_FREE_UNLOCK=true`** (local only) fulfills the paid edition without
  charging, so you can exercise the full flow offline.

Copy `.env.example` → `.env` and fill in keys. Stripe webhook for local testing:

```bash
stripe listen --forward-to localhost:8000/api/webhook
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Landing + converter |
| GET | `/api/config` | Price, currency, Stripe on/off, format capabilities |
| POST | `/api/preview` | Build free preview (multipart) |
| POST | `/api/unlock` | Start checkout / capture intent / dev-fulfill |
| POST | `/api/webhook` | Stripe payment fulfillment |
| GET | `/api/job/{id}` | Job status + paid download links |
| GET | `/d/{id}/{token}/{name}` | Gated file download (`token=preview` for the free EPUB) |

## Funnel instrumentation

Events append to `jobs/events.jsonl`: `preview_created`, `unlock_click`,
`unlock_intent`, `payment_fulfilled` — enough to read visits → previews →
unlock clicks → payments for the validation slice.

## Deploy (Railway / Render / Fly)

Build the root `Dockerfile` at `webapp/Dockerfile` (it copies both `scripts/`
and `webapp/`). Set `PUBLIC_URL` to the deployed origin and the Stripe env vars.
`jobs/` is ephemeral on these platforms — fine for the MVP; mount a volume if
you need links to outlive a redeploy.
