#!/usr/bin/env bash
# Generate AI cover art for the sample books with the `ai` CLI (Vercel AI
# Gateway). Writes samples/covers/<slug>.png, which app/samples.py then embeds.
#
# Auth first (one of):
#   export AI_GATEWAY_API_KEY=...        # create at vercel.com/.../ai/api-keys
#   # or: npx vercel link && vc env pull
#
# Model defaults to openai/gpt-image-2 (best at rendering legible title text);
# override with AI_IMAGE_MODEL=<creator/model> (e.g. google/imagen-4.0-generate-001).
set -euo pipefail
cd "$(dirname "$0")/.."   # -> webapp/

MODEL="${AI_IMAGE_MODEL:-openai/gpt-image-2}"
OUT="samples/covers"
mkdir -p "$OUT"

# Pull the canonical sample list (slug / title / author) from the app.
python3 - <<'PY' > /tmp/_t2b_samples.tsv
import sys; sys.path.insert(0, ".")
from app import samples
for s in samples.SAMPLES:
    print(f"{s['slug']}\t{s['title']}\t{s['author']}")
PY

while IFS=$'\t' read -r slug title author; do
  prompt="Minimalist editorial book cover, portrait 2:3 aspect ratio. The title \"$title\" set large in a clean serif or restrained sans-serif, deep ink #1E1A17, in the upper area. Below the title, a single thin horizontal rule in oxblood #7F1D1D as the only accent, used sparingly. Near the bottom, the byline \"$author\" small in muted warm grey. Background warm paper #F7F0E5. Calm, editorial, generous negative space. No gradients, no neon glow, no glassy panels, no photography, no clutter."
  echo "→ generating cover: $slug ($MODEL)"
  ai image "$prompt" -m "$MODEL" --size 1024x1536 -o "$OUT/$slug.png" --quiet --no-preview
done < /tmp/_t2b_samples.tsv

echo "Done. Covers written to $OUT/ — restart the server to rebuild sample EPUBs with them."
