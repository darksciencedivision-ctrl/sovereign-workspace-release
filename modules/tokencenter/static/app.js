const $ = (selector) => document.querySelector(selector);

const TOKEN_STEP = 1000;
const MAX_ACTIVE_DROPS = 7;
const MAX_QUEUED_DROPS = 20;
const DROP_INTERVAL_MS = 800;
const DROP_FALL_MS = 1250;
const DROP_LIFE_MIN_MS = 30000;
const DROP_LIFE_MAX_MS = 60000;
const SUMMARY_POLL_MS = 30000;
const DROP_SOURCES = [
  { key: "sam", name: "Sam Altman", asset: "/assets/gold-drop-sam.png", weight: 1 },
  { key: "elon", name: "Elon Musk", asset: "/assets/gold-drop-elon.png", weight: 1 },
  { key: "dario", name: "Dario Amodei", asset: "/assets/gold-drop-dario.png", weight: 1 },
];

let currentSummary = null;
let selectedDate = null;
let goldQueue = 0;
let nextDropTimer = null;
let weightedDropSources = DROP_SOURCES;
const activeDrops = new Set();

function tokenNumber(value) {
  return new Intl.NumberFormat("en-US", {
    notation: Number(value) >= 1000000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value || 0);
}

function fullNumber(value) {
  return new Intl.NumberFormat("en-US").format(value || 0);
}

function dayLabel(value) {
  const date = new Date(`${value}T12:00:00`);
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
}

function renderChart(days) {
  const chart = $("#chart");
  const max = Math.max(...days.map((day) => day.total_tokens), 1);
  chart.innerHTML = days.map((day) => {
    const height = day.total_tokens ? Math.max(7, Math.round((day.total_tokens / max) * 100)) : 2;
    const selected = day.date === selectedDate;
    return `<button class="bar-cell ${selected ? "selected" : ""}" data-date="${day.date}" type="button" aria-pressed="${selected}" title="${day.date}: ${fullNumber(day.total_tokens)} observed tokens">
      <span class="bar-value">${tokenNumber(day.total_tokens)}</span>
      <span class="bar-track"><span class="bar" style="height:${height}%"></span></span>
      <span class="bar-day">${dayLabel(day.date)}</span>
    </button>`;
  }).join("");
  chart.querySelectorAll(".bar-cell").forEach((button) => button.addEventListener("click", () => {
    selectedDate = button.dataset.date;
    renderChart(currentSummary.days);
    renderModels(currentSummary, selectedDate);
  }));
}

function renderModels(summary, date) {
  const rows = summary.models.filter((row) => row.date === date);
  $("#selected-day").textContent = date === summary.range.to ? "today" : dayLabel(date);
  $("#models").innerHTML = rows.length ? rows.map((row) => `<tr>
    <td><strong>${escapeHtml(row.provider)}</strong><span>${escapeHtml(row.model)}</span></td>
    <td><span class="pill ${escapeHtml(row.locality)}">${escapeHtml(row.locality)}</span></td>
    <td class="numeric">${fullNumber(row.total_tokens)}</td>
    <td><span class="pill verified">${escapeHtml(row.confidence)}</span></td>
  </tr>`).join("") : `<tr><td colspan="4" class="empty">No numeric token events were observed on ${escapeHtml(dayLabel(date))}.</td></tr>`;
}

function renderProviders(providers) {
  $("#providers").innerHTML = providers.map((provider) => {
    const known = provider.confidence === "VERIFIED";
    const icon = known ? "✓" : "?";
    const models = (provider.models || []).length
      ? `<span class="provider-models">${provider.models.map(escapeHtml).join(", ")}</span>`
      : "";
    return `<details class="provider" ${!known ? "open" : ""}>
      <summary><span class="status ${known ? "known" : "unknown"}">${icon}</span><span><strong>${escapeHtml(provider.provider)}</strong><small>${escapeHtml(provider.coverage)}</small></span></summary>
      <p>${escapeHtml(provider.detail)}</p>${models}
    </details>`;
  }).join("");
}

function safeStoredThreshold(key) {
  try {
    const stored = Number.parseInt(localStorage.getItem(key), 10);
    return Number.isFinite(stored) ? stored : null;
  } catch {
    return null;
  }
}

function storeThreshold(key, value) {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // The visual remains functional when browser storage is unavailable.
  }
}

