/* ============================================================
   Mini-Game Doors — Client JS
   ============================================================ */

"use strict";

// ── State ──
let mgState = null;
let currentDoors = [];
let runInProgress = false;

// ── DOM refs ──
const _el = id => document.getElementById(id);

function showScreen(name) {
  ["loading","lobby","game","victory"].forEach(s => {
    _el(`screen-${s}`).classList.toggle("hidden", s !== name);
  });
}

// ── Fetch state ──
async function loadState() {
  showScreen("loading");
  try {
    const r = await fetch(`/api/minigame/${MG_KEY}/state`);
    if (!r.ok) {
      const text = await r.text();
      showError(`Erreur serveur ${r.status} — ${text.slice(0, 200)}`);
      return;
    }
    const data = await r.json();
    if (!data.ok) { showError(data.error); return; }
    mgState = data.state;
    applyState();
  } catch(e) {
    showError("Erreur réseau : " + e.message);
  }
}

function applyState() {
  if (!mgState) return;

  // Stat bar
  _el("mg-stock").textContent = mgState.card_stock_remaining > 0
    ? mgState.card_stock_remaining : "Épuisé";
  _el("mg-best").textContent = mgState.best_level_reached > 0
    ? `Niveau ${mgState.best_level_reached}` : "—";
  _el("mg-attempts").textContent =
    `${mgState.daily_attempts_used} / ${mgState.free_attempts_per_day} gratuit${mgState.free_attempts_per_day > 1 ? "es" : "e"}`;
  _el("mg-card-label").textContent = mgState.card_key || "—";

  // Lobby buttons
  const hasWon = mgState.has_won_card;
  const stockOk = mgState.card_stock_remaining > 0;
  const canFree = mgState.can_attempt_free;

  _el("lobby-won-notice").classList.toggle("hidden", !hasWon);
  _el("lobby-stock-empty").classList.toggle("hidden", stockOk || hasWon);
  _el("lobby-actions").classList.toggle("hidden", hasWon || !stockOk);

  if (!hasWon && stockOk) {
    _el("btn-start-free").classList.toggle("hidden", !canFree);
    const paidSection = _el("paid-section");
    paidSection.classList.toggle("hidden", canFree);
    if (!canFree) {
      _el("btn-paid-cost").textContent = mgState.extra_attempt_cost_diams;
    }
  }

  // Route to correct screen
  if (mgState.in_progress) {
    resumeRun();
  } else {
    showScreen("lobby");
  }
}

async function resumeRun() {
  try {
    const r = await fetch(`/api/minigame/${MG_KEY}/start`, { method: "POST" });
    const data = await r.json();
    if (!data.ok) { showError(data.error); return; }
    mgState = data.state;
    currentDoors = data.doors;
    renderGameScreen(data.current_level);
  } catch(e) { showError("Erreur réseau."); }
}

// ── Start attempt ──
async function startAttempt(paid = false) {
  try {
    const r = await fetch(`/api/minigame/${MG_KEY}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paid }),
    });
    const data = await r.json();
    if (!data.ok) {
      if (data.error === "no_free_attempts") {
        // Show paid section
        mgState.can_attempt_free = false;
        mgState.extra_attempt_cost_diams = data.cost_diams;
        applyState();
      } else {
        showError(data.error);
      }
      return;
    }
    mgState = data.state;
    currentDoors = data.doors;
    renderGameScreen(data.current_level);
  } catch(e) { showError("Erreur réseau."); }
}

// ── Choose door ──
async function chooseDoor(index) {
  // Disable all doors
  document.querySelectorAll(".mg-door").forEach(d => d.classList.add("disabled"));

  try {
    const r = await fetch(`/api/minigame/${MG_KEY}/choose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ door: index }),
    });
    const data = await r.json();
    if (!data.ok) { showError(data.error); return; }

    mgState = data.state;

    // Reveal chosen door
    revealDoor(index, data.outcome, data.granted);

    // Show outcome overlay
    showOutcome(data);

    if (data.next_level) {
      currentDoors = data.doors;
    }
  } catch(e) { showError("Erreur réseau."); }
}

// ── Render game screen ──
function renderGameScreen(level) {
  showScreen("game");
  _el("current-level-label").textContent = level;
  _el("progress-fill").style.width = `${(level / 10) * 100}%`;

  // Hide outcome overlay
  _el("mg-outcome").classList.add("hidden");

  // Render doors
  const container = _el("mg-doors");
  container.innerHTML = "";

  currentDoors.forEach((door, i) => {
    const el = document.createElement("div");
    el.className = "mg-door";
    el.dataset.index = i;

    el.innerHTML = `
      <div class="mg-door-number">${i + 1}</div>
      <div class="mg-door-icon">🚪</div>
      <div class="mg-door-label">Choisir</div>
    `;
    el.addEventListener("click", () => chooseDoor(i));
    container.appendChild(el);
  });
}

