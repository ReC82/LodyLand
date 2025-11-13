/*
  File: static/play.js
  Purpose: Simple "Play" UI for Lodyland (grid + player summary + inventory).
*/

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------
function baseUrl() {
  return `${location.protocol}//${location.host}`;
}

const $ = (id) => document.getElementById(id);

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

// ------------------------------------------------------------------
// State
// ------------------------------------------------------------------
let playCurrentPlayer = null;

// ------------------------------------------------------------------
// Rendu du player + XP
// ------------------------------------------------------------------
function playRenderPlayer(p) {
  const box = $("playPlayerBox");
  const nameSpan = $("playCurrentPlayerName");

  if (!p) {
    box.textContent = "No player (login via /ui).";
    nameSpan.textContent = "—";

    $("playXpFill").style.width = "0%";
    $("playXpTextLeft").textContent = "XP: 0";
    $("playXpTextRight").textContent = "0%";
    return;
  }

  playCurrentPlayer = p;
  nameSpan.textContent = p.name || "—";

  box.textContent = [
    `id=${p.id}  name=${p.name}`,
    `level=${p.level}  xp=${p.xp}`,
    `coins=${p.coins ?? 0}  diams=${p.diams ?? 0}`,
  ].join("\n");

  const xp = Number(p.xp || 0);
  const level = Number(p.level || 0);
  const next = p.next_xp ?? p.nextXp ?? null;

  let pct = 0;
  if (next !== null && next !== undefined && Number(next) > 0) {
    pct = Math.max(0, Math.min(100, Math.round((xp / Number(next)) * 100)));
  } else {
    pct = 100;
  }

  $("playXpFill").style.width = `${pct}%`;
  $("playXpTextLeft").textContent = `XP: ${xp} • Level: ${level}`;
  $("playXpTextRight").textContent = `${pct}%`;
}

// ------------------------------------------------------------------
// Inventory
// ------------------------------------------------------------------
function playRenderInventory(list) {
  const box = $("playInventoryBox");
  if (!list || !list.length) {
    box.innerHTML = `
      <div class="col">
        <div class="text-muted small">Inventaire vide.</div>
      </div>
    `;
    return;
  }

  box.innerHTML = list
    .map(
      (r) => `
      <div class="col">
        <div class="inv-card h-100">
          <div class="inv-title text-capitalize">${r.resource}</div>
          <div class="inv-qty">qty: ${r.qty}</div>
        </div>
      </div>
    `
    )
    .join("");
}

async function playRefreshInventory() {
  const res = await http("GET", "/api/inventory");
  const box = $("playInventoryBox");
  if (!res.ok) {
    box.innerHTML = `
      <div class="col">
        <div class="text-danger small">
          ERR ${res.status} — ${JSON.stringify(res.data)}
        </div>
      </div>
    `;
    return;
  }
  playRenderInventory(res.data);
}

// ------------------------------------------------------------------
// Grid de tuiles
// ------------------------------------------------------------------
function playRenderGrid(tiles) {
  const grid = $("playGridBox");
  if (!tiles || !tiles.length) {
    grid.innerHTML = `
      <div class="col">
        <div class="text-muted small">Aucune tuile débloquée.</div>
      </div>
    `;
    return;
  }

  grid.innerHTML = "";
  tiles.forEach((t) => {
    const col = document.createElement("div");
    col.className = "col";

    const cdText = t.cooldown_until
      ? new Date(t.cooldown_until).toLocaleTimeString()
      : "—";

    const disabledAttr = t.locked ? "disabled" : "";

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
          ${cdText}
        </div>

        <div class="mt-2 d-grid">
          <button
            class="btn btn-sm btn-outline-success"
            onclick="playCollect(${t.id})"
            ${disabledAttr}
          >
            Collect
          </button>
        </div>
      </div>
    `;

    grid.appendChild(col);
  });
}

async function playRefreshGrid() {
  const grid = $("playGridBox");
  if (!playCurrentPlayer) {
    grid.innerHTML = `
      <div class="col">
        <div class="text-muted small">
          No player. Va sur /ui pour t’enregistrer / te logger.
        </div>
      </div>
    `;
    return;
  }

  grid.innerHTML = `
    <div class="col">
      <div class="text-muted small">Loading tiles…</div>
    </div>
  `;

  const res = await http("GET", `/api/player/${playCurrentPlayer.id}/tiles`);
  if (!res.ok) {
    grid.innerHTML = `
      <div class="col">
        <div class="text-danger small">
          ERR ${res.status} — ${JSON.stringify(res.data)}
        </div>
      </div>
    `;
    return;
  }

  playRenderGrid(res.data);
}

// ------------------------------------------------------------------
// Collect depuis la grille
// ------------------------------------------------------------------
async function playCollect(tileId) {
  const res = await http("POST", "/api/collect", { tileId });
  if (!res.ok) {
    alert(`Collect error: ${res.status} — ${JSON.stringify(res.data)}`);
    return;
  }

  const data = res.data || {};
  // Met à jour le player (XP/coins…) s’il est renvoyé
  if (data.player) {
    playRenderPlayer({
      ...data.player,
      coins: data.player.coins ?? 0,
      diams: data.player.diams ?? 0,
      next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
    });
  } else {
    // fallback : recharger /api/me
    await playLoadPlayer();
  }

  await playRefreshInventory();
  await playRefreshGrid();
}

// ------------------------------------------------------------------
// Init : charger le player courant, inventaire, grid
// ------------------------------------------------------------------
async function playLoadPlayer() {
  const res = await http("GET", "/api/me");
  if (!res.ok) {
    playRenderPlayer(null);
    return;
  }
  playRenderPlayer(res.data);
}

document.addEventListener("DOMContentLoaded", async () => {
  await playLoadPlayer();
  await playRefreshInventory();
  await playRefreshGrid();
});