function sourceWeights(summary) {
  const weights = new Map(DROP_SOURCES.map((source) => [source.key, 0]));
  summary.models
    .filter((row) => row.date === summary.today.date)
    .forEach((row) => {
      const identity = `${row.provider || ""} ${row.model || ""}`.toLowerCase();
      const tokens = Math.max(0, Number(row.total_tokens) || 0);
      if (/anthropic|claude/.test(identity)) weights.set("dario", weights.get("dario") + tokens);
      else if (/xai|x\.ai|grok|x-preview/.test(identity)) weights.set("elon", weights.get("elon") + tokens);
      else if (/openai|codex|gpt/.test(identity)) weights.set("sam", weights.get("sam") + tokens);
    });

  const attributedTotal = [...weights.values()].reduce((sum, value) => sum + value, 0);
  return DROP_SOURCES.map((source) => ({
    ...source,
    weight: attributedTotal > 0 ? weights.get(source.key) : 1,
  })).filter((source) => source.weight > 0);
}

function randomDropSource() {
  const totalWeight = weightedDropSources.reduce((sum, source) => sum + source.weight, 0);
  let selection = Math.random() * totalWeight;
  for (const source of weightedDropSources) {
    selection -= source.weight;
    if (selection <= 0) return source;
  }
  return weightedDropSources.at(-1) || DROP_SOURCES[0];
}

function updateGoldProtocol(summary) {
  const thresholdCount = Math.floor((summary.today.total_tokens || 0) / TOKEN_STEP);
  $("#gold-count").textContent = fullNumber(thresholdCount);
  const key = `sovereign-token-center:gold-threshold:${summary.today.date}`;
  let previous = safeStoredThreshold(key);

  if (previous === null) {
    previous = Math.max(0, thresholdCount - (thresholdCount > 0 ? 1 : 0));
  } else if (previous > thresholdCount) {
    previous = thresholdCount;
  }

  const earned = Math.max(0, thresholdCount - previous);
  storeThreshold(key, thresholdCount);
  if (earned > 0) enqueueGoldDrops(earned);
}

function enqueueGoldDrops(count) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  goldQueue = Math.min(MAX_QUEUED_DROPS, goldQueue + count);
  pumpGoldDrops();
}

function pumpGoldDrops() {
  if (document.hidden || nextDropTimer || goldQueue <= 0 || activeDrops.size >= MAX_ACTIVE_DROPS) return;
  nextDropTimer = window.setTimeout(() => {
    nextDropTimer = null;
    if (goldQueue <= 0 || activeDrops.size >= MAX_ACTIVE_DROPS) return;
    goldQueue -= 1;
    spawnGoldDrop();
    pumpGoldDrops();
  }, activeDrops.size ? DROP_INTERVAL_MS : 80);
}

function spawnGoldDrop() {
  const origin = $("#drop-origin");
  const field = $("#gold-field");
  if (!origin || !field) return;

  const rect = origin.getBoundingClientRect();
  const source = randomDropSource();
  const size = Math.round(54 + Math.random() * 20);
  const startX = rect.left + rect.width / 2 - size / 2;
  const startY = rect.top + rect.height / 2 - size / 2;
  const drift = Math.round((Math.random() - 0.5) * 94);
  const endX = Math.max(8, Math.min(window.innerWidth - size - 8, startX + drift));
  const bottom = Math.round(7 + Math.random() * 11);
  const fallDistance = Math.max(40, window.innerHeight - startY - size - bottom);
  const lifetime = Math.round(DROP_LIFE_MIN_MS + Math.random() * (DROP_LIFE_MAX_MS - DROP_LIFE_MIN_MS));

  const drop = document.createElement("span");
  drop.className = `gold-drop gold-drop-${source.key} falling`;
  drop.dataset.source = source.name;
  drop.style.left = `${startX}px`;
  drop.style.top = `${startY}px`;
  drop.style.width = `${size}px`;
  drop.style.height = `${size}px`;
  drop.style.setProperty("--drift", `${drift}px`);
  drop.style.setProperty("--fall", `${fallDistance}px`);
  drop.style.setProperty("--spin", `${Math.round((Math.random() - 0.5) * 28)}deg`);
  drop.style.setProperty("--life", `${lifetime}ms`);

  const image = document.createElement("img");
  image.src = source.asset;
  image.alt = "";
  image.draggable = false;
  drop.append(image);
  field.append(drop);
  activeDrops.add(drop);

  window.setTimeout(() => {
    if (!drop.isConnected) return;
    drop.classList.remove("falling");
    drop.classList.add("landed");
    drop.style.left = `${endX}px`;
    drop.style.top = "auto";
    drop.style.bottom = `${bottom}px`;
  }, DROP_FALL_MS);

  window.setTimeout(() => {
    activeDrops.delete(drop);
    drop.remove();
    pumpGoldDrops();
  }, DROP_FALL_MS + lifetime + 250);
}

