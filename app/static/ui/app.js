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

let resources = []; 

function renderResInfo() {
  const sel = $("resource");
  const info = $("resInfo");
  const btn = $("unlockBtn");
  if (!sel || !info || !btn) return;

  const key = sel.value;
  const r = resources.find(x => x.key === key);
  if (!r) {
    info.textContent = "—";
    btn.disabled = true;
    return;
  }
  info.innerHTML = `min level=${r.unlock_min_level} • cooldown=${r.base_cooldown}s • prix=${r.base_sell_price}`;

  // si on a déjà le player chargé, désactive le bouton si niveau insuffisant
  if (currentPlayer && typeof currentPlayer.level === "number") {
    btn.disabled = currentPlayer.level < r.unlock_min_level;
  } else {
    btn.disabled = false;
  }
}

async function loadResources() {
  const r = await http("GET", "/api/resources");
  if (!r.ok) return;
  resources = r.data || [];
  const sel = $("resource");
  if (!sel) return;
  sel.innerHTML = "";
  resources
    .filter(x => x.enabled)
    .forEach(it => {
      const opt = document.createElement("option");
      opt.value = it.key;
      opt.textContent = `${it.label} (lvl ${it.unlock_min_level})`;
      sel.appendChild(opt);
    });
  sel.onchange = renderResInfo;
  renderResInfo();
}

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
  // --- 1) Gestion du panneau Collect (input + bouton rouge) ---
  const input = $("tileId");
  const btn = $("collectBtn");
  if (input && btn) {
    const tileIdVal = Number((input.value || "").trim());
    if (tileIdVal && cooldowns[tileIdVal]) {
      const sec = secondsUntil(cooldowns[tileIdVal]);
      if (sec > 0) {
        btn.disabled = true;
        $("collectBox").innerHTML = `Cooldown… ${sec}s`;
      } else {
        delete cooldowns[tileIdVal];
        btn.disabled = false;
        $("collectBox").innerHTML = "Prêt à collecter.";
      }
    } else {
      btn.disabled = false;
    }
  }

  // --- 2) Gestion de la Gameplay Grid (cartes) ---
  Object.entries(cooldowns).forEach(([tileId, iso]) => {
    const sec = secondsUntil(iso);
    const card = document.querySelector(
      `.tile-card[data-tile-id="${tileId}"]`
    );
    if (!card) return;

    const cdSpan = card.querySelector(".tile-cooldown");
    const collectBtn = card.querySelector(".tile-collect-btn");

    if (sec > 0) {
      if (cdSpan) cdSpan.textContent = `${sec}s restantes`;
      if (collectBtn) collectBtn.disabled = true;
    } else {
      if (cdSpan) cdSpan.textContent = "Prêt";
      if (collectBtn) collectBtn.disabled = false;
      delete cooldowns[tileId];
    }
  });
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
    renderResInfo();
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
  refreshGrid();
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

