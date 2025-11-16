/*
  File: static/GAME_UI/js/game_app.js
  Purpose: Main game UI logic (grid + inventory).
  Notes:
  - Uses same API endpoints as dev_app.js (/api/me, /api/collect, etc.)
*/

let currentPlayer = null;
const cooldowns = {};
let tickInterval = null;
let cardShopLoaded = false;

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
  data = isJson ? await res.json() : await res.text();

  return { ok: res.ok, status: res.status, data };
}

// ---------------------------------------------------------------------------
// Helpers cooldown
// ---------------------------------------------------------------------------
function secondsUntil(iso) {
  if (!iso) return 0;
  const end = new Date(iso).getTime();
  const now = Date.now();
  return Math.max(0, Math.ceil((end - now) / 1000));
}

function ensureTicker() {
  if (tickInterval) return;
  tickInterval = setInterval(updateCooldownUI, 1000);
}

function updateCooldownUI() {
  Object.entries(cooldowns).forEach(([tileId, iso]) => {
    const sec = secondsUntil(iso);
    const card = document.querySelector(`.game-tile[data-tile-id="${tileId}"]`);
    if (!card) return;

    const cdSpan = card.querySelector(".tile-cooldown");
    const btn = card.querySelector(".tile-collect-btn");

    if (sec > 0) {
      if (cdSpan) cdSpan.textContent = `${sec}s`;
      if (btn) btn.disabled = true;
    } else {
      if (cdSpan) cdSpan.textContent = "Prêt";
      if (btn) btn.disabled = card.dataset.locked === "true";
      delete cooldowns[tileId];
    }
  });
}

// ---------------------------------------------------------------------------
// Player rendering
// ---------------------------------------------------------------------------
function renderPlayer(p) {
  const header = $("playerHeader");
  const xpBar = $("xpBar");
  const xpLeft = $("xpLabelLeft");
  const xpRight = $("xpLabelRight");
  const headerName = $("currentPlayerName");

  if (!p) {
    if (header) header.textContent = "Aucun joueur (clique sur \"Commencer\").";
    if (xpBar) xpBar.style.width = "0%";
    if (xpLeft) xpLeft.textContent = "XP: 0 • Level: 0";
    if (xpRight) xpRight.textContent = "0%";
    if (headerName) headerName.textContent = "—";
    return;
  }

  if (header) {
    header.textContent = `id=${p.id} • ${p.name} • lvl=${p.level} • XP=${p.xp} • coins=${p.coins}`;
  }

  const xp = Number(p.xp || 0);
  const level = Number(p.level || 0);
  const next = p.next_xp ?? p.nextXp ?? null;

  let pct = 0;
  if (next !== null && next !== undefined && Number(next) > 0) {
    pct = Math.max(0, Math.min(100, Math.round((xp / Number(next)) * 100)));
  } else {
    pct = 100;
  }

  if (xpBar) xpBar.style.width = `${pct}%`;
  if (xpLeft) xpLeft.textContent = `XP: ${xp} • Level: ${level}`;
  if (xpRight) xpRight.textContent = `${pct}%`;
  if (headerName) headerName.textContent = p.name ?? "—";
}

