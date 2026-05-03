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

// ============================================================
// Story / Levels cache
// ============================================================
let LEVEL_DEFS = [];            // contenu brut de /api/levels
let LEVEL_STORY_INDEX = {};     // { [level]: [story_events] }

let storyQueue = [];            // file des story_events à afficher
let storyIsPlaying = false;     // pour éviter de lancer 2 histoires en même temps
let _seenStoryIds = new Set();    // story IDs déjà vus (chargés depuis /api/state)
let pendingLevelUpModal = null;   // { newLevel, rewards } — affiché après les stories
let pendingNameModal = false;     // true si le modal de nom doit s'afficher après les stories
let pendingTutorialMilestones = []; // callbacks tutoriel différés après stories + level-up modal
let _knownResourceKeys = new Set(); // ressources déjà vues (pour notif première récolte)
window._knownResourceKeys = _knownResourceKeys; // expose for land_common.js

// ============================================================
// Feature flags (system_unlocks via /api/levels)
// ============================================================
let ACTIVE_FEATURES = new Set();

// Travel / lands
let UNLOCKED_LANDS = []; // list of lands unlocked for the current player
let TRAVEL_LIST_LOADED = false;

// ============================================================
// Resources registry (icons from DB via /api/resources/resources)
// ============================================================
let RESOURCE_DEFS_BY_KEY = {};

/**
 * Normalise un chemin icon venant de la DB / YAML.
 * Gère :
 *  - http(s)://...
 *  - /static/...
 *  - static/...
 *  - autres chemins relatifs
 */
