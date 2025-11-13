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

// ======================================================================
//  INVENTAIRE + VENTE (/play)
// ======================================================================

function playRenderInventory(list) {
  const box = document.getElementById("playInventoryBox");
  if (!box) return;

  if (!list || !list.length) {
    box.innerHTML = "<div class='col small text-muted'>Inventaire vide.</div>";
    return;
  }

  const html = list.map(r => `
    <div class="col">
      <div class="border rounded p-2 bg-light h-100">
        <div class="fw-semibold text-capitalize">${r.resource}</div>
        <div class="small text-muted">qty: ${r.qty}</div>
      </div>
    </div>
  `).join("");

  box.innerHTML = html;
}

async function playRefreshInventory() {
  const box = document.getElementById("playInventoryBox");
  if (!box) return;

  const res = await http("GET", "/api/inventory");
  if (!res.ok) {
    box.innerHTML =
      `<div class="col text-danger small">ERR ${res.status} — ${JSON.stringify(res.data)}</div>`;
    return;
  }
  playRenderInventory(res.data);
}

async function playSell() {
  const resSel = document.getElementById("playSellResource");
  const qtyInput = document.getElementById("playSellQty");
  const msg = document.getElementById("playSellBox");

  if (!resSel || !qtyInput || !msg) return;

  const resource = (resSel.value || "").trim();
  const qty = parseInt(qtyInput.value || "0", 10);

  if (!resource || !qty || qty <= 0) {
    msg.textContent = "Payload invalide (ressource ou quantité).";
    return;
  }

  msg.textContent = "Selling...";
  const r = await http("POST", "/api/sell", { resource, qty });

  if (!r.ok) {
    const err = r.data || {};
    msg.textContent = `ERR ${r.status} — ${err.error || "sell_failed"}`;
    return;
  }

  const data = r.data;
  msg.textContent =
    `Sold ${data.sold.qty}× ${data.sold.resource} for ${data.sold.gain} coins.`;

  // mettre à jour le player si renvoyé
  if (data.player) {
    // on protège contre undefined (comme pour coins/diams plus haut)
    playRenderPlayer({
      ...data.player,
      coins: data.player.coins ?? 0,
      diams: data.player.diams ?? 0,
      next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
    });
  }

  // Rafraîchir l’inventaire
  playRefreshInventory();
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

// ======================================================================
//  DAILY CHEST (/play)
// ======================================================================
async function playClaimDaily() {
  const btn = $("playDailyBtn");
  const box = $("playDailyBox");

  if (!btn || !box) return;

  btn.disabled = true;
  box.textContent = "Claiming...";

  const res = await http("POST", "/api/daily");

  if (!res.ok) {
    const err = res.data || {};

    if (err.error === "not_authenticated") {
      box.textContent = "Pas connecté. Va sur /ui pour te logger.";
    } else if (err.error === "already_claimed" && err.next_at) {
      const next = new Date(err.next_at);
      box.textContent =
        "Déjà réclamé. Prochain coffre: " + next.toLocaleString();
    } else {
      box.textContent =
        `ERR ${res.status} — ${JSON.stringify(res.data)}`;
    }

    btn.disabled = false;
    return;
  }

  const data = res.data || {};
  const reward = data.reward ?? 0;

  let msg = `Coffre réclamé : +${reward} coins`;
  if (data.next_at) {
    const next = new Date(data.next_at);
    msg += ` (prochain: ${next.toLocaleString()})`;
  }
  box.textContent = msg + ".";

  // Mettre à jour le player si renvoyé
  if (data.player) {
    playRenderPlayer({
      ...data.player,
      coins: data.player.coins ?? 0,
      diams: data.player.diams ?? 0,
      next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
    });
  } else {
    // fallback : recharge le player
    await playLoadPlayer();
  }

  // L'inventaire peut avoir changé (coins affichés ailleurs plus tard)
  await playRefreshInventory();

  btn.disabled = false;
}


document.addEventListener("DOMContentLoaded", async () => {
  await playLoadPlayer();
  //await playRefreshInventory();
  await playRefreshGrid();

    // bouton Refresh inventory
    const invBtn = document.getElementById("playInventoryRefreshBtn");
    if (invBtn) {
      invBtn.addEventListener("click", playRefreshInventory);
    }

    // bouton Daily Chest
    const dailyBtn = document.getElementById("playDailyBtn");
    if (dailyBtn) {
      dailyBtn.addEventListener("click", playClaimDaily);
    }    

    // bouton Sell
    const sellBtn = document.getElementById("playSellBtn");
    if (sellBtn) {
      sellBtn.addEventListener("click", playSell);
    }

    // premier chargement auto si le joueur est loggé
    playRefreshInventory();
});