// ======================================================================
//  Collect : depuis l'input OU depuis la grille
//    - si on appelle collect({ tileId: 123 }) → utilise cet ID
//    - sinon → lit l'input #tileId
// ======================================================================
async function collect(opts) {
  const statusEl = $("collectBox");
  const btn = $("collectBtn");

  // 1) ID éventuellement fourni par la grille
  const fromGrid = opts && typeof opts.tileId !== "undefined"
    ? opts.tileId
    : null;

  // 2) Sinon on lit l'input
  let raw = $("tileId").value.trim();
  let idFromInput = raw ? parseInt(raw, 10) : null;

  // 3) On choisit la source prioritaire : grille > input
  const tileId = fromGrid ?? idFromInput;

  if (!tileId || Number.isNaN(tileId)) {
    statusEl.textContent = "tileId manquant ou invalide.";
    return;
  }

  btn.disabled = true;
  statusEl.textContent = "Collecting...";

    try {
    const r = await http("POST", "/api/collect", { tileId });

    if (!r.ok) {
      const err = r.data || {};
      statusEl.textContent =
        `ERR ${r.status} — ${err.error || "collect_failed"}`;
      return;
    }

    const data = r.data;
    statusEl.textContent =
      `OK — next=${data.next || "?"}`;

    // 🔹 On mémorise le cooldown pour cette tuile
    if (data.next) {
      cooldowns[tileId] = data.next;
      ensureTicker();
    }

    // Mise à jour progression / inventaire
    if (data.player) {
      renderPlayer({
        ...data.player,
        next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
      });
    }
    await refreshInventory();
    await refreshGrid();  // pour que la tuile soit rafraîchie
  } catch (e) {
    console.error(e);
    statusEl.textContent = "Erreur réseau.";
  } finally {
    btn.disabled = false;
  }

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
  refreshGrid();
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
  refreshGrid();
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

async function sell() {
  const r = $("sellResource").value;
  const q = Number(($("sellQty").value || "0").trim());
  if (!r || !q) return;
  const res = await http("POST", "/api/sell", { resource: r, qty: q });
  if (!res.ok) {
    alert("Sell error: " + JSON.stringify(res.data));
    return;
  }
  // Update player + inventory
  if (res.data?.player) renderPlayer(res.data.player);
  await refreshInventory();
}

// Claim daily chest
async function claimDaily() {
  const btn = $("dailyBtn");
  const box = $("dailyBox");
  btn.disabled = true;
  box.textContent = "Claiming...";

  const r = await http("POST", "/api/daily");

  if (r.ok) {
    const d = r.data;
    const reward = d.reward ?? d.coins_awarded ?? 0;
    const streak = d.streak ?? 1;
    const best = d.best_streak ?? streak;

    box.innerHTML = `
      OK — +${reward} coins<br>
      Streak: ${streak} jour(s) • Best: ${best}
    `;

    // refresh player to reflect new coins/xp
    await refreshPlayer();
  } else {
    box.innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
  }
  btn.disabled = false;
}


async function loadGameState() {
  const r = await http("GET", "/api/state");
  const box = document.getElementById("gameStateBox");
  if (!r.ok) {
    box.textContent = "Error: " + JSON.stringify(r.data);
    return;
  }
  box.textContent = JSON.stringify(r.data, null, 2);
}

// ======================================================================
//  Gameplay Grid — Version 1 (cartes Bootstrap)
// ======================================================================
async function refreshGrid() {
  const grid = document.getElementById("gridBox");
  if (!grid) return;

  grid.innerHTML = `<div class="text-muted small">Loading...</div>`;

  // 1) récupérer le joueur courant (via cookie)
  const me = await http("GET", "/api/me");
  if (!me.ok) {
    grid.innerHTML = `<div class="text-danger small">Not logged in.</div>`;
    return;
  }

  const pid = me.data.id;

  // 2) récupérer les tiles du joueur
  const r = await http("GET", `/api/player/${pid}/tiles`);
  if (!r.ok) {
    grid.innerHTML = `<div class="text-danger small">Error loading tiles.</div>`;
    return;
  }

  const tiles = r.data || [];
  if (!tiles.length) {
    grid.innerHTML = `<div class="text-muted small">Aucune tuile débloquée.</div>`;
    return;
  }

  // 3) rendu des cartes
  grid.innerHTML = "";
    tiles.forEach(t => {
    // calcul du cooldown (version que tu as déjà, gardons-la)
    let cdText = "—";
    let onCooldown = false;

    const sourceIso = cooldowns[t.id] || t.cooldown_until || null;
    if (sourceIso) {
      const sec = secondsUntil(sourceIso);
      if (sec > 0) {
        onCooldown = true;
        cdText = `${sec}s restantes`;
        cooldowns[t.id] = sourceIso;
        ensureTicker();
      } else {
        cdText = "Prêt";
        delete cooldowns[t.id];
      }
    }

    const col = document.createElement("div");
    col.className = "col";

    col.innerHTML = `
      <div class="border rounded p-2 bg-white small text-center tile-card"
           data-tile-id="${t.id}">
        <div class="fw-semibold text-capitalize">${t.resource}</div>

        <div class="text-muted">
          ID : <span class="font-monospace">${t.id}</span>
        </div>

        <div class="text-muted">
          Locked: <strong>${t.locked ? "YES" : "NO"}</strong>
        </div>

        <div class="text-muted small">
          Cooldown:<br>
          <span class="tile-cooldown">${cdText}</span>
        </div>

        <div class="mt-2 d-grid">
          <button
            class="btn btn-sm btn-outline-success tile-collect-btn"
            onclick="collectFromGrid(${t.id})"
            ${t.locked || onCooldown ? "disabled" : ""}
          >
            Collect
          </button>
        </div>
      </div>
    `;

    grid.appendChild(col);
  });

}


// ======================================================================
//  Bouton collect depuis la grille
// ======================================================================
async function collectFromGrid(id) {
  await collect({ tileId: id });
  refreshGrid();
}


document.addEventListener("DOMContentLoaded", () => {
  loadResources();
  refreshGrid();   // <--- ajout ici !
});