// ---------------------------------------------------------------------------
// Inventory rendering
// ---------------------------------------------------------------------------
function renderInventory(list) {
  const box = $("inventoryBox");
  if (!box) return;

  if (!list || !list.length) {
    box.innerHTML = `
      <div class="col">
        <div class="border border-secondary rounded-3 p-2 small text-muted h-100 d-flex align-items-center justify-content-center">
          Inventaire vide.
        </div>
      </div>`;
    return;
  }

  const html = list.map((r) => {
    return `
      <div class="col">
        <div class="border border-secondary rounded-3 p-2 h-100 d-flex flex-column justify-content-between">
          <div class="small text-uppercase fw-semibold">${r.resource}</div>
          <div class="small">qty: ${r.qty}</div>
        </div>
      </div>`;
  }).join("");

  box.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Grid rendering
// ---------------------------------------------------------------------------
function tileIconUrl(t) {
  // Icon field from API (DB). Might be:
  // - "branch.png"
  // - "static/img/resources/branch.png"
  // - "/static/img/resources/branch.png"
  const raw = t.icon || "default.png";

  // 1) Already an absolute path like "/static/..."
  if (raw.startsWith("/")) {
    return raw;
  }

  // 2) Starts with "static/..." (relative)
  if (raw.startsWith("static/")) {
    return "/" + raw;
  }

  // 3) Just a filename: we assume it's inside our resources folder
  return `/static/assets/img/resources/${raw}`;
}

function renderGrid(tiles) {
  const grid = $("gridBox");
  if (!grid) return;

  if (!tiles || !tiles.length) {
    grid.innerHTML = `
      <div class="col">
        <div class="border border-secondary rounded-3 p-3 text-center small text-muted">
          Aucune tuile débloquée pour l'instant.
        </div>
      </div>`;
    return;
  }

  const now = Date.now();
  grid.innerHTML = "";

  tiles.forEach((t) => {
    let cdText = "—";
    let onCooldown = false;

    const sourceIso = cooldowns[t.id] || t.cooldown_until || null;
    if (sourceIso) {
      const msEnd = new Date(sourceIso).getTime();
      const diff = Math.ceil((msEnd - now) / 1000);
      if (diff > 0) {
        onCooldown = true;
        cdText = `${diff}s`;
        cooldowns[t.id] = sourceIso;
        ensureTicker();
      } else {
        cdText = "Prêt";
        delete cooldowns[t.id];
      }
    } else {
      cdText = "Prêt";
    }

    const locked = !!t.locked;

    const col = document.createElement("div");
    col.className = "col";

    col.innerHTML = `
      <div class="game-tile border border-secondary rounded-3 p-2 text-center h-100 bg-dark-subtle"
           data-tile-id="${t.id}"
           data-locked="${locked}">
        <div class="mb-2">
          <img src="${tileIconUrl(t)}"
               alt="${t.resource}"
               class="img-fluid"
               style="image-rendering: pixelated; max-height: 48px;">
        </div>
        <div class="small text-uppercase fw-semibold">${t.resource}</div>
        <div class="small text-muted">ID: ${t.id}</div>
        <div class="small ${locked ? "text-danger" : "text-success"}">
          ${locked ? "Locked" : "Unlocked"}
        </div>
        <div class="small text-info">
          Cooldown: <span class="tile-cooldown">${cdText}</span>
        </div>
        <div class="d-grid mt-2">
          <button
            class="btn btn-sm btn-success tile-collect-btn"
            ${locked || onCooldown ? "disabled" : ""}
            onclick="collectFromTile(${t.id})"
          >
            Collect
          </button>
        </div>
      </div>
    `;

    grid.appendChild(col);
  });
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------
async function refreshInventory() {
  const r = await http("GET", "/api/inventory");
  if (!r.ok) {
    console.error("inventory error", r);
    renderInventory([]);
    return;
  }
  renderInventory(r.data);
}

async function refreshGrid() {
  const gridStatus = $("gridStatus");
  if (!currentPlayer) {
    if (gridStatus) gridStatus.textContent = "Pas de joueur connecté.";
    renderGrid([]);
    return;
  }

  if (gridStatus) gridStatus.textContent = "Chargement des tuiles...";

  const r = await http("GET", `/api/player/${currentPlayer.id}/tiles`);
  if (!r.ok) {
    console.error("tiles error", r);
    if (gridStatus)
      gridStatus.textContent = `Erreur chargement des tuiles (${r.status})`;
    renderGrid([]);
    return;
  }

  renderGrid(r.data);
  if (gridStatus) gridStatus.textContent = "Clique sur une tuile pour récolter.";
}

async function collectFromTile(tileId) {
  const status = $("gridStatus");
  if (status) status.textContent = "Collect en cours...";

  const r = await http("POST", "/api/collect", { tileId });

  if (!r.ok) {
    const err = r.data || {};
    if (status) status.textContent =
      `Erreur collect (${r.status}) : ${err.error || "collect_failed"}`;
    return;
  }

  const data = r.data;
  if (data.next) {
    cooldowns[tileId] = data.next;
    ensureTicker();
  }

  if (data.player) {
    renderPlayer({
      ...data.player,
      next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
    });
  }

  await refreshInventory();
  await refreshGrid();
}

// ---------------------------------------------------------------------------
// Auth / start game
// ---------------------------------------------------------------------------
async function tryMe() {
  const r = await http("GET", "/api/me");
  if (!r.ok) return null;
  return r.data;
}

async function registerPlayer(name) {
  const r = await http("POST", "/api/register", { name });
  if (!r.ok) {
    console.error("register error", r);
    return null;
  }
  return r.data;
}

async function startGame() {
  const input = $("playerName");
  const baseName = (input?.value || "Farmer").trim() || "Farmer";
  const name = `${baseName}`;

  let p = await registerPlayer(name);
  if (!p) {
    // Try fallback: maybe already exists -> login
    const r = await http("POST", "/api/login", { name });
    if (!r.ok) {
      alert("Impossible de créer/login le joueur.");
      return;
    }
    p = r.data;
  }

  currentPlayer = p;
  renderPlayer(currentPlayer);
  await refreshInventory();
  await refreshGrid();
  await loadCardShop(); 
}

// ---------------------------------------------------------------------------
// Card Shop rendering
// ---------------------------------------------------------------------------
function renderCardShop(cards) {
  const box = $("cardShopBox");
  const status = $("cardShopStatus");
  if (!box) return;

  if (!currentPlayer) {
    box.innerHTML = `
      <div class="col">
        <div class="border border-secondary rounded-3 p-3 small text-muted text-center">
          Connecte-toi d'abord pour voir les cartes.
        </div>
      </div>`;
    if (status) status.textContent = "Aucun joueur connecté.";
    return;
  }

  if (!cards || !cards.length) {
    box.innerHTML = `
      <div class="col">
        <div class="border border-secondary rounded-3 p-3 small text-muted text-center">
          Aucune carte disponible pour l'instant.
        </div>
      </div>`;
    if (status) status.textContent = "Shop vide.";
    return;
  }

  const html = cards.map((c) => {
    const priceParts = [];
    if (c.price_coins > 0) priceParts.push(`${c.price_coins} coins`);
    if (c.price_diams > 0) priceParts.push(`${c.price_diams} diams`);
    const priceText = priceParts.length ? priceParts.join(" + ") : "Gratuit";

    const owned = c.owned_qty || 0;
    const maxOwned = c.max_owned;
    const isMaxed = maxOwned !== null && maxOwned !== undefined && owned >= maxOwned;

    const typeLabel =
      c.type === "resource_boost"
        ? `Boost ${c.target_resource || "resource"}`
        : c.type || "Card";

    // If icon is a full path, reuse it, else nothing (no fallback icon here)
    const iconSrc = c.icon && c.icon.startsWith("/")
      ? c.icon
      : (c.icon || "");

    return `
      <div class="col">
        <div class="border border-secondary rounded-3 p-3 h-100 d-flex flex-column bg-dark-subtle">
          <div class="d-flex align-items-center mb-2">
            ${iconSrc
              ? `<img src="${iconSrc}" alt="${c.label}"
                      style="width:32px;height:32px;image-rendering:pixelated;"
                      class="me-2">`
              : ""
            }
            <div>
              <div class="small fw-semibold">${c.label}</div>
              <div class="small text-muted">${typeLabel}</div>
            </div>
          </div>

          <div class="small flex-grow-1 mb-2">
            ${c.description || ""}
          </div>

          <div class="small mb-2">
            Prix : <strong>${priceText}</strong><br>
            Possédées : <strong>${owned}</strong>${maxOwned ? ` / ${maxOwned}` : ""}
          </div>

          <div class="d-grid">
            <button
              class="btn btn-sm btn-primary"
              ${isMaxed ? "disabled" : ""}
              onclick="buyCard('${c.key}')"
            >
              ${isMaxed ? "Max" : "Acheter"}
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");

  box.innerHTML = html;
  if (status) status.textContent = "Clique sur une carte pour l'acheter.";
}

// ---------------------------------------------------------------------------
// Card Shop loading & actions
// ---------------------------------------------------------------------------
async function loadCardShop() {
  const box = $("cardShopBox");
  const status = $("cardShopStatus");

  if (!box) return;

  if (!currentPlayer) {
    // No player -> just render empty state
    renderCardShop([]);
    return;
  }

  if (status) status.textContent = "Chargement du shop...";

  const r = await http("GET", `/api/cards?playerId=${currentPlayer.id}`);

  if (!r.ok) {
    console.error("Error loading card shop", r);
    box.innerHTML = `
      <div class="col">
        <div class="border border-danger rounded-3 p-3 small text-danger text-center">
          Erreur chargement shop (${r.status})
        </div>
      </div>`;
    if (status) status.textContent = "Erreur lors du chargement du shop.";
    return;
  }

  const cards = r.data || [];
  renderCardShop(cards);
  cardShopLoaded = true;
}

async function buyCard(cardKey) {
  const status = $("cardShopStatus");

  if (!currentPlayer) {
    if (status) status.textContent = "Connecte-toi d'abord.";
    return;
  }

  if (status) status.textContent = "Achat en cours...";

  const body = {
    card_key: cardKey,
    playerId: currentPlayer.id,
  };

  const r = await http("POST", "/api/cards/buy", body);

  if (!r.ok) {
    console.error("Buy card error", r);
    const d = r.data || {};
    const err = d.error || "buy_failed";
    if (status) status.textContent = `Erreur : ${err}`;
    return;
  }

  const d = r.data || {};
  if (status) status.textContent = `Achat réussi : ${d.card?.label || cardKey}`;

  // refresh player coins/diams + shop
  if (d.player) {
    renderPlayer({
      ...currentPlayer,
      coins: d.player.coins,
      diams: d.player.diams,
    });
    currentPlayer.coins = d.player.coins;
    currentPlayer.diams = d.player.diams;
  }

  await loadCardShop();
}
  

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  // Try to reuse existing player via cookie
  const me = await tryMe();
  if (me) {
    currentPlayer = me;
    renderPlayer(currentPlayer);
    await refreshInventory();
    await refreshGrid();
    await loadCardShop();  
  } else {
    renderPlayer(null);
    renderCardShop([]); 
    // On attend que l'utilisateur clique sur "Commencer"
  }
});