function normalizeStaticPath(path) {
  if (!path) return null;

  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  if (path.startsWith("/")) {
    return path;
  }

  if (path.startsWith("static/")) {
    return "/" + path;
  }

  // Fallback : on s'assure qu'il y a bien /static/ au début
  return "/static/" + path.replace(/^\/?static\//, "");
}

/**
 * Retourne l'URL d'icône pour une ressource à partir du registre.
 * @param {string} resKey
 * @returns {string|null}
 */
function getResourceIconPathFromRegistry(resKey) {
  if (!resKey) return null;
  const def = RESOURCE_DEFS_BY_KEY[resKey];
  if (!def || !def.icon) return null;
  return normalizeStaticPath(def.icon);
}

/**
 * Version "publique" avec fallback :
 * - d'abord DB (RESOURCE_DEFS_BY_KEY)
 * - sinon, ancien chemin hardcodé (resources/<key>.png)
 */
function getResourceIconPath(resKey) {
  const fromDb = getResourceIconPathFromRegistry(resKey);
  if (fromDb) return fromDb;

  // Fallback, au cas où la ressource n'est pas trouvée dans la DB
  return `/static/assets/img/items/resources/${resKey}.png`;
}

/**
 * Charge les ResourceDef depuis /api/resources/resources si pas déjà fait.
 */
async function loadResourceDefsIfNeeded() {
  if (Object.keys(RESOURCE_DEFS_BY_KEY).length > 0) return;

  try {
    const res = await http("GET", "/api/resources");
    if (!res.ok) {
      console.error("[resources] Failed to load /api/resources/resources", res.status, res.data);
      return;
    }

    const list = Array.isArray(res.data) ? res.data : [];
    const byKey = {};
    list.forEach((r) => {
      if (r && r.key) {
        byKey[r.key] = r;
      }
    });

    RESOURCE_DEFS_BY_KEY = byKey;

    // Exposé global si tu veux debug dans la console
    window.LL_RESOURCES = list;
    window.LL_RESOURCES_BY_KEY = byKey;

    console.log("[resources] Loaded", list.length, "resources from DB");
  } catch (err) {
    console.error("[resources] Error while loading resource defs", err);
  }
}

// On expose la fonction pour d'autres scripts si besoin (village, lands, etc.)
window.getResourceIconPath = getResourceIconPath;

/**
 * Calcule toutes les features débloquées jusqu'au niveau `level`.
 * Prend les données de LEVEL_DEFS (avec system_unlocks).
 */
function computeUnlockedFeaturesForLevel(level) {
  const lvl = Number(level || 0);
  const features = new Set();

  (LEVEL_DEFS || []).forEach((def) => {
    const defLevel = Number(def.level ?? 0);
    if (defLevel > lvl) return;

    const unlocks = Array.isArray(def.system_unlocks)
      ? def.system_unlocks
      : [];

    unlocks.forEach((u) => {
      if (!u) return;

      // Format normal : { type: "feature", key: "daily_chest" }
      if (typeof u === "object" && u.key && (u.type === "feature" || !u.type)) {
        features.add(u.key);
      }
      // Fallback si un jour tu mets juste une string
      else if (typeof u === "string") {
        features.add(u);
      }
    });
  });

  return features;
}

/**
 * Recalcule ACTIVE_FEATURES en fonction du joueur + LEVEL_DEFS
 * puis applique l'affichage sur le HUD / menus.
 */
function recomputeFeaturesFromLevels() {
  if (!window.currentPlayer || !LEVEL_DEFS.length) return;

  const lvl = Number(window.currentPlayer.level || 0);
  ACTIVE_FEATURES = computeUnlockedFeaturesForLevel(lvl);

  applyFeatureVisibility();
}

/**
 * Test simple utilisable partout : isFeatureUnlocked("daily_chest")
 */
function isFeatureUnlocked(key) {
  if (!key) return false;
  return ACTIVE_FEATURES.has(key);
}

/**
 * Parcourt tous les éléments ayant data-feature="xxx"
 * et les affiche / cache selon l'état de la feature.
 *
 * Convention :
 *  - data-feature="quest_system"  → clé telle que dans system_unlocks
 *  - optionnel data-feature-hide="0" pour ne PAS faire display:none
 */
function applyFeatureVisibility() {
  const nodes = document.querySelectorAll("[data-feature]");
  if (!nodes.length) return;

  nodes.forEach((el) => {
    const key = el.getAttribute("data-feature");
    if (!key) return;

    const unlocked = isFeatureUnlocked(key);

    el.classList.toggle("feature-locked", !unlocked);

    // Par défaut : on cache complètement l'élément si non débloqué
    const hide = el.dataset.featureHide !== "0";

    if (hide) {
      if (unlocked) {
        // On remet le display original si on l'avait sauvegardé
        const prev = el.dataset.featureDisplay || "";
        el.style.display = prev;
      } else {
        // On mémorise le display actuel pour plus tard
        if (!el.dataset.featureDisplay) {
          el.dataset.featureDisplay = el.style.display || "";
        }
        el.style.display = "none";
      }
    }

    // Accessibilité : on marque désactivé
    if (!unlocked) {
      el.setAttribute("aria-disabled", "true");
    } else {
      el.removeAttribute("aria-disabled");
    }
  });
}

// On expose le testeur global pour d'autres scripts (village, etc.)
window.isFeatureUnlocked = isFeatureUnlocked;

function formatRewardLabel(r) {
  const amount = r.amount ?? 0;

  if (r.type === "shards") {
    const label = (typeof I18n !== "undefined")
      ? I18n.currencyLabel("primary", amount)
      : (r.label || "Shards");
    return `${amount} ${label}`;
  }

  if (r.type === "essence") {
    const label = (typeof I18n !== "undefined")
      ? I18n.currencyLabel("premium", amount)
      : (r.label || "Essence");
    return `${amount} ${label}`;
  }

  if (r.type === "resource") {
    const name = r.label || r.key || "???";
    return `${amount} x ${name}`;
  }

  if (r.type === "card") {
    // Land access cards: show description ("Débloque le land Plage") instead of "1 x Accès Plage"
    if (r.key?.startsWith("land_")) {
      return r.description || r.label || r.key;
    }
    const name = r.label || r.key || "Carte";
    return `${amount} x ${name}`;
  }

  return r.label || r.type || "?";
}

function getRewardIconPath(r) {
  // 1) Si le backend fournit déjà un chemin d'icône, on le respecte
  if (r.icon) {
    if (typeof r.icon === "string" && r.icon.startsWith("/")) {
      return r.icon;
    }
    // Si ce n'est pas absolu, on le passe tel quel (ou tu peux prefixer si besoin)
    return r.icon;
  }

  // 2) Fallbacks basés sur le type et la key
  if (r.type === "resource" && r.key) {
    return `/static/assets/img/items/resources/${r.key}.png`;
  }

  if (r.type === "card" && r.key) {
    return `/static/assets/img/cards/${r.key}.png`;
  }

  if (r.type === "shards") {
    return `/static/assets/img/ui/shards.png`;
  }

  if (r.type === "essence") {
    return `/static/assets/img/ui/essence.png`;
  }

  return null;
}

// =====================================================
// Image viewer (lightbox)
// =====================================================

function initImageViewer() {
  const modal = document.getElementById("imgViewer");
  const closeBtn = document.getElementById("imgViewerClose");
  const backdrop = document.getElementById("imgViewerBackdrop");
  const imgTag = document.getElementById("imgViewerImg");

  function close() {
    modal.classList.remove("is-open");
    imgTag.src = "";
  }

  closeBtn.addEventListener("click", close);
  backdrop.addEventListener("click", close);

  // On ajoute une méthode globale pour ouvrir l'image
  window.showImageViewer = function (src) {
    imgTag.src = src;
    modal.classList.add("is-open");
  };
}

// ============================================================
// Load levels & cache story events
// ============================================================
async function loadLevelDefinitions() {
  try {
    const res = await http("GET", "/api/levels");
    if (!res.ok) {
      console.error("[levels] Failed to load /api/levels", res.status);
      return;
    }

    const data = res.data || [];
    LEVEL_DEFS = data;
    LEVEL_STORY_INDEX = {};

    data.forEach((lvl) => {
      const lvlNo = Number(lvl.level);
      LEVEL_STORY_INDEX[lvlNo] = Array.isArray(lvl.story_events)
        ? lvl.story_events
        : [];
    });

    // debug léger
    console.log(
      "[story] Loaded level definitions, story levels =",
      Object.keys(LEVEL_STORY_INDEX)
    );

        // Dès qu'on a les levels + un joueur, on recalcule les features
    if (window.currentPlayer) {
      recomputeFeaturesFromLevels();
    }


  } catch (err) {
    console.error("[levels] Error while loading /api/levels", err);
  }
}


function showLevelUpModal(level, rewards) {
  const modal = document.getElementById("levelUpModal");
  if (!modal) return;

  const levelSpan = document.getElementById("levelUpModalLevel");
  const rewardsContainer = document.getElementById("levelUpModalRewards");
  if (!levelSpan || !rewardsContainer) return;

  levelSpan.textContent = level;
  rewardsContainer.innerHTML = "";

  (rewards || []).forEach((r) => {
    const item = document.createElement("div");
    item.className = "levelup-reward-item";

    const iconPath = getRewardIconPath(r);
    if (iconPath) {
      const img = document.createElement("img");

      // Cartes → taille spéciale
      if (r.type === "card") {
        img.className = "levelup-reward-card";
      } else {
        img.className = "levelup-reward-icon";
      }

      img.src = iconPath;
      img.alt = r.label || r.type;
      item.appendChild(img);
    }

    const label = document.createElement("div");
    label.className = "levelup-reward-label";
    label.textContent = formatRewardLabel(r);
    item.appendChild(label);

    rewardsContainer.appendChild(item);
  });

  modal.classList.add("is-open");
}

function initLevelUpModal() {
  const modal = document.getElementById("levelUpModal");
  if (!modal) return;

  const closeBtn = document.getElementById("levelUpModalClose");
  const backdrop = document.getElementById("levelUpModalBackdrop");

  const close = () => {
    modal.classList.remove("is-open");
  };

  if (closeBtn) closeBtn.addEventListener("click", close);
  if (backdrop) backdrop.addEventListener("click", close);
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
  const hudshards = $("hudshards");
  const hudessence = $("hudessence");

  // 🔥 NEW: garder currentPlayer en phase avec ce qui est affiché (et accessible aux autres scripts)
  if (!p) {
    currentPlayer = null;
    window.currentPlayer = null;
  } else {
    currentPlayer = p;
    window.currentPlayer = p;
  }


  if (!p) {
    if (header) header.textContent = 'Aucun joueur (clique sur "Commencer").';
    if (xpBar) xpBar.style.width = "0%";
    if (xpLeft) xpLeft.textContent = "XP: 0 • Level: 0";
    if (xpRight) xpRight.textContent = "0%";
    if (headerName) headerName.textContent = "—";
    if (hudshards) hudshards.textContent = "0";
    if (hudessence) hudessence.textContent = "0";
    
    // HUD moderne à zéro
    updatePlayerHUD({
      level: 0,
      xp: 0,
      xp_next: 100,
      shards: 0,
      essence: 0,
      land_name: window.LAND_NAME || "",
    });

    // Recalcule les features dès que le niveau du joueur change
    if (LEVEL_DEFS && LEVEL_DEFS.length) {
      recomputeFeaturesFromLevels();
    }

    return;
  }

  const xp = Number(p.xp ?? 0);
  const level = Number(p.level ?? 0);
  const shards = Number(p.shards ?? 0);
  const essence = Number(p.essence ?? 0);
  const next = p.next_xp ?? p.nextXp ?? null;

  if (header) {
    header.textContent =
      `id=${p.id} • ${p.name} • lvl=${level} ` +
      `• XP=${xp} • shards=${shards}`;
  }

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
  if (hudshards) hudshards.textContent = shards;
  if (hudessence) hudessence.textContent = essence;


  
    // 🔥 Mise à jour du nouveau HUD
  updatePlayerHUD({
    level,
    xp,
    xp_next: next ?? 100,
    shards,
    essence,
    land_name: window.LAND_NAME || "",
  });
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
  return `/static/assets/img/items/resources/${raw}`;
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
async function refreshInventory(isStartup = false) {
  const r = await http("GET", "/api/inventory");
  if (!r.ok) {
    console.error("inventory error", r);
    renderInventory([]);
    return;
  }
  renderInventory(r.data);

  // Populate known resource keys on first load (no new-resource notif at startup)
  if (isStartup && Array.isArray(r.data)) {
    r.data.forEach((item) => {
      if (item.resource) _knownResourceKeys.add(item.resource);
    });
  }
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

  // --- First-resource notifications ---
  const loot = Array.isArray(data.loot) ? data.loot : [];
  const isFirstEverCollect = _knownResourceKeys.size === 0;
  loot.forEach((entry) => {
    const key = entry.resource;
    if (key && !_knownResourceKeys.has(key)) {
      _knownResourceKeys.add(key);
      if (typeof window.GameNotif !== "undefined") {
        window.GameNotif.firstResource(
          key,
          entry.label || key,
          entry.icon || null,
          entry.final_amount ?? entry.base_amount ?? 1
        );
      }
    }
  });

  // --- Tutorial: first collect ever ---
  if (isFirstEverCollect && loot.length > 0) {
    if (typeof window.TutorialApp !== "undefined") {
      window.TutorialApp.onFirstCollect();
    }
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

  // 🔥 Charge les niveaux + flags vus + stories de premier login
  await loadLevelDefinitions();
  await loadStoryFlags();
  enqueueInitialStoriesOnLogin();

  await refreshInventory(true);
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
    if (c.price_shards > 0) priceParts.push(`${c.price_shards} shards`);
    if (c.price_essence > 0) priceParts.push(`${c.price_essence} essence`);
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
    // Also reset boosts
    renderBoostSummary([]);
    return;
  }

  const cards = r.data || [];
  renderCardShop(cards);
  renderBoostSummary(cards);   // 👈 NEW
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

  // refresh player shards/essence + shop
  if (d.player) {
    renderPlayer({
      ...currentPlayer,
      shards: d.player.shards,
      essence: d.player.essence,
    });
    currentPlayer.shards = d.player.shards;
    currentPlayer.essence = d.player.essence;
  }

  await loadCardShop();
}

// ---------------------------------------------------------------------------
// Boost summary rendering (based on cards list)
// ---------------------------------------------------------------------------
function renderBoostSummary(cards) {
  const box = $("boostSummaryBox");
  if (!box) return;

  if (!currentPlayer) {
    box.textContent = "Aucun joueur connecté.";
    return;
  }

  if (!cards || !cards.length) {
    box.textContent = "Aucun boost actif.";
    return;
  }

  // Aggregate boosts
  let xpBoostCards = 0;
  let globalCdCards = 0;
  const resourceBoosts = {};     // key -> { qtyBoost: n, qtyCd: n }

  for (const c of cards) {
    const owned = c.owned_qty || 0;
    if (!owned) continue;

    const type = c.type;
    const res = c.target_resource || null;

    if (type === "boost_xp") {
      xpBoostCards += owned;
    } else if (type === "reduce_cooldown") {
      if (res) {
        if (!resourceBoosts[res]) {
          resourceBoosts[res] = { qtyBoost: 0, qtyCd: 0 };
        }
        resourceBoosts[res].qtyCd += owned;
      } else {
        globalCdCards += owned;
      }
    } else if (type === "resource_boost") {
      if (!res) continue;
      if (!resourceBoosts[res]) {
        resourceBoosts[res] = { qtyBoost: 0, qtyCd: 0 };
      }
      resourceBoosts[res].qtyBoost += owned;
    }
  }

  const parts = [];

  // XP boosts: +10% per card
  if (xpBoostCards > 0) {
    const pct = xpBoostCards * 10;
    parts.push(`+${pct}% XP`);
  }

  // Global cooldown reduction: -10% per card
  if (globalCdCards > 0) {
    const pct = globalCdCards * 10;
    parts.push(`-${pct}% cooldown global`);
  }

  // Per-resource boosts
  Object.entries(resourceBoosts).forEach(([resKey, vals]) => {
    const { qtyBoost, qtyCd } = vals;
    const labels = [];

    if (qtyBoost > 0) {
      const pct = qtyBoost * 10;
      labels.push(`+${pct}% ${resKey}`);
    }
    if (qtyCd > 0) {
      const pct = qtyCd * 10;
      labels.push(`-${pct}% cooldown ${resKey}`);
    }

    if (labels.length) {
      parts.push(labels.join(", "));
    }
  });

  if (!parts.length) {
    box.textContent = "Aucun boost actif.";
  } else {
    box.textContent = "Boosts actifs : " + parts.join(" • ");
  }
}

// ---------------------------------------------------------------------------
// CARD ADMIN PANEL (Debug UI)
// ---------------------------------------------------------------------------

async function refreshCardsDev() {
  const table = $("cardDevTable");
  const status = $("cardDevStatus");

  if (!currentPlayer) {
    table.innerHTML = `
      <tr><td colspan="7" class="text-center text-muted">Aucun joueur chargé</td></tr>`;
    status.textContent = "Aucun joueur.";
    return;
  }

  status.textContent = "Chargement...";
  const r = await http("GET", `/api/cards?playerId=${currentPlayer.id}`);

  if (!r.ok) {
    table.innerHTML = `
      <tr><td colspan="7" class="text-danger text-center">Erreur chargement (${r.status})</td></tr>`;
    status.textContent = "Erreur";
    return;
  }

  const cards = r.data || [];
  if (!cards.length) {
    table.innerHTML = `
      <tr><td colspan="7" class="text-center text-muted">Aucune carte définie</td></tr>`;
    status.textContent = "Aucune carte.";
    return;
  }

  table.innerHTML = cards.map(c => {
    const icon = c.icon && c.icon.startsWith("/")
      ? `<img src="${c.icon}" style="width:24px;height:24px;image-rendering:pixelated">`
      : "";

    const tgt = c.target_resource || c.target_building || "-";

    return `
      <tr>
        <td>${icon}</td>
        <td class="font-monospace">${c.key}</td>
        <td>${c.label}</td>
        <td>${c.type}</td>
        <td>${tgt}</td>
        <td>${c.owned_qty}</td>
        <td>
          <button class="btn btn-sm btn-success me-1"
                  onclick="giveCardDev('${c.key}')">+1</button>
          <button class="btn btn-sm btn-warning"
                  onclick="resetCardDev('${c.key}')">Reset</button>
        </td>
      </tr>
    `;
  }).join("");

  status.textContent = "OK.";
}

async function giveCardDev(cardKey) {
  if (!currentPlayer) return;

  const body = {
    card_key: cardKey,
    playerId: currentPlayer.id
  };

  const r = await http("POST", "/api/cards/buy", body);

  if (!r.ok) {
    alert("Erreur d'ajout: " + JSON.stringify(r.data));
    return;
  }

  await refreshCardsDev();
}

async function resetCardDev(cardKey) {
  if (!currentPlayer) return;

  // Reset = mettre qty = 0 dans player_cards
  const r = await http("POST", "/api/dev/set_card_qty", {
    playerId: currentPlayer.id,
    card_key: cardKey,
    qty: 0
  });

  if (!r.ok) {
    alert("Reset error: " + JSON.stringify(r.data));
    return;
  }

  await refreshCardsDev();
}

// ---------------------------------------------------------------------------
// HUD helpers
// ---------------------------------------------------------------------------

function updatePlayerHUD(playerData) {
  // playerData attendu: { level, xp, xp_next, shards, essence, land_name }
  if (!playerData) return;

  const safeCur  = Math.round(Number(playerData.xp      ?? 0));
  const safeNext = Math.round(Number(playerData.xp_next ?? 100));
  const ratio    = safeNext > 0 ? Math.max(0, Math.min(1, safeCur / safeNext)) : 0;
  const lvl      = playerData.level ?? 0;

  // ── Desktop: barre horizontale ──────────────────────────────
  const levelEl  = document.getElementById("hud-level");
  const xpFillEl = document.getElementById("hud-xp-fill");
  const xpCurEl  = document.getElementById("hud-xp-current");
  const xpNextEl = document.getElementById("hud-xp-next");

  if (levelEl)  levelEl.textContent  = lvl;
  if (xpCurEl)  xpCurEl.textContent  = safeCur;
  if (xpNextEl) xpNextEl.textContent = safeNext;
  if (xpFillEl) xpFillEl.style.width = `${ratio * 100}%`;

  // ── Mobile/tablette: anneau circulaire ───────────────────────
  const levelRingEl   = document.getElementById("hud-level-ring");
  const xpCurRingEl   = document.getElementById("hud-xp-current-ring");
  const xpNextRingEl  = document.getElementById("hud-xp-next-ring");
  const xpRingEl      = document.getElementById("hud-xp-ring");

  if (levelRingEl)  levelRingEl.textContent  = lvl;
  if (xpCurRingEl)  xpCurRingEl.textContent  = safeCur;
  if (xpNextRingEl) xpNextRingEl.textContent = safeNext;
  if (xpRingEl) {
    const circumference = 106.81; // 2π × 17
    xpRingEl.style.strokeDashoffset = `${circumference * (1 - ratio)}`;
  }

  // ── Commun ───────────────────────────────────────────────────
  const shardsEl  = document.getElementById("hud-shards");
  const essenceEl = document.getElementById("hud-essence");
  const landNameEl = document.getElementById("gh-land-name");

  if (shardsEl)   shardsEl.textContent   = playerData.shards    ?? 0;
  if (essenceEl)  essenceEl.textContent  = playerData.essence   ?? 0;
  if (landNameEl) landNameEl.textContent = playerData.land_name || "";
}

// ---------------------------------------------------------------------------
// Loot Toasts (icône + quantité)
// ---------------------------------------------------------------------------

function formatLootAmount(value) {
  const v = Number(value || 0);
  return "+ " + v.toFixed(1); // ex: + 1.6
}

function showLootToasts(lootArray) {
  if (!Array.isArray(lootArray) || lootArray.length === 0) return;

  const container = document.getElementById("loot-toasts");
  if (!container) return;

  lootArray.forEach((entry, index) => {
    const rawAmount =
      typeof entry.final_amount === "number"
        ? entry.final_amount
        : entry.base_amount;

    const qtyText = formatLootAmount(rawAmount);
    const resKey = entry.resource;            // ex: "ancient_bark"
    const label = entry.label || resKey;      // label DB si présent

    // 1️⃣ On privilégie toujours l'icône envoyée par l'API (DB)
    let iconUrl = entry.icon || null;

    // 2️⃣ Fallback possible : fonction globale getRewardIconPath (si dispo)
    if (!iconUrl && typeof getRewardIconPath === "function") {
      iconUrl = getRewardIconPath({
        type: "resource",
        key: resKey,
        label: label,
        icon: null,
      });
    }

    // 3️⃣ Dernier fallback : ancien chemin (ne devrait presque jamais servir)
    if (!iconUrl) {
      iconUrl = `/static/assets/img/items/resources/${resKey}.png`;
    }

    const toast = document.createElement("div");
    toast.className = "loot-toast";

    const img = document.createElement("img");
    img.src = iconUrl;
    img.alt = label;
    toast.appendChild(img);

    const qtySpan = document.createElement("span");
    qtySpan.className = "loot-toast-qty";
    qtySpan.textContent = qtyText;
    toast.appendChild(qtySpan);

    container.appendChild(toast);

    // déclenche l'animation CSS
    requestAnimationFrame(() => {
      toast.classList.add("show");
    });

    const lifeTime = 2200 + index * 250;
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => {
        toast.remove();
      }, 200);
    }, lifeTime);
  });
}


