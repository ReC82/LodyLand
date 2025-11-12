/*
  File: static/ui/app.js
  Purpose: Small helper script to drive the Debug UI.
  Notes:
  - All fetch calls are same-origin (no CORS).
  - Simple, framework-free ES6 for clarity.
*/

/** Returns base URL from the current location (e.g., http://127.0.0.1:8000) */
function baseUrl() {
  return `${location.protocol}//${location.host}`;
}

const $ = (id) => document.getElementById(id);
const serverUrlEl = $("serverUrl");
serverUrlEl.textContent = baseUrl();

let currentPlayer = null;

// Cooldown trackers keyed by tileId -> ISO date string
const cooldowns = {};
let tickInterval = null;

// -- after const $ = ... and serverUrlEl...
const playerNameEl = $("currentPlayerName");

// Update current player name in navbar
function setCurrentPlayerName(p) {
  playerNameEl.textContent = p?.name ?? "—";
}

function secondsUntil(iso) {
  if (!iso) return 0;
  const end = new Date(iso).getTime();
  const now = Date.now();
  return Math.max(0, Math.ceil((end - now) / 1000));
}

function ensureTicker() {
  if (tickInterval) return;
  tickInterval = setInterval(updateCountdownUI, 1000);
}

function updateCountdownUI() {
  // Update the Collect panel button state
  const input = $("tileId");
  if (!input) return;
  const tileIdVal = Number((input.value || "").trim());
  const btn = $("collectBtn");
  if (tileIdVal && cooldowns[tileIdVal]) {
    const sec = secondsUntil(cooldowns[tileIdVal]);
    if (sec > 0) {
      btn.disabled = true;
      $("collectBox").innerHTML = `Cooldown… ${sec}s`;
    } else {
      delete cooldowns[tileIdVal];
      btn.disabled = false;
      $("collectBox").innerHTML = "Prêt à collecter.";
      // Optionnel: refresh tiles pour refléter cooldown_until nul
      refreshTiles();
    }
  } else {
    btn.disabled = false;
  }

  // Met à jour l’affichage des tiles (temps restant)
  // (léger: on ne refait pas un fetch, on re-rendera sur prochain refreshTiles)
}

// ---- Generic helpers --------------------------------------------------------
async function http(method, path, body) {
  const res = await fetch(`${baseUrl()}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",               // <-- important pour cookies
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

  function renderPlayer(p) {
    // Render basic player info
    if (!p) {
      $("playerBox").innerHTML = "Aucun player.";
      $("progressTextLeft").textContent = "XP: 0";
      $("progressTextRight").textContent = "0%";
      $("progressFill").style.width = "0%";
      return;
    }

    $("playerBox").innerHTML = `
      id=${p.id}  name=${p.name}
      level=${p.level}  xp=${p.xp}  coins=${p.coins}  diams=${p.diams}
    `.trim();

    // Compute percentage towards next level
    // next_xp is the threshold value to reach the next level (absolute XP)
    const next = p.next_xp ?? p.nextXp ?? null;

    // Safety: ensure numeric XP/level
    const xp = Number(p.xp || 0);
    const level = Number(p.level || 0);

    let pct = 0;
    // If next is present and > 0, compute ratio; else consider "max" (100%)
    if (next !== null && next !== undefined && Number(next) > 0) {
      pct = Math.max(0, Math.min(100, Math.round((xp / Number(next)) * 100)));
    } else {
      pct = 100; // max level
    }

    // Update progress bar visuals
    $("progressFill").style.width = `${pct}%`;
    $("progressTextLeft").textContent = `XP: ${xp}  •  Level: ${level}`;
    $("progressTextRight").textContent = `${pct}%`;

    setCurrentPlayerName(p);
  }

function renderTiles(list) {
  if (!list || !list.length) {
    $("tilesBox").innerHTML = "Aucune tuile.";
    return;
  }
  const lines = list.map(t => {
    let cd = "-";
    if (t.cooldown_until) {
      const sec = secondsUntil(t.cooldown_until);
      if (sec > 0) {
        cd = `${sec}s`;
        // garde en mémoire pour ce tile
        cooldowns[t.id] = t.cooldown_until;
        ensureTicker();
      } else {
        cd = "-";
        delete cooldowns[t.id];
      }
    }
    return `#${t.id}  res=${t.resource}  locked=${t.locked}  cooldown=${cd}`;
  });
  $("tilesBox").innerHTML = lines.join("\n");
}