// ── Reveal door (animation) ──
function revealDoor(index, outcome, granted) {
  const el = document.querySelector(`.mg-door[data-index="${index}"]`);
  if (!el) return;
  el.classList.add("disabled");
  const icon = el.querySelector(".mg-door-icon");
  if (outcome === "lose") {
    el.style.borderColor = "#ef4444";
    el.style.background = "rgba(239,68,68,.15)";
    icon.textContent = "💀";
  } else if (outcome === "win_grand") {
    el.style.borderColor = "#fbbf24";
    el.style.background = "rgba(251,191,36,.2)";
    icon.textContent = "🏆";
  } else {
    el.style.borderColor = "#34d399";
    el.style.background = "rgba(52,211,153,.12)";
    icon.textContent = "🎁";
  }
}

// ── Outcome overlay ──
function showOutcome(data) {
  const { outcome, granted, run_over, won_grand, next_level, level } = data;

  if (won_grand) {
    showVictoryScreen(granted);
    return;
  }

  const overlay = _el("mg-outcome");
  overlay.className = "mg-outcome"; // reset classes

  if (outcome === "lose") {
    overlay.classList.add("outcome-lose");
    _el("outcome-icon").textContent = "💀";
    _el("outcome-title").textContent = "Défaite…";
    _el("outcome-subtitle").textContent = `Arrêté au niveau ${level}`;
    _el("outcome-rewards").innerHTML = "";
    _el("btn-outcome-next").textContent = "Retour au lobby";
  } else if (outcome === "win_stop") {
    overlay.classList.add("outcome-win");
    _el("outcome-icon").textContent = "🎁";
    _el("outcome-title").textContent = "Récompense !";
    _el("outcome-subtitle").textContent = `Niveau ${level} terminé`;
    _el("outcome-rewards").innerHTML = buildGrantedHtml(granted);
    _el("btn-outcome-next").textContent = "Retour au lobby";
  } else { // win_continue
    overlay.classList.add("outcome-continue");
    _el("outcome-icon").textContent = "⬆️";
    _el("outcome-title").textContent = `Niveau ${level} passé !`;
    _el("outcome-subtitle").textContent = "Continue ton aventure…";
    _el("outcome-rewards").innerHTML = buildGrantedHtml(granted);
    _el("btn-outcome-next").textContent = `Niveau ${next_level} →`;
  }

  overlay.classList.remove("hidden");

  _el("btn-outcome-next").onclick = () => {
    overlay.classList.add("hidden");
    if (run_over) {
      loadState();
    } else {
      renderGameScreen(next_level);
    }
  };
}

function buildGrantedHtml(granted) {
  const parts = [];
  if (granted.shards) parts.push(`<div class="granted-item">🪙 <strong>+${granted.shards}</strong> Shards</div>`);
  return parts.length ? parts.join("") : "";
}

// ── Victory screen ──
function showVictoryScreen(granted) {
  const cardBox = _el("victory-card");
  cardBox.innerHTML = "";

  if (granted.card_key) {
    const rarity = granted.card_rarity || "";
    const label = granted.card_label || granted.card_key;
    const img = granted.card_image || "";

    let imgHtml = img
      ? `<img src="/static/${img}" alt="${label}" class="victory-card-img">`
      : `<div class="victory-card-placeholder">🃏</div>`;

    cardBox.innerHTML = `
      ${imgHtml}
      <div class="victory-card-label">${label}</div>
      ${rarity ? `<div class="victory-card-rarity rarity-${rarity}">${rarity}</div>` : ""}
    `;
    cardBox.classList.remove("hidden");
    cardBox.style.cursor = "pointer";
    cardBox.title = "Voir mon inventaire";
    cardBox.onclick = () => {
      window.location.href = `/inventory`;
    };
  }

  showScreen("victory");
}

// ── Error ──
function showError(msg) {
  showScreen("lobby");
  // Show inline error instead of alert
  let errBox = document.getElementById('mg-error-box');
  if (!errBox) {
    errBox = document.createElement('div');
    errBox.id = 'mg-error-box';
    errBox.style.cssText = 'background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.4);border-radius:8px;padding:.75rem 1rem;color:#fca5a5;margin-bottom:1rem;font-size:.9rem;';
    document.getElementById('screen-lobby').prepend(errBox);
  }
  errBox.textContent = '⚠️ ' + msg;
  console.error('[minigame]', msg);
}

// ── Event bindings ──
_el("btn-start-free").addEventListener("click", () => startAttempt(false));
_el("btn-start-paid").addEventListener("click", () => startAttempt(true));
_el("btn-victory-close").addEventListener("click", () => {
  window.location.href = "/village";
});

// ── Boot ──
loadState();