// ============================================================
// Story helpers: seen / queue / run
// ============================================================
function hasSeenStoryEvent(eventId) {
  if (!eventId) return false;
  return _seenStoryIds.has(eventId);
}

function markStoryEventSeen(eventId) {
  if (!eventId) return;
  _seenStoryIds.add(eventId);
  // Persist to DB (fire and forget)
  http("POST", "/api/story/seen", { story_id: eventId }).catch((e) =>
    console.warn("[story] markStoryEventSeen:", e)
  );
}

/**
 * Charge les story flags depuis /api/state et peuple _seenStoryIds.
 * Appelé au démarrage, avant enqueueInitialStoriesOnLogin().
 */
async function loadStoryFlags() {
  try {
    const r = await http("GET", "/api/state");
    if (r.ok && Array.isArray(r.data?.story_flags)) {
      _seenStoryIds = new Set(r.data.story_flags);
    }
  } catch (e) {
    console.warn("[story] loadStoryFlags failed:", e);
  }
}

/**
 * Affiche le modal de saisie du nom du personnage.
 * Appelé automatiquement après l'intro_forest_wakeup si pendingNameModal est true.
 */
function showNameInputModal() {
  const modal   = document.getElementById("nameInputModal");
  const input   = document.getElementById("nameInputField");
  const confirm = document.getElementById("nameInputConfirm");
  const errEl   = document.getElementById("nameInputError");
  if (!modal) return;

  modal.classList.add("is-open");
  if (input) {
    input.value = "";
    setTimeout(() => input.focus(), 100);
  }

  const doConfirm = async () => {
    const name = (input?.value || "").trim();
    if (!name) {
      if (errEl) { errEl.textContent = "Veuillez entrer un nom."; errEl.style.display = ""; }
      return;
    }
    if (errEl) errEl.style.display = "none";

    const r = await http("PATCH", "/api/player/name", { name });
    if (!r.ok) {
      const msg = r.data?.error === "name_taken"
        ? "Ce nom est déjà pris."
        : "Erreur lors de la sauvegarde.";
      if (errEl) { errEl.textContent = msg; errEl.style.display = ""; }
      return;
    }

    // Mise à jour locale
    if (currentPlayer) {
      currentPlayer.name = r.data.name;
      window.currentPlayer = currentPlayer;
      renderPlayer(currentPlayer);
    }

    modal.classList.remove("is-open");
    confirm.removeEventListener("click", doConfirm);

    // Start interactive tutorial after name is set
    if (typeof window.TutorialApp !== "undefined") {
      window.TutorialApp.startIntroSequence();
    }
  };

  confirm.addEventListener("click", doConfirm);

  // Confirmer avec Entrée
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doConfirm();
  });
}

