// TalkToBook front-end. Plain JS — no build step.
const $ = (sel, root = document) => root.querySelector(sel);

let CONFIG = { price_cents: 700, price_annual_cents: 6700, currency: "usd", payments_enabled: false };
let CURRENT_JOB = null;

function money(cents, currency) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: (currency || "usd").toUpperCase() })
    .format(cents / 100)
    .replace(/\.00$/, "");
}

// Pricing-section billing toggle. The Polar checkout offers both intervals
// regardless; this only swaps what the Creator Plan card displays.
function selectedBilling() {
  return document.querySelector('input[name="billing"]:checked')?.value || "monthly";
}

function renderPlanPrice(period) {
  const priceEl = document.getElementById("plan-price");
  const periodEl = document.getElementById("plan-period");
  const yearly = CONFIG.price_annual_cents ? money(CONFIG.price_annual_cents, CONFIG.currency) : null;
  if (period === "yearly" && yearly) {
    if (priceEl) priceEl.textContent = yearly;
    if (periodEl) periodEl.textContent = "/year";
  } else {
    if (priceEl) priceEl.textContent = money(CONFIG.price_cents, CONFIG.currency);
    if (periodEl) periodEl.textContent = "/month";
  }
}

document.querySelectorAll('input[name="billing"]').forEach((radio) => {
  radio.addEventListener("change", () => renderPlanPrice(radio.value));
});

// Pay for the Creator Plan straight from the pricing section: start a Polar
// checkout for the selected interval, no preview job required.
const getPlanBtn = document.getElementById("get-plan-btn");
if (getPlanBtn) {
  getPlanBtn.addEventListener("click", async () => {
    const msg = document.getElementById("get-plan-msg");
    if (msg) { msg.hidden = true; msg.classList.remove("err"); }
    const label = getPlanBtn.textContent;
    getPlanBtn.disabled = true;
    getPlanBtn.textContent = "Starting checkout…";
    try {
      const fd = new FormData();
      fd.set("interval", selectedBilling());
      const res = await fetch("/api/checkout", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Couldn't start checkout.");
      if (data.checkout_url) { window.location.href = data.checkout_url; return; }
      if (msg) { msg.textContent = data.message || "Thanks. We saved your interest."; msg.hidden = false; }
    } catch (ex) {
      if (msg) {
        msg.textContent = ex.message || `Couldn't start checkout. Try again, or email ${CONFIG.contact_email || "hello@talktobook.example"}.`;
        msg.classList.add("err");
        msg.hidden = false;
      }
    } finally {
      getPlanBtn.disabled = false;
      getPlanBtn.textContent = label;
    }
  });
}

async function loadConfig() {
  try {
    CONFIG = await (await fetch("/api/config")).json();
    // Set the CTA mode first: in waitlist mode this replaces the whole button
    // label (incl. the price span), so the price loop below cleanly skips the
    // now-absent #unlock-price node instead of formatting then clobbering it.
    applyPaymentMode();
    const p = money(CONFIG.price_cents, CONFIG.currency);
    ["price", "unlock-price"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = p;
    });
    if (CONFIG.price_annual_cents) {
      const ann = document.getElementById("price-annual");
      if (ann) ann.textContent = money(CONFIG.price_annual_cents, CONFIG.currency);
    }
    renderPlanPrice(selectedBilling());
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

// Keep the unlock CTA honest: when Polar isn't wired yet, a click captures
// interest rather than charging, so don't promise an instant subscription.
function applyPaymentMode() {
  if (CONFIG.payments_enabled) return;
  const btn = document.getElementById("unlock-btn");
  if (btn) btn.textContent = "Join the creator-plan waitlist";
  const plan = document.getElementById("get-plan-btn");
  if (plan) plan.textContent = "Join the creator-plan waitlist";
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
    err.textContent = ex.message || `Something went wrong. Try again, or email ${CONFIG.contact_email || "hello@talktobook.example"} if it keeps happening.`;
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
      window.location.href = data.checkout_url; // Polar Checkout
      return;
    }
    if (data.paid && data.downloads) {
      renderDownloads(data.downloads); // dev free-unlock
      return;
    }
    // Intent-capture mode (payments not wired yet).
    msg.textContent = data.message || "Thanks. We saved your interest.";
    msg.hidden = false;
  } catch (ex) {
    msg.textContent = ex.message || `Couldn't unlock. Try again, or email ${CONFIG.contact_email || "hello@talktobook.example"}.`;
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

// A canceled Polar checkout returns the visitor to /?canceled=<job_id>. Restore
// their preview and unlock panel instead of dropping them on a blank homepage.
async function restoreCanceledJob() {
  const jobId = new URLSearchParams(location.search).get("canceled");
  if (!jobId) return;
  history.replaceState(null, "", location.pathname + location.hash);
  try {
    const res = await fetch(`/api/job/${encodeURIComponent(jobId)}`);
    if (!res.ok) return;
    const job = await res.json();
    if (!job || !job.preview) return;
    CURRENT_JOB = job;
    renderResult(job);
    const msg = $("#unlock-msg");
    if (msg) {
      msg.textContent = "Checkout canceled. Your preview is still here whenever you're ready.";
      msg.classList.remove("err");
      msg.hidden = false;
    }
  } catch (_) { /* leave the page as-is */ }
}

// loadConfig never rejects (it catches internally), so restore always runs —
// after config resolves, so the unlock CTA label is settled deterministically.
loadConfig().then(restoreCanceledJob);
