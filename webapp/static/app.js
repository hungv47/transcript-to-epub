// TalkToBook front-end. Plain JS — no build step.
const $ = (sel, root = document) => root.querySelector(sel);

let CONFIG = { price_cents: 900, currency: "usd", stripe_enabled: false };
let CURRENT_JOB = null;

function money(cents, currency) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: (currency || "usd").toUpperCase() })
    .format(cents / 100)
    .replace(/\.00$/, "");
}

async function loadConfig() {
  try {
    CONFIG = await (await fetch("/api/config")).json();
    const p = money(CONFIG.price_cents, CONFIG.currency);
    ["price", "unlock-price", "plan-price"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = p;
    });
    if (CONFIG.capabilities && CONFIG.capabilities.epub === false) {
      const form = document.getElementById("preview-form");
      const err = document.getElementById("preview-error");
      const btn = form?.querySelector("button[type=submit]");
      if (btn) btn.disabled = true;
      if (err) {
        err.textContent = "EPUB generation is temporarily unavailable on this server.";
        err.hidden = false;
      }
    }
  } catch (_) { /* defaults are fine */ }
}

// ---- Sample library ----
async function loadSamples() {
  const grid = document.getElementById("sample-grid");
  if (!grid) return;
  try {
    const { samples } = await (await fetch("/api/samples")).json();
    if (!samples || !samples.length) { grid.closest("section").style.display = "none"; return; }
    grid.innerHTML = samples.map(function (s) {
      const cover = s.cover
        ? `<img class="sample-cover" src="${s.cover}" alt="Cover of ${esc(s.title)}" loading="lazy" />`
        : `<div class="sample-cover sample-cover--blank"></div>`;
      const pdf = s.pdf ? ` · <a href="${s.pdf}" download>PDF</a>` : "";
      return `<article class="sample-card">
        <div class="sample-coverframe">${cover}</div>
        <div class="sample-body">
          <span class="sample-kind">${esc(s.kind || "Sample")}</span>
          <h3>${esc(s.title)}</h3>
          <p class="sample-author">by ${esc(s.author)}</p>
          <p class="sample-blurb">${esc(s.blurb)}</p>
          <div class="sample-actions">
            <a class="btn btn-primary btn-sm" href="${s.epub}" download>Download EPUB</a>
            <span class="sample-alt">${pdf}</span>
          </div>
        </div>
      </article>`;
    }).join("");
  } catch (_) {
    grid.closest("section").style.display = "none";
  }
}
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---- Preview ----
$("#preview-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const err = $("#preview-error");
  err.hidden = true;
  const btn = form.querySelector("button[type=submit]");
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Generating EPUB…";

  try {
    const sourceUrl = (form.source_url?.value || "").trim();
    const fileInput = form.file;
    const hasFile = Boolean(fileInput && fileInput.files && fileInput.files.length);
    const hasTranscript = Boolean((form.transcript?.value || "").trim());
    if (!sourceUrl && !hasFile && !hasTranscript) {
      throw new Error("Enter a YouTube URL or upload a transcript file.");
    }

    const fd = new FormData(form);
    // Checkbox → explicit string the backend understands.
    fd.set("owns", form.owns.checked ? "true" : "");
    if (!hasFile) fd.delete("file");
    if (!hasTranscript) fd.delete("transcript");

    const res = await fetch("/api/preview", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Something went wrong.");
    CURRENT_JOB = data;
    renderResult(data);
  } catch (ex) {
    err.textContent = ex.message || "Something went wrong. Try again, or email hello@talktobook.example if it keeps happening.";
    err.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
});

function renderResult(job) {
  $("#result-title").textContent = job.title;
  const words = job.word_count ? `${job.word_count.toLocaleString()} words · ` : "";
  $("#result-meta").textContent = `${words}${job.author ? "by " + job.author : "ready to read"}`;
  const dl = $("#download-preview");
  dl.href = job.preview.epub;
  $("#cover-prompt").textContent = job.cover_prompt || "";
  $("#result").classList.remove("hidden");
  $("#result").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---- Unlock ----
$("#unlock-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!CURRENT_JOB) return;
  const msg = $("#unlock-msg");
  msg.hidden = true;
  msg.classList.remove("err");
  const btn = $("#unlock-btn");
  const label = btn.innerHTML;
  btn.disabled = true;
  btn.textContent = "Working…";

  try {
    const fd = new FormData(e.target);
    fd.set("job_id", CURRENT_JOB.job_id);
    const res = await fetch("/api/unlock", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Unlock failed.");

    if (data.checkout_url) {
      window.location.href = data.checkout_url; // Stripe Checkout
      return;
    }
    if (data.paid && data.downloads) {
      renderDownloads(data.downloads); // dev free-unlock
      return;
    }
    // Intent-capture mode (payments not wired yet).
    msg.textContent = data.message || "Thanks — we saved your interest.";
    msg.hidden = false;
  } catch (ex) {
    msg.textContent = ex.message || "Couldn't unlock. Try again, or email hello@talktobook.example.";
    msg.classList.add("err");
    msg.hidden = false;
  } finally {
    btn.disabled = false;
    btn.innerHTML = label;
  }
});

function renderDownloads(downloads) {
  const msg = $("#unlock-msg");
  const links = Object.entries(downloads)
    .map(([k, url]) => `<a href="${esc(url)}" download>${esc(k.toUpperCase())}</a>`)
    .join(" · ");
  msg.innerHTML = `Unlocked! Download: ${links}`;
  msg.hidden = false;
}

loadConfig();
loadSamples();