function enqueueStoryEvent(ev) {
  if (!ev) return;
  storyQueue.push(ev);
}

function renderStoryEventAsText(ev) {
  const lang = document.documentElement.lang || "fr";
  const pages = Array.isArray(ev.pages) ? ev.pages : [];
  const lines = [];

  pages.forEach((p) => {
    const t =
      (p.text && (p.text[lang] || p.text.en)) ||
      "";
    const speaker = p.speaker || "";
    const mood = p.mood || "";
    const prefix = speaker ? `[${speaker}${mood ? " / " + mood : ""}] ` : "";
    if (t.trim()) {
      lines.push(prefix + t.trim());
    }
  });

  return lines.join("\n\n");
}

function playNextStoryFromQueue() {
  if (storyIsPlaying) return;

  const ev = storyQueue.shift();
  if (!ev) {
    // File vide — afficher le modal de nom si en attente
    if (pendingNameModal) {
      pendingNameModal = false;
      showNameInputModal();
      return;
    }
    // Puis le modal de level-up différé si présent
    if (pendingLevelUpModal) {
      const { newLevel, rewards } = pendingLevelUpModal;
      pendingLevelUpModal = null;
      if (typeof showLevelUpModal === "function") {
        showLevelUpModal(newLevel, rewards);
      }
      // Après le modal level-up, drainer les milestones tutoriel
      if (pendingTutorialMilestones.length > 0) {
        const cb = pendingTutorialMilestones.shift();
        setTimeout(cb, 600); // délai après fermeture du modal
      }
      return;
    }
    // File vide, pas de modal — drainer les milestones tutoriel si besoin
    if (pendingTutorialMilestones.length > 0) {
      const cb = pendingTutorialMilestones.shift();
      setTimeout(cb, 400);
    }
    return;
  }

  storyIsPlaying = true;

  // 🟡 Si le nouveau StoryModal est dispo → on l'utilise
  if (typeof window.openStoryModalForEvent === "function") {
    window.openStoryModalForEvent(ev, () => {
      // callback appelé quand le joueur clique sur "J'ai compris"
      storyIsPlaying = false;
      // Toujours appeler playNextStoryFromQueue pour gérer les pendingXxx
      playNextStoryFromQueue();
    });
    return;
  }

  // 🔙 Fallback : ancien comportement en alert()
  const msg = renderStoryEventAsText(ev);
  alert(msg);

  if (ev.id && typeof markStoryEventSeen === "function") {
    markStoryEventSeen(ev.id);
  }

  storyIsPlaying = false;
  playNextStoryFromQueue();
}


