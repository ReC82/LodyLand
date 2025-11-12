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

// ---- Generic helpers --------------------------------------------------------
async function http(method, path, body) {
  const res = await fetch(`${baseUrl()}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
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
  if (!p) {
    $("playerBox").innerHTML = "Aucun player.";
    $("progressBox").innerHTML = "";
    return;
  }
  $("playerBox").innerHTML = `
    id=${p.id}  name=${p.name}
    level=${p.level}  xp=${p.xp}  coins=${p.coins}  diams=${p.diams}
  `.trim();

  const next = p.next_xp ?? p.nextXp ?? null; // tolerate both keys if present
  let html = `
    <div class="pill">Level: <b>${p.level}</b></div>
    <div class="pill">XP: <b>${p.xp}</b></div>
  `;
  if (next !== null && next !== undefined) {
    const pct = Math.max(0, Math.min(100, Math.round((p.xp / next) * 100)));
    html += `<div class="pill">Next threshold: <b>${next} XP</b> (~${pct}%)</div>`;
  } else {
    html += `<div class="pill">Max level for demo thresholds</div>`;
  }
  $("progressBox").innerHTML = html;
}

function renderTiles(list) {
  if (!list || !list.length) {
    $("tilesBox").innerHTML = "Aucune tuile.";
    return;
  }
  $("tilesBox").innerHTML = list.map(t =>
    `#${t.id}  res=${t.resource}  locked=${t.locked}  cooldown=${t.cooldown_until ?? "-"}`
  ).join("\n");
}

function renderCollect(resp) {
  if (!resp) return;
  if (resp.ok) {
    const lu = resp.level_up ? " (LEVEL UP 🎉)" : "";
    $("collectBox").innerHTML = `OK — next=${resp.next}${lu}`;
    if (resp.player) {
      // Attach next_xp if API returns it
      renderPlayer({
        ...resp.player,
        next_xp: resp.player.next_xp ?? resp.player.nextXp ?? null,
      });
    }
  } else {
    $("collectBox").innerHTML = `ERR ${resp.status} — ${JSON.stringify(resp.data)}`;
  }
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
  if (!currentPlayer) {
    $("playerBox").innerHTML = "Pas de player en mémoire. Crée d'abord un player.";
    return;
  }
  const r = await http("GET", `/api/player/${currentPlayer.id}`);
  if (!r.ok) {
    $("playerBox").innerHTML = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }
  currentPlayer = r.data;
  renderPlayer(currentPlayer);
}

async function unlockTile() {
  if (!currentPlayer) {
    $("tilesBox").innerHTML = "Crée d'abord un player.";
    return;
  }
  const resource = $("resource").value;
  const r = await http("POST", "/api/tiles/unlock", {
    playerId: currentPlayer.id, resource
  });
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
  const tileId = Number(($("tileId").value || "").trim());
  if (!tileId) {
    $("collectBox").innerHTML = "Renseigne un tileId (ex: 1).";
    return;
  }
  const r = await http("POST", "/api/collect", { tileId });
  renderCollect(r);
}