function render(summary) {
  currentSummary = summary;
  selectedDate = selectedDate && summary.days.some((day) => day.date === selectedDate)
    ? selectedDate
    : summary.range.to;
  const today = summary.today;
  weightedDropSources = sourceWeights(summary);

  $("#today-total").textContent = fullNumber(today.total_tokens);
  $("#fresh-input").textContent = tokenNumber(today.input_tokens);
  $("#cached-input").textContent = tokenNumber(today.cache_read_tokens);
  $("#output-total").textContent = tokenNumber(today.output_tokens);
  $("#reasoning-total").textContent = tokenNumber(today.reasoning_tokens);
  $("#coverage").textContent = summary.coverage === "PARTIAL"
    ? "PARTIAL COVERAGE · UNKNOWN CLIENTS VISIBLE"
    : "DISCOVERED LOCAL LEDGERS COVERED";
  $("#coverage").className = `coverage ${summary.coverage === "PARTIAL" ? "warn" : "good"}`;
  $("#range-total").textContent = tokenNumber(summary.range_total_tokens);
  $("#last-refresh").textContent = `Ledger sync ${new Date(summary.collected_at).toLocaleString()} · ${summary.refresh_seconds ?? 0}s scan`;

  renderChart(summary.days);
  renderModels(summary, selectedDate);
  renderProviders(summary.providers);
  updateGoldProtocol(summary);
}

async function load() {
  const response = await fetch("/api/summary?days=14", { cache: "no-store" });
  if (!response.ok) throw new Error("Summary unavailable");
  render(await response.json());
}

async function refreshLedgers() {
  const button = $("#refresh");
  button.disabled = true;
  button.classList.add("working");
  $(".refresh-copy").textContent = "Reading…";
  try {
    // H-3/M-1 Option A: fetch the server's per-process CSRF token over the
    // same origin, then present it on the mutating request.
    const tokenResponse = await fetch("/api/csrf-token");
    if (!tokenResponse.ok) throw new Error("Refresh failed");
    const { token } = await tokenResponse.json();
    const response = await fetch("/api/refresh", {
      method: "POST",
      headers: { "X-CSRF-Nonce": token },
    });
    if (!response.ok) throw new Error("Refresh failed");
    await load();
  } catch {
    $(".refresh-copy").textContent = "Retry";
    window.setTimeout(() => { $(".refresh-copy").textContent = "Refresh"; }, 1800);
  } finally {
    button.disabled = false;
    button.classList.remove("working");
  }
  if ($(".refresh-copy").textContent !== "Retry") $(".refresh-copy").textContent = "Refresh";
}

function updateClock() {
  $("#clock").textContent = new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date());
}

$("#refresh").addEventListener("click", refreshLedgers);
document.addEventListener("visibilitychange", () => { if (!document.hidden) pumpGoldDrops(); });
window.addEventListener("resize", () => {
  activeDrops.forEach((drop) => {
    if (drop.classList.contains("landed")) {
      const width = Number.parseFloat(drop.style.width) || 48;
      const left = Math.max(8, Math.min(window.innerWidth - width - 8, Number.parseFloat(drop.style.left) || 8));
      drop.style.left = `${left}px`;
    }
  });
});

updateClock();
window.setInterval(updateClock, 1000);
window.setInterval(() => { if (!document.hidden) load().catch(() => {}); }, SUMMARY_POLL_MS);
load().catch(() => {
  $("#coverage").textContent = "COLLECTOR UNAVAILABLE";
  $("#coverage").className = "coverage warn";
});