/**
 * Appelé quand le joueur passe de oldLevel -> newLevel.
 * Parcourt tous les niveaux gagnés et met en file les story_events
 * avec trigger === "on_level_reached".
 */
function handleStoryAfterLevelUp(oldLevel, newLevel) {
  if (!LEVEL_STORY_INDEX) return;

  for (let lvl = oldLevel + 1; lvl <= newLevel; lvl++) {
    const events = LEVEL_STORY_INDEX[lvl] || [];
    events
      .filter((ev) => ev.trigger === "on_level_reached")
      .forEach((ev) => {
        if (ev.show_once && hasSeenStoryEvent(ev.id)) {
          return; // déjà vu
        }
        enqueueStoryEvent(ev);
      });
  }

  // Les stories seront démarrées par handleLevelUpFront après cet appel.
}

/**
 * Stories de type "on_first_login"
 * Appelée après qu'on connaisse le joueur + qu'on ait chargé /api/levels.
 */
function enqueueInitialStoriesOnLogin() {
  if (!Array.isArray(LEVEL_DEFS) || !LEVEL_DEFS.length) return;

  let introWasQueued = false;

  LEVEL_DEFS.forEach((lvl) => {
    const events = Array.isArray(lvl.story_events) ? lvl.story_events : [];

    events
      .filter((ev) => ev.trigger === "on_first_login")
      .forEach((ev) => {
        if (ev.show_once && hasSeenStoryEvent(ev.id)) {
          return; // déjà vu => on ne rejoue pas
        }
        enqueueStoryEvent(ev);
        if (ev.id === "intro_forest_wakeup") {
          introWasQueued = true;
        }
      });
  });

  // Si l'intro a joué pour la première fois, demander le nom après
  if (introWasQueued) {
    pendingNameModal = true;
    // Tutorial starts after name modal (triggered inside showNameInputModal's doConfirm)
  } else if (storyQueue.length === 0) {
    // Returning player: no intro queued — still show tutorial collect step if not done
    setTimeout(() => {
      if (typeof window.TutorialApp !== "undefined") {
        window.TutorialApp.startIntroSequence();
      }
    }, 800);
  }

  // S'il y a au moins une story dans la file, on démarre
  if (storyQueue.length > 0 && typeof window.playNextStoryFromQueue === "function") {
    window.playNextStoryFromQueue();
  }
}


/**
 * Stories déclenchées quand un land est débloqué via une carte de land
 * reçue dans les récompenses de level.
 *
 * - oldLevel / newLevel : niveaux avant/après
 * - levelRewards : array de récompenses du level up (shards, essence, card, ...)
 *
 * On va chercher dans LEVEL_STORY_INDEX[lvl] les events:
 *   trigger === "on_land_unlocked"
 *   et land_key qui correspond à une carte de land débloquée.
 */
