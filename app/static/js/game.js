// app/static/js/game.js

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
// Render player + XP
// ------------------------------------------------------------------
function playRenderPlayer(p) {
  const box = $("playPlayerBox");
  const nameSpan = $("playCurrentPlayerName");

  if (!p) {
    playCurrentPlayer = null;
    if (box) box.textContent = "No player (please register/login).";
    if (nameSpan) nameSpan.textContent = "—";
    const f = $("playXpFill");
    if (f) f.style.width = "0%";
    $("playXpTextLeft").textContent = "XP: 0";
    $("playXpTextRight").textContent = "0%";
    return;
  }

  playCurrentPlayer = p;
  if (nameSpan) nameSpan.textContent = p.name || "—";

  if (box) {
    box.textContent = [
      `id=${p.id}  name=${p.name}`,
      `level=${p.level}  xp=${p.xp}`,
      `coins=${p.coins ?? 0}  diams=${p.diams ?? 0}`,
    ].join("\n");
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

  const fill = $("playXpFill");
  if (fill) fill.style.width = `${pct}%`;
  $("playXpTextLeft").textContent = `XP: ${xp} • Level: ${level}`;
  $("playXpTextRight").textContent = `${pct}%`;
}

// ------------------------------------------------------------------
// Inventory
// ------------------------------------------------------------------
function playRenderInventory(list) {
  const box = $("playInventoryBox");
  if (!box) return;

  if (!list || !list.length) {
    box.innerHTML = "<div class='col small text-muted'>Inventaire vide.</div>";
    return;
  }

  const html = list
    .map(
      (r) => `
    <div class="col">
      <div class="border rounded p-2 bg-light h-100">
        <div class="fw-semibold text-capitalize">${r.resource}</div>
        <div class="small text-muted">qty: ${r.qty}</div>
      </div>
    </div>
  `
    )
    .join("");

  box.innerHTML = html;
}

async function playRefreshInventory() {
  const res = await http("GET", "/api/inventory");
  const box = $("playInventoryBox");
  if (!res.ok) {
    if (box) {
      box.innerHTML = `<div class='col text-danger small'>ERR ${res.status} — ${JSON.stringify(
        res.data
      )}</div>`;
    }
    return;
  }
  playRenderInventory(res.data);
}

// ------------------------------------------------------------------
// Tiles (grid minimal pour l’instant)
// ------------------------------------------------------------------
function playRenderGrid(tiles) {
  const grid = $("playGridBox");
  if (!grid) return;

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
          Cooldown:<br>${cdText}
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
    if (grid) {
      grid.innerHTML = `
        <div class="col">
          <div class="text-muted small">
            No player. Please register/login.
          </div>
        </div>
      `;
    }
    return;
  }

  if (grid) {
    grid.innerHTML = `
      <div class="col">
        <div class="text-muted small">Loading tiles…</div>
      </div>
    `;
  }

  const res = await http("GET", `/api/player/${playCurrentPlayer.id}/tiles`);
  if (!res.ok) {
    if (grid) {
      grid.innerHTML = `
        <div class="col">
          <div class="text-danger small">
            ERR ${res.status} — ${JSON.stringify(res.data)}
          </div>
        </div>
      `;
    }
    return;
  }

  playRenderGrid(res.data);
}

// Collect
async function playCollect(tileId) {
  const res = await http("POST", "/api/collect", { tileId });
  if (!res.ok) {
    alert(`Collect error: ${res.status} — ${JSON.stringify(res.data)}`);
    return;
  }
  const data = res.data || {};
  if (data.player) {
    playRenderPlayer({
      ...data.player,
      coins: data.player.coins ?? 0,
      diams: data.player.diams ?? 0,
      next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
    });
  } else {
    await playLoadPlayer();
  }
  await playRefreshInventory();
  await playRefreshGrid();
}

// ------------------------------------------------------------------
// Sell
// ------------------------------------------------------------------
async function playSell() {
  const resSel = $("playSellResource");
  const qtyInput = $("playSellQty");
  const msg = $("playSellBox");

  const resource = (resSel?.value || "").trim();
  const qty = parseInt(qtyInput?.value || "0", 10);

  if (!resource || !qty || qty <= 0) {
    if (msg) msg.textContent = "Payload invalide (ressource ou quantité).";
    return;
  }

  if (msg) msg.textContent = "Selling...";
  const r = await http("POST", "/api/sell", { resource, qty });

  if (!r.ok) {
    const err = r.data || {};
    if (msg) msg.textContent = `ERR ${r.status} — ${err.error || "sell_failed"}`;
    return;
  }

  const data = r.data;
  if (msg) {
    msg.textContent = `Sold ${data.sold.qty}× ${data.sold.resource} for ${data.sold.gain} coins.`;
  }

  if (data.player) {
    playRenderPlayer({
      ...data.player,
      coins: data.player.coins ?? 0,
      diams: data.player.diams ?? 0,
      next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
    });
  }

  playRefreshInventory();
}

// ------------------------------------------------------------------
// Auth : register / login / logout
// ------------------------------------------------------------------
async function playRegister() {
  const nameInput = $("playNameInput");
  const authBox = $("playAuthBox");
  const name = (nameInput?.value || "").trim() || "player1";

  if (authBox) authBox.textContent = "Registering...";
  const r = await http("POST", "/api/register", { name });

  if (!r.ok) {
    if (authBox) authBox.textContent = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }

  if (authBox) authBox.textContent = `Registered as ${r.data.name} (id=${r.data.id})`;
  playRenderPlayer(r.data);
  await playRefreshInventory();
  await playRefreshGrid();
}

async function playLogin() {
  const nameInput = $("playNameInput");
  const authBox = $("playAuthBox");
  const name = (nameInput?.value || "").trim() || "player1";

  if (authBox) authBox.textContent = "Logging in...";
  const r = await http("POST", "/api/login", { name });

  if (!r.ok) {
    if (authBox) authBox.textContent = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }

  if (authBox) authBox.textContent = `Logged as ${r.data.name} (id=${r.data.id})`;
  playRenderPlayer(r.data);
  await playRefreshInventory();
  await playRefreshGrid();
}

async function playLogout() {
  const authBox = $("playAuthBox");

  if (authBox) authBox.textContent = "Logging out...";
  const r = await http("POST", "/api/logout", {});

  if (!r.ok) {
    if (authBox) authBox.textContent = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }

  if (authBox) authBox.textContent = "Logged out.";
  playRenderPlayer(null);

  const inv = $("playInventoryBox");
  const grid = $("playGridBox");
  if (inv) inv.innerHTML = "<div class='col small text-muted'>Inventaire vide.</div>";
  if (grid) {
    grid.innerHTML = `
      <div class="col">
        <div class="text-muted small">
          No player. Please register/login.
        </div>
      </div>
    `;
  }
}

// ------------------------------------------------------------------
// Init
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
  await playRefreshGrid();
  playRefreshInventory();

  const invBtn = $("playInventoryRefreshBtn");
  if (invBtn) invBtn.addEventListener("click", playRefreshInventory);

  const sellBtn = $("playSellBtn");
  if (sellBtn) sellBtn.addEventListener("click", playSell);

  const regBtn = $("playRegisterBtn");
  const loginBtn = $("playLoginBtn");
  const logoutBtn = $("playLogoutBtn");

  if (regBtn) regBtn.addEventListener("click", playRegister);
  if (loginBtn) loginBtn.addEventListener("click", playLogin);
  if (logoutBtn) logoutBtn.addEventListener("click", playLogout);
});
