# Deploy TalkToBook

Container app (pandoc + WeasyPrint, optional Calibre). **Not serverless** —
deploy the `webapp/Dockerfile` to a container host. Build context is the **repo
root** (the Dockerfile copies both `scripts/` and `webapp/`).

## Ship posture (validation slice)

First ship runs in **intent-capture mode**: free preview + sample downloads +
"unlock" captures an email as a demand signal. **No Stripe keys needed.** Wire
payments only after the unlock signal clears your kill threshold (see PRD).

| Format | In the lean image |
|---|---|
| EPUB | ✅ pandoc |
| PDF | ✅ WeasyPrint |
| Kindle AZW3 | ⛔ until you build with `--build-arg INSTALL_CALIBRE=true` |

The app detects capabilities at runtime (`GET /healthz`) and degrades gracefully.

## Option A — Render (no CLI, GitHub-connected)

1. Push this repo to GitHub (done if `git remote` points at it).
2. Render → **New → Blueprint** → pick this repo. It reads [`render.yaml`](../render.yaml).
3. First deploy completes → copy the URL (e.g. `https://talktobook.onrender.com`).
4. Set env `PUBLIC_URL` to that URL → redeploy.
5. Smoke test: open the URL, `GET /healthz`, run a preview, download a sample.

## Option B — Railway (no CLI, GitHub-connected)

1. Railway → **New Project → Deploy from GitHub repo** → this repo.
2. Service settings → **Build**: Dockerfile path `webapp/Dockerfile`, root `/`.
3. **Variables**: `PUBLIC_URL=https://<app>.up.railway.app`, `MAX_TRANSCRIPT_CHARS=800000`.
4. Deploy → smoke test as above.

## Option C — Fly.io (CLI)

```bash
brew install flyctl && fly auth login
cd /path/to/transcript-to-epub
fly launch --dockerfile webapp/Dockerfile --no-deploy   # creates fly.toml
fly secrets set PUBLIC_URL=https://<app>.fly.dev
fly deploy
```
Set the health check path to `/healthz` in `fly.toml`.

## Going live with payments (later)

1. Add `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`.
2. In Stripe, point a webhook at `https://<your-domain>/api/webhook`
   (event `checkout.session.completed`).
3. **Test mode first**: run one full Checkout round-trip (the fresh-eyes review
   flagged the Stripe binding as unit-tested only).
4. For Kindle output, rebuild with `INSTALL_CALIBRE=true`.

## Persistence note

`jobs/` (previews, paid files, funnel `events.jsonl`) is **ephemeral** on these
platforms — fine for validation. Mount a volume at `/srv/webapp/jobs` if you need
download links / leads to survive restarts.