function handleLandStoryOnUnlock(oldLevel, newLevel, levelRewards) {
  if (!LEVEL_STORY_INDEX) return;

  const rewards = Array.isArray(levelRewards) ? levelRewards : [];

  // On ne garde que les cartes de type "land_xxx"
  const unlockedLandKeys = rewards
    .filter(
      (r) =>
        r &&
        r.type === "card" &&
        typeof r.key === "string" &&
        r.key.startsWith("land_")
    )
    .map((r) => r.key);

  if (!unlockedLandKeys.length) return;

  for (let lvl = oldLevel + 1; lvl <= newLevel; lvl++) {
    const events = LEVEL_STORY_INDEX[lvl] || [];
    events
      .filter(
        (ev) =>
          ev &&
          ev.trigger === "on_land_unlocked" &&
          (!ev.land_key || unlockedLandKeys.includes(ev.land_key))
      )
      .forEach((ev) => {
        if (ev.show_once && hasSeenStoryEvent(ev.id)) {
          return;
        }
        enqueueStoryEvent(ev);
      });
  }
}

/**
 * Stories déclenchées quand on ENTRE sur un land (page /land/xxx ouverte).
 * On parcourt tous les events ayant trigger === "on_enter_land" + land_key.
 */
function handleStoryOnEnterLand(landKey) {
  if (!LEVEL_STORY_INDEX || !landKey) return;

  Object.values(LEVEL_STORY_INDEX).forEach((events) => {
    (events || [])
      .filter(
        (ev) =>
          ev &&
          ev.trigger === "on_enter_land" &&
          (!ev.land_key || ev.land_key === landKey)
      )
      .forEach((ev) => {
        if (ev.show_once && hasSeenStoryEvent(ev.id)) {
          return;
        }
        enqueueStoryEvent(ev);
      });
  });

  // Pas de modal de level up ici, on peut jouer la story tout de suite
  if (typeof playNextStoryFromQueue === "function") {
    playNextStoryFromQueue();
  }
}

/**
 * Orchestrateur front : à appeler quand on détecte un level up côté client.
 * - Affiche le LevelUp modal
 * - Met en file les stories "on_level_reached"
 * - Met en file les stories "on_land_unlocked" (en fonction des rewards)
 */
function handleLevelUpFront(oldLevel, newLevel, levelRewards) {
  const rewards = levelRewards || [];

  // Gather system_unlocks for this level (for notification)
  const levelDef = (LEVEL_DEFS || []).find((d) => Number(d.level) === newLevel);
  const unlocks  = Array.isArray(levelDef?.system_unlocks) ? levelDef.system_unlocks : [];

  // --- Notification: level up ---
  if (typeof window.GameNotif !== "undefined") {
    window.GameNotif.levelUp(newLevel, rewards, unlocks);
  }

  // 1) Stories de type "on_level_reached" (mises en file d'abord)
  if (typeof handleStoryAfterLevelUp === "function") {
    handleStoryAfterLevelUp(oldLevel, newLevel);
  }

  // 2) Stories de type "on_land_unlocked"
  handleLandStoryOnUnlock(oldLevel, newLevel, rewards);

  // 3) Modal de Level Up — différé après les stories
  if (storyQueue.length > 0) {
    pendingLevelUpModal = { newLevel, rewards };
    playNextStoryFromQueue();
  } else {
    if (typeof showLevelUpModal === "function") {
      showLevelUpModal(newLevel, rewards);
    }
  }

  // --- Tutorial milestones (différés après stories + level-up modal) ---
  if (typeof window.TutorialApp !== "undefined") {
    if (newLevel === 1) pendingTutorialMilestones.push(() => window.TutorialApp.onLevel1Reached());
    if (newLevel === 2) pendingTutorialMilestones.push(() => window.TutorialApp.onLevel2Reached());
    if (newLevel === 3) pendingTutorialMilestones.push(() => window.TutorialApp.onLevel3Reached());
  }

  // Si aucune story ni modal en attente, drainer immédiatement
  if (storyQueue.length === 0 && !pendingLevelUpModal && pendingTutorialMilestones.length > 0) {
    const cb = pendingTutorialMilestones.shift();
    setTimeout(cb, 400);
  }
}

// On expose au window pour les autres scripts (land_common.js)
window.handleStoryOnEnterLand = handleStoryOnEnterLand;
window.handleLevelUpFront = handleLevelUpFront;


// On met la fonction sur window pour l'appeler depuis les lands
window.showLootToasts = showLootToasts;

/**
 * Initialise le bouton 📜 du HUD pour ouvrir/fermer le panel de quêtes.
 */
function _initQuestHudButton() {
  const btn   = document.getElementById("btn-quests");
  const close = document.getElementById("btn-quests-close");

  if (btn) {
    btn.addEventListener("click", () => {
      if (typeof window.QQ_openPanel === "function") window.QQ_openPanel();
    });
  }

  if (close) {
    close.addEventListener("click", () => {
      if (typeof window.QQ_closePanel === "function") window.QQ_closePanel();
    });
  }
}

/**
 * Affiche un toast "quête prête à être réclamée" pour chaque quête de la liste.
 * @param {Array<{id: number, title: string}>} quests
 */
function showQuestReadyToasts(quests) {
  if (!Array.isArray(quests) || quests.length === 0) return;
  const container = document.getElementById("loot-toasts");
  if (!container) return;

  // Light up the HUD dot immediately when a quest becomes claimable
  const dot = document.getElementById("hud-quest-dot");
  if (dot) dot.style.display = "block";

  quests.forEach((q, index) => {
    const toast = document.createElement("div");
    toast.className = "quest-ready-toast";
    toast.textContent = `✔ Quête prête : ${q.title}`;
    container.appendChild(toast);

    requestAnimationFrame(() => { toast.classList.add("show"); });

    const lifetime = 3500 + index * 400;
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 220);
    }, lifetime);
  });
}
window.showQuestReadyToasts = showQuestReadyToasts;


// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  await loadResourceDefsIfNeeded();
  initLevelUpModal();
  initNotebookUI();
  setupGameMenu();  
  setupDailyModal();
  refreshDailyStatus();
  initQuestsUI();
  _initQuestHudButton();
  initLevelsUI();
  initImageViewer(); 
  
  if (typeof initCraftUI === "function") {
    initCraftUI();
  }

  initTravelUI();

  const me = await tryMe();
  if (me) {
    currentPlayer = me;
    renderPlayer(currentPlayer);

    // On charge les niveaux + flags vus AVANT d'essayer de jouer les stories
    await loadLevelDefinitions();
    await loadStoryFlags();
    // 🔥 Stories "on_first_login" possibles (si jamais pas encore vues)
    enqueueInitialStoriesOnLogin();

    await refreshInventory(true);
    await refreshGrid();
    await loadCardShop();
  } else {
    renderPlayer(null);
    renderCardShop([]); 
    renderBoostSummary([]);  
    // On attend que l'utilisateur clique sur "Commencer"
  }

});