function renderCollect(r) {
  const btn = $("collectBtn");

  // Network/HTTP error
  if (!r || !r.ok) {
    $("collectBox").innerHTML = `ERR ${r?.status} — ${JSON.stringify(r?.data)}`;
    btn.disabled = false;
    return;
  }

  const d = r.data; // <-- This is your API JSON (ok, next, player, level_up, ...)
  if (!d || !d.ok) {
    $("collectBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    btn.disabled = false;
    return;
  }

  const lu = d.level_up ? " (LEVEL UP 🎉)" : "";
  $("collectBox").innerHTML = `OK — next=${d.next ?? "-"}`;

  // Start cooldown timer only if backend sent a next time
  const input = $("tileId");
  const tileIdVal = Number((input?.value || "").trim());
  if (tileIdVal && d.next) {
    cooldowns[tileIdVal] = d.next;   // <-- store ISO until
    ensureTicker();                  // <-- start 1s interval if not running
    btn.disabled = true;             // lock button during cooldown
  } else {
    // if no cooldown returned, re-enable the button
    btn.disabled = false;
  }

  // Update player (progress bar will refresh here)
  if (d.player) {
    renderPlayer({
      ...d.player,
      next_xp: d.player.next_xp ?? d.player.nextXp ?? null,
    });
  }

  // Live refresh lists
  refreshInventory();
  refreshTiles();
}


function renderInventory(list) {
  if (!list || !list.length) {
    $("inventoryBox").innerHTML = "<div class='text-muted small'>Inventaire vide.</div>";
    return;
  }
  const html = list.map(r => `
    <div class="col">
      <div class="inv-card h-100">
        <div class="inv-title text-capitalize">${r.resource}</div>
        <div class="inv-qty">qty: ${r.qty}</div>
      </div>
    </div>
  `).join("");
  $("inventoryBox").innerHTML = html;
}


async function refreshInventory() {
  const r = await http("GET", "/api/inventory");
  if (!r.ok) {
    $("inventoryBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }
  renderInventory(r.data);
}


// ---- Actions ----------------------------------------------------------------
async function createPlayer() {
  const name = $("playerName").value || "player1";
  const r = await http("POST", "/api/player", { name });
  if (!r.ok) {
    $("playerBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }
  currentPlayer = r.data;
  renderPlayer(currentPlayer);
}

async function refreshPlayer() {
  const r = await http("GET", `/api/me`);
  if (!r.ok) {
    $("playerBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }
  currentPlayer = r.data;
  renderPlayer(currentPlayer);
}

async function unlockTile() {
  if (!currentPlayer) {
    $("tilesBox").innerHTML = "Crée ou login d'abord un player.";
    return;
  }
  const resource = $("resource").value;
  const r = await http("POST", "/api/tiles/unlock", { resource }); // <-- sans playerId
  if (!r.ok) {
    $("tilesBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }
  await refreshTiles();
}

async function refreshTiles() {
  if (!currentPlayer) {
    $("tilesBox").innerHTML = "Crée d'abord un player.";
    return;
  }
  const r = await http("GET", `/api/player/${currentPlayer.id}/tiles`);
  if (!r.ok) {
    $("tilesBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }
  renderTiles(r.data);
}

async function collect() {
  const input = $("tileId");  // <-- important
  if (!input) {
    console.warn("Input #tileId not found in DOM.");
    return;
  }
  const tileId = Number((input.value || "").trim());
  if (!tileId) {
    $("collectBox").innerHTML = "Renseigne un tileId (ex: 1).";
    return;
  }
  if (cooldowns[tileId] && secondsUntil(cooldowns[tileId]) > 0) {
    $("collectBox").innerHTML = `Cooldown… ${secondsUntil(cooldowns[tileId])}s`;
    $("collectBtn").disabled = true;
    return;
  }
  $("collectBtn").disabled = true;

  const r = await http("POST", "/api/collect", { tileId });
  if (r.status === 409) {
    $("collectBox").innerHTML = "⚠️ Action déjà effectuée ou en conflit.";
    $("collectBtn").disabled = false;
    return;
  }
  renderCollect(r);
}

async function register() {
  const name = $("playerName").value || "player1";
  const r = await http("POST", "/api/register", { name });
  if (!r.ok) {
    $("authBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }
  currentPlayer = r.data;
  $("authBox").innerHTML = `Connecté en cookie: id=${currentPlayer.id}`;
  renderPlayer(currentPlayer);
  await refreshInventory();
  
}

async function login() {
  const name = $("playerName").value || "player1";
  const r = await http("POST", "/api/login", { name });
  if (!r.ok) {
    $("authBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }
  currentPlayer = r.data;
  $("authBox").innerHTML = `Connecté en cookie: id=${currentPlayer.id}`;
  renderPlayer(currentPlayer);
  await refreshInventory();
}

async function logout() {
  const r = await http("POST", "/api/logout");
  if (!r.ok) {
    $("authBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }
  currentPlayer = null;
  $("authBox").innerHTML = "Déconnecté.";
  renderPlayer(null);
}



