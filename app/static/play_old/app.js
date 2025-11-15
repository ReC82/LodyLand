/*
  File: static/play/app.js
  Purpose: Logique minimaliste pour la page /play
  - Register / Login / Logout via l’API existante
  - Affichage du joueur courant
*/

function baseUrl() {
  return `${location.protocol}//${location.host}`;
}

const $ = (id) => document.getElementById(id);

let playCurrentPlayer = null;

// ---------------------------------------------------------------------------
// Helpers HTTP
// ---------------------------------------------------------------------------
async function http(method, path, body) {
  const res = await fetch(`${baseUrl()}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  const ct = res.headers.get("content-type");
  if (ct && ct.includes("application/json")) {
    data = await res.json();
  } else {
    data = await res.text();
  }

  return { ok: res.ok, status: res.status, data };
}

// ---------------------------------------------------------------------------
// Rendu du joueur
// ---------------------------------------------------------------------------
function renderPlayPlayer(p) {
  const box = $("playPlayerBox");
  const nameSpan = $("playCurrentPlayerName");

  if (!p) {
    box.textContent = "Aucun joueur chargé.";
    nameSpan.textContent = "—";
    return;
  }

  box.textContent = [
    `id=${p.id}`,
    `name=${p.name}`,
    `level=${p.level}`,
    `xp=${p.xp}`,
    `coins=${p.coins}`,
    `diams=${p.diams}`,
  ].join("  ");

  nameSpan.textContent = p.name || "—";
}

// ---------------------------------------------------------------------------
// Actions Auth
// ---------------------------------------------------------------------------
async function playRegister() {
  const name = ($("playPlayerName").value || "").trim() || "player1";
  const r = await http("POST", "/api/register", { name });

  const authBox = $("playAuthBox");
  if (!r.ok) {
    authBox.textContent = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }

  playCurrentPlayer = r.data;
  authBox.textContent = `Connecté via cookie (register). id=${playCurrentPlayer.id}`;
  renderPlayPlayer(playCurrentPlayer);
}

async function playLogin() {
  const name = ($("playPlayerName").value || "").trim() || "player1";
  const r = await http("POST", "/api/login", { name });

  const authBox = $("playAuthBox");
  if (!r.ok) {
    authBox.textContent = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }

  playCurrentPlayer = r.data;
  authBox.textContent = `Connecté via cookie (login). id=${playCurrentPlayer.id}`;
  renderPlayPlayer(playCurrentPlayer);
}

async function playLogout() {
  const r = await http("POST", "/api/logout", null);
  const authBox = $("playAuthBox");

  if (!r.ok) {
    authBox.textContent = `ERR ${r.status} — ${JSON.stringify(r.data)}`;
    return;
  }

  playCurrentPlayer = null;
  authBox.textContent = "Déconnecté.";
  renderPlayPlayer(null);
}

// ---------------------------------------------------------------------------
// Chargement initial : vérifier si un joueur est déjà en cookie
// ---------------------------------------------------------------------------
async function loadCurrentPlayerIfAny() {
  const r = await http("GET", "/api/me");
  if (!r.ok) {
    // Pas grave, probablement pas connecté
    renderPlayPlayer(null);
    $("playAuthBox").textContent = "Non connecté.";
    return;
  }

  playCurrentPlayer = r.data;
  $("playAuthBox").textContent = `Connecté via cookie. id=${playCurrentPlayer.id}`;
  renderPlayPlayer(playCurrentPlayer);
}

// ---------------------------------------------------------------------------
// Wiring des événements
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  $("btnPlayRegister").addEventListener("click", playRegister);
  $("btnPlayLogin").addEventListener("click", playLogin);
  $("btnPlayLogout").addEventListener("click", playLogout);

  loadCurrentPlayerIfAny();
});