// ---------------------------------------------------------------------------
// Levels overview UI (all levels + rewards)
// ---------------------------------------------------------------------------

function initLevelsUI() {
  const trigger     = $("hud-level-zone");
  const triggerRing = $("hud-level-zone-ring");
  const modal    = $("levelsModal");
  const closeBtn = $("levelsModalClose");
  const backdrop = $("levelsModalBackdrop");

  if (trigger)     trigger.addEventListener("click", openLevelsModal);
  if (triggerRing) triggerRing.addEventListener("click", openLevelsModal);

  const close = () => {
    if (modal) modal.classList.remove("is-open");
  };

  if (closeBtn) closeBtn.addEventListener("click", close);
  if (backdrop) backdrop.addEventListener("click", close);
}

async function openLevelsModal() {
  const modal = $("levelsModal");
  const body = $("levelsModalBody");
  if (!modal || !body) return;

  body.innerHTML = `<div class="text-muted small">Chargement des niveaux...</div>`;

  const r = await http("GET", "/api/levels");
  if (!r.ok) {
    console.error("levels error", r);
    body.innerHTML = `<div class="text-danger small">Erreur chargement (${r.status})</div>`;
    modal.classList.add("is-open");
    return;
  }

  const levels = r.data || [];

  // Résumé XP en haut de la modale — utilise xp_max du niveau courant (données API)
  const summaryEl = $("levelsXpSummary");
  if (summaryEl && currentPlayer) {
    const lvl     = currentPlayer.level ?? 0;
    const cur     = Math.round(currentPlayer.xp ?? 0);

    // Cherche le niveau courant dans les données pour récupérer xp_min / xp_max réels
    const curLvlData = levels.find(l => Number(l.level) === Number(lvl));
    const xpMin = curLvlData ? (curLvlData.xp_min ?? 0) : 0;
    const xpMax = curLvlData ? (curLvlData.xp_max ?? curLvlData.x_max ?? 0) : 0;

    const range = xpMax - xpMin;
    const pct   = range > 0 ? Math.max(0, Math.min(100, ((cur - xpMin) / range) * 100)) : 0;

    summaryEl.innerHTML = `
      <div class="levels-xp-summary-bar">
        <span class="levels-xp-summary-level">Niv. ${lvl}</span>
        <div class="levels-xp-summary-track">
          <div class="levels-xp-summary-fill" style="width:${pct}%"></div>
        </div>
        <span class="levels-xp-summary-values">${cur} / ${xpMax} XP</span>
      </div>
    `;
  }

  renderLevelsList(levels);
  modal.classList.add("is-open");
}

// ---------------------------------------------------------------------------
// Travel UI: quick travel between lands
// ---------------------------------------------------------------------------

async function fetchUnlockedLands() {
  // If already loaded, do nothing
  if (TRAVEL_LIST_LOADED && UNLOCKED_LANDS.length > 0) return;

  const res = await http("GET", "/api/lands/unlocked");
  if (!res.ok) {
    console.error("[travel] Failed to load unlocked lands", res.status, res.data);
    UNLOCKED_LANDS = [];
    TRAVEL_LIST_LOADED = true;
    return;
  }

  const data = res.data || {};
  UNLOCKED_LANDS = Array.isArray(data.lands) ? data.lands : [];
  TRAVEL_LIST_LOADED = true;
}

function renderTravelList(filterText = "") {
  const listEl = document.getElementById("travel-list");
  if (!listEl) return;

  const text = (filterText || "").toLowerCase().trim();

  // Filter lands by label or key
  const filtered = UNLOCKED_LANDS.filter((land) => {
    const label = (land.label || "").toLowerCase();
    const key = (land.land_key || "").toLowerCase();
    return !text || label.includes(text) || key.includes(text);
  });

  if (!filtered.length) {
    listEl.innerHTML = `
      <div class="travel-item-empty text-muted small">
        Aucun land ne correspond à ta recherche.
      </div>
    `;
    return;
  }

  listEl.innerHTML = filtered
    .map((land, index) => {
      const isSelectedClass = index === 0 ? " travel-item-selected" : "";
      const iconHtml = land.icon
        ? `<img src="${land.icon}" alt="${land.label}" class="travel-item-icon">`
        : "";

      return `
        <button
          type="button"
          class="travel-item${isSelectedClass}"
          data-land-key="${land.land_key}"
          data-land-url="${land.url}"
        >
          ${iconHtml}
          <span class="travel-item-label">${land.label}</span>
        </button>
      `;
    })
    .join("");

  // Click = select
  listEl.querySelectorAll(".travel-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      setSelectedTravelItem(btn);
    });
    btn.addEventListener("dblclick", () => {
      setSelectedTravelItem(btn);
      confirmTravelSelection();
    });
  });
}

function setSelectedTravelItem(btn) {
  const listEl = document.getElementById("travel-list");
  if (!listEl || !btn) return;

  listEl
    .querySelectorAll(".travel-item")
    .forEach((b) => b.classList.remove("travel-item-selected"));

  btn.classList.add("travel-item-selected");
}

function getSelectedTravelItem() {
  const listEl = document.getElementById("travel-list");
  if (!listEl) return null;
  return listEl.querySelector(".travel-item-selected");
}

function confirmTravelSelection() {
  const selected = getSelectedTravelItem();
  if (!selected) return;

  const url = selected.getAttribute("data-land-url");
  if (!url) return;

  // Redirect to land
  window.location.href = url;
}

function openTravelModal() {
  const modal = document.getElementById("travelModal");
  const searchInput = document.getElementById("travel-search-input");
  if (!modal) return;

  modal.classList.add("is-open");

  // Reset filter + render list
  renderTravelList("");

  // Focus on search for quick typing
  if (searchInput) {
    searchInput.value = "";
    searchInput.focus();
  }
}

function closeTravelModal() {
  const modal = document.getElementById("travelModal");
  if (!modal) return;
  modal.classList.remove("is-open");
}

