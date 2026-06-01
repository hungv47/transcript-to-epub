# Deploy TalkToBook (Railway)

Container app (pandoc + WeasyPrint, optional Calibre). **Not serverless** —
deploy the `webapp/Dockerfile` to a container host. Build context is the **repo
root** (the Dockerfile copies both `scripts/` and `webapp/`). Config lives in
[`railway.json`](../railway.json).

## Ship posture (validation slice)

First ship can run in **intent-capture mode**: free preview + sample downloads +
"unlock" captures an email as a demand signal. **No Polar keys needed.** Wire
payments only after the unlock signal clears your kill threshold (see PRD).

| Format | In the lean image |
|---|---|
| EPUB | ✅ pandoc |
| PDF | ✅ WeasyPrint |
| Kindle AZW3 | ⛔ until you build with `INSTALL_CALIBRE=true` |

The app detects capabilities at runtime (`GET /healthz`) and degrades gracefully.

## Deploy — GitHub connect (no CLI)

1. [railway.com](https://railway.com) → **New Project → Deploy from GitHub repo**
   → `hungv47/transcript-to-epub`. Railway reads `railway.json` (Dockerfile build,
   `webapp/Dockerfile`, healthcheck `/healthz`).
2. Service → **Settings → Networking → Generate Domain**. Railway injects
   `RAILWAY_PUBLIC_DOMAIN`, and the app derives `PUBLIC_URL` from it automatically
   — no manual URL step needed.
3. First build pulls pandoc + WeasyPrint libs (a few minutes). When it's live,
   smoke test: open the domain, `GET /healthz`, run a preview, download a sample.

That's it for the validation ship.

## Deploy — CLI (alternative)

```bash
npm i -g @railway/cli      # or: brew install railway
railway login
cd /path/to/transcript-to-epub
railway init                # create/link a project
railway up                  # build webapp/Dockerfile from repo root
railway domain              # generate a public URL
```

## Environment variables

| Var | When | Notes |
|---|---|---|
| `PUBLIC_URL` | optional on Railway | auto-derived from `RAILWAY_PUBLIC_DOMAIN`; set explicitly only for a custom domain |
| `MAX_TRANSCRIPT_CHARS` | optional | default `800000` |
| `POLAR_ACCESS_TOKEN` / `POLAR_PRODUCT_ID` / `POLAR_WEBHOOK_SECRET` | to go live | unset → intent-capture mode |
| `POLAR_SERVER` | testing | `sandbox` for sandbox tokens/products; default `production` |
| `PLAN_PRICE_CENTS` | optional | UI display price; default `700` |
| `FORCE_HTTPS` | production | defaults on when `PUBLIC_URL` starts with `https://`; fixes insecure download warnings |
| `INSTALL_CALIBRE` (build arg) | for Kindle | set `true` in Railway **Build** settings to enable AZW3 |

`PORT` is injected by Railway and honored by the Dockerfile CMD — don't set it.

## Going live with payments

1. Create a recurring `$7/month` Polar product and copy its Product ID.
2. Add `POLAR_ACCESS_TOKEN`, `POLAR_PRODUCT_ID`, and `POLAR_WEBHOOK_SECRET`.
3. Polar → webhook → `https://<your-domain>/api/webhook`, events `order.paid`,
   `subscription.active`, `subscription.canceled`, `subscription.revoked`, and
   `customer.state_changed`.
4. **Sandbox first**: set `POLAR_SERVER=sandbox` and run one full Checkout
   round-trip before switching to production keys.
5. For Kindle output, set build arg `INSTALL_CALIBRE=true` and redeploy.

## Persistence note

`jobs/` (previews, paid files, funnel `events.jsonl`) is **ephemeral** by default.
Fine for validation. For links/leads to survive restarts, attach a Railway
**Volume** mounted at `/srv/webapp/jobs`.
