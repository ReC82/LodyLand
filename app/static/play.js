/*
  File: static/play.js
  Purpose: Minimal “play” UI using existing API:
   - /api/me
   - /api/player/<id>/tiles
   - /api/collect
*/

function baseUrl() {
  return `${location.protocol}//${location.host}`;
}
const $ = (id) => document.getElementById(id);

let playCurrentPlayer = null;

async function http(method, path, body) {
  const res = await fetch(`${baseUrl()}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  const isJson = res.headers.get("content-type")?.includes("application/json");
  if (isJson) {
    data = await res.json();
  } else {
    data = await res.text();
  }
  return { ok: res.ok, status: res.status, data };
}

// ---------------------------------------------------------------------------
// Player
// ---------------------------------------------------------------------------
function renderPlayPlayer(p) {
  const box = $("playPlayerBox");
  const nameEl = $("playCurrentPlayerName");

  if (!p) {
    box.textContent = "Pas de joueur connecté (utilise /ui pour register/login).";
    nameEl.textContent = "—";
    return;
  }

  nameEl.textContent = p.name;
  box.innerHTML = `
    <div><strong>${p.name}</strong></div>
    <div class="text-muted">
      Niveau: ${p.level} • XP: ${p.xp} • Coins: ${p.coins} • Diams: ${p.diams}
    </div>
  `;
}

async function loadPlayPlayer() {
  const r = await http("GET", "/api/me");
  if (!r.ok) {
    renderPlayPlayer(null);
    return null;
  }
  playCurrentPlayer = r.data;
  renderPlayPlayer(playCurrentPlayer);
  return playCurrentPlayer;
}

// ---------------------------------------------------------------------------
// Tiles
// ---------------------------------------------------------------------------
function renderPlayTiles(tiles) {
  const grid = $("playTilesGrid");
  const status = $("playTilesStatus");

  if (!tiles || !tiles.length) {
    status.textContent = "Aucune tuile (utilise /ui pour débloquer quelques tuiles).";
    grid.innerHTML = "";
    return;
  }

  status.textContent = `${tiles.length} tuile(s)`;

  grid.innerHTML = "";

  tiles.forEach(t => {
    const col = document.createElement("div");
    col.className = "col";

    const cooldownText = t.cooldown_until ? t.cooldown_until : "—";

    col.innerHTML = `
      <div class="border rounded p-2 bg-white small text-center">
        <div class="fw-semibold text-capitalize">${t.resource}</div>
        <div class="text-muted">
          ID: <span class="font-monospace">${t.id}</span>
        </div>
        <div class="text-muted">
          Locked: <strong>${t.locked ? "YES" : "NO"}</strong>
        </div>
        <div class="text-muted small">
          Cooldown:<br>
          ${cooldownText}
        </div>
        <div class="mt-2 d-grid">
          <button
            class="btn btn-sm btn-outline-success"
            onclick="playCollect(${t.id})"
            ${t.locked ? "disabled" : ""}
          >
            Collect
          </button>
        </div>
      </div>
    `;

    grid.appendChild(col);
  });
}

async function loadPlayTiles() {
  const status = $("playTilesStatus");
  const grid = $("playTilesGrid");
  grid.innerHTML = "";
  status.textContent = "Chargement des tuiles...";

  if (!playCurrentPlayer) {
    status.textContent = "Pas de joueur (va sur /ui pour login/register).";
    return;
  }

  const r = await http("GET", `/api/player/${playCurrentPlayer.id}/tiles`);
  if (!r.ok) {
    status.textContent = `Erreur: ${r.status}`;
    return;
  }

  renderPlayTiles(r.data);
}

// ---------------------------------------------------------------------------
// Collect
// ---------------------------------------------------------------------------
async function playCollect(tileId) {
  const status = $("playTilesStatus");
  status.textContent = `Collecting tile #${tileId}...`;

  const r = await http("POST", "/api/collect", { tileId });
  if (!r.ok) {
    const err = r.data || {};
    status.textContent = `ERR ${r.status} — ${err.error || "collect_failed"}`;
    return;
  }

  const data = r.data;
  status.textContent = `OK — next=${data.next || "?"}`;

  // Mettre à jour le joueur si renvoyé
  if (data.player) {
    playCurrentPlayer = data.player;
    renderPlayPlayer(playCurrentPlayer);
  }

  // Recharger la grille
  await loadPlayTiles();
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  const p = await loadPlayPlayer();
  if (p) {
    await loadPlayTiles();
  }
});

// Expose à window pour onclick inline
window.playCollect = playCollect;