function initTravelUI() {
  const btn = document.getElementById("hud-travel-btn");
  const modal = document.getElementById("travelModal");
  const closeBtn = document.getElementById("travelModalClose");
  const backdrop = document.getElementById("travelModalBackdrop");
  const searchInput = document.getElementById("travel-search-input");
  const confirmBtn = document.getElementById("travelConfirmBtn");

  if (btn) {
    btn.addEventListener("click", async () => {
      // Lazy load lands when opening the modal
      await fetchUnlockedLands();
      openTravelModal();
    });
  }

  const close = () => {
    closeTravelModal();
  };

  if (closeBtn) closeBtn.addEventListener("click", close);
  if (backdrop) backdrop.addEventListener("click", close);

  if (confirmBtn) {
    confirmBtn.addEventListener("click", () => {
      confirmTravelSelection();
    });
  }

  if (searchInput) {
    // Filter as you type
    searchInput.addEventListener("input", (e) => {
      renderTravelList(e.target.value || "");
    });

    // Enter = confirm travel on selected item
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        confirmTravelSelection();
      }

      // Bonus: navigate with arrows up/down
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        moveTravelSelection(e.key === "ArrowDown" ? 1 : -1);
      }
    });
  }
}

function moveTravelSelection(direction) {
  const listEl = document.getElementById("travel-list");
  if (!listEl) return;

  const items = Array.from(listEl.querySelectorAll(".travel-item"));
  if (!items.length) return;

  let currentIndex = items.findIndex((btn) =>
    btn.classList.contains("travel-item-selected")
  );
  if (currentIndex === -1) currentIndex = 0;

  let nextIndex = currentIndex + direction;
  if (nextIndex < 0) nextIndex = items.length - 1;
  if (nextIndex >= items.length) nextIndex = 0;

  setSelectedTravelItem(items[nextIndex]);
}



function computeLevelRowProgress(levelDef) {
  if (!currentPlayer) return 0;

  const curLevel = Number(currentPlayer.level ?? 0);
  const curXp = Number(currentPlayer.xp ?? 0);
  const L = Number(levelDef.level ?? 0);

  // Player below this level => 0%
  if (curLevel < L) return 0;

  // Player above this level => 100%
  if (curLevel > L) return 100;

  // Player is exactly on this level => use xp_min/xp_max range
  const min = Number(levelDef.xp_min ?? 0);
  const max = Number(levelDef.xp_max ?? (min + 1));
  const span = Math.max(1, max - min);
  const pos = Math.max(0, Math.min(span, curXp - min));
  return Math.round((pos / span) * 100);
}

function renderLevelsList(levels) {
  const container = $("levelsModalBody");
  if (!container) return;

  if (!levels.length) {
    container.innerHTML = `<div class="text-muted small">Aucun niveau défini.</div>`;
    return;
  }

  container.innerHTML = levels
    .map((lvl) => {
      const pct = computeLevelRowProgress(lvl);
      const isCurrent =
        currentPlayer &&
        Number(currentPlayer.level ?? 0) === Number(lvl.level);

      const rewards = Array.isArray(lvl.rewards) ? lvl.rewards : [];

      // Vue compacte (pills)
      const rewardsCompactHtml = rewards.length
        ? rewards
            .map((r) => {
              const icon = getRewardIconPath(r);
              const label = formatRewardLabel(r);
              return `
                <div class="level-reward-pill">
                  ${icon ? `<img src="${icon}" alt="">` : ""}
                  <span>${label}</span>
                </div>
              `;
            })
            .join("")
        : `<span class="text-muted">Aucune récompense</span>`;

      const xpMin = lvl.xp_min ?? 0;
      const xpMax = lvl.x_max ?? lvl.xp_max ?? null; // compat petit bug possible
      const xpRequired = lvl.xp_required ?? xpMin;

      const xpRangeText = xpMax
        ? `XP ${xpMin} → ${xpMax}`
        : `XP ≥ ${xpMin}`;

      // Détails : on met en avant les rewards de type "card"
      const cardRewards = rewards.filter((r) => r.type === "card");
      const otherRewards = rewards.filter((r) => r.type !== "card");

const cardsDetailsHtml = cardRewards.length
  ? cardRewards
      .map((r) => {
        const icon = getRewardIconPath(r);
        const label = formatRewardLabel(r);
        return `
          <div class="level-card-detail">
            ${
              icon
                ? `<img src="${icon}"
                         alt="${r.label || r.key || "Carte"}"
                         class="clickable-img"
                         onclick="showImageViewer('${icon}')">`
                : ""
            }
            <div>
              <div class="level-card-text-main">${label}</div>
              <div class="level-card-text-sub">
                Carte débloquée à ce niveau.
              </div>
            </div>
          </div>
        `;
      })
      .join("")
  : `<div class="text-muted small">Pas de carte spécifique à ce niveau.</div>`;


      const otherRewardsHtml = otherRewards.length
        ? otherRewards
            .map((r) => `<li>${formatRewardLabel(r)}</li>`)
            .join("")
        : `<li class="text-muted">Aucune autre récompense.</li>`;

        return `
          <div class="level-row ${isCurrent ? "current" : ""}" data-level="${lvl.level}">
            <div class="level-row-main">
              <div class="d-flex align-items-center justify-content-center">
                <div class="level-badge">${lvl.level}</div>
              </div>

              <div>
                <div class="level-xp-range">
                  ${xpRangeText}
                  ${isCurrent ? `<span class="text-info ms-1">(niveau actuel)</span>` : ""}
                </div>
                <div class="level-progress-bar">
                  <div class="level-progress-fill" style="width: ${pct}%;"></div>
                </div>
              </div>

              <div class="level-rewards">
                ${rewardsCompactHtml}
              </div>

              <div class="level-chevron">
                <span class="level-chevron-icon">▼</span>
              </div>
            </div>

            <!-- 🔽 Partie accordéon avec détails -->
            <div class="level-details">
              <div class="level-details-inner">
                <div>
                  <div class="level-details-block-title">Cartes débloquées</div>
                  ${cardsDetailsHtml}
                </div>
                <div>
                  <div class="level-details-block-title">Autres récompenses</div>
                  <ul class="mb-0">
                    ${otherRewardsHtml}
                  </ul>
                </div>
              </div>
            </div>
          </div>
        `;


    })
    .join("");

  setupLevelsAccordion();
}

function setupLevelsAccordion() {
  const rows = document.querySelectorAll(".level-row");
  if (!rows.length) return;

  rows.forEach((row) => {
    row.addEventListener("click", () => {
      const alreadyExpanded = row.classList.contains("expanded");

      // Si tu veux un vrai accordéon (une seule ouverte à la fois)
      rows.forEach((r) => r.classList.remove("expanded"));

      if (!alreadyExpanded) {
        row.classList.add("expanded");
      }
    });
  });
}

function initNotebookUI() {
  // Notebook is fully handled by static/GAME_UI/js/notebook_app.js
  // Keep this no-op to avoid double event wiring.
}