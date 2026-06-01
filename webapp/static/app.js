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
  } catch (_) { /* defaults are fine */ }
}

// ---- Tabs ----
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const which = tab.dataset.tab;
    document.querySelectorAll(".tab-panel").forEach((p) =>
      p.classList.toggle("hidden", p.dataset.panel !== which)
    );
  });
});

// ---- Preview ----
$("#preview-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const err = $("#preview-error");
  err.hidden = true;
  const btn = form.querySelector("button[type=submit]");
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Building your preview…";

  try {
    const fd = new FormData(form);
    // Checkbox → explicit string the backend understands.
    fd.set("owns", form.owns.checked ? "true" : "");
    // Only send the active input (avoid empty file overwriting pasted text).
    const activeTab = document.querySelector(".tab.active").dataset.tab;
    if (activeTab === "paste") fd.delete("file");
    else fd.delete("transcript");

    const res = await fetch("/api/preview", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Something went wrong.");
    CURRENT_JOB = data;
    renderResult(data);
  } catch (ex) {
    err.textContent = ex.message;
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
    msg.textContent = ex.message;
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
    .map(([k, url]) => `<a href="${url}" download>${k.toUpperCase()}</a>`)
    .join(" · ");
  msg.innerHTML = `Unlocked! Download: ${links}`;
  msg.hidden = false;
}

loadConfig();
