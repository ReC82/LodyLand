/* 
  File: static/GAME_UI/js/craft_app.js
  Purpose: Craft UI logic (popup, ingredients, recipes, drag & drop, perform craft).
  Notes:
  - Uses http() and $() helpers from common.js / game_app.js.
*/

/* global http, $ */

// Global craft state
// ============================================================================
let craftState = {
  recipes: [],
  selectedRecipe: null,
  tableLevel: 0,        // 0: no table, 1: 1x3, 2: 2x3, 3: 3x3

  inventory: [],        // player stock from /api/state
  resourceDefs: [],     // ResourceDef list from /api/state

  expectedSlots: [],    // pattern decoded from recipe
  filledSlots: [],      // what the player dropped in slots

  showRecipes: false,   // toggle ingredients / recipes panel

  // NEW: craft job state
  activeJob: null,          // current craft job for the craft table
  jobRemainingSeconds: 0,   // countdown for UI
};

// NEW: timer id for countdown
let craftJobTimerId = null;


// Format seconds as "mm:ss"
function formatSecondsMMSS(total) {
  const sec = Math.max(0, parseInt(total, 10) || 0);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

// Update the craft job status UI
// Update the craft job status UI
// Update the craft job status UI
function renderCraftJobStatus() {
  const box = $("craft-job-status");
  const textEl = $("craft-job-status-text");
  if (!box || !textEl) return;

  const job = craftState.activeJob;

  // Si pas de job ou job terminé -> on cache
  if (!job || !isCraftJobActive()) {
    box.classList.add("d-none");
    textEl.textContent = "";
    return;
  }

  const label = job.label || job.item_key || "Item";

  const remainingUnits =
    job.remaining_units != null
      ? job.remaining_units
      : Math.max(
          0,
          (job.quantity_total || 0) - (job.quantity_done || 0)
        );

  const serverRemaining =
    typeof job.seconds_remaining_total === "number"
      ? job.seconds_remaining_total
      : 0;

  const sec =
    craftState.jobRemainingSeconds > 0
      ? craftState.jobRemainingSeconds
      : serverRemaining;

  textEl.textContent =
    `Craft en cours : ${remainingUnits} × ${label} ` +
    `— temps restant : ${formatSecondsMMSS(sec)}`;

  box.classList.remove("d-none");
}

// Helper: determines if the current job is REALLY active (still crafting)
function isCraftJobActive() {
  const job = craftState.activeJob;
  if (!job) return false;

  const remainingUnits =
    job.remaining_units != null
      ? job.remaining_units
      : Math.max(
          0,
          (job.quantity_total || 0) - (job.quantity_done || 0)
        );

  const serverRemaining =
    typeof job.seconds_remaining_total === "number"
      ? job.seconds_remaining_total
      : 0;

  const sec =
    craftState.jobRemainingSeconds > 0
      ? craftState.jobRemainingSeconds
      : serverRemaining;

  return remainingUnits > 0 && sec > 0;
}


// Setup / reset the local countdown based on activeJob
function setupCraftJobTimerFromState() {
  // Clear previous timer
  if (craftJobTimerId) {
    clearInterval(craftJobTimerId);
    craftJobTimerId = null;
  }

  const job = craftState.activeJob;

  // Si pas de job ou job déjà fini => on nettoie l'état
  if (!job || !isCraftJobActive()) {
    craftState.activeJob = null;
    craftState.jobRemainingSeconds = 0;
    renderCraftJobStatus();
    return;
  }

  const serverRemaining =
    typeof job.seconds_remaining_total === "number"
      ? job.seconds_remaining_total
      : 0;

  craftState.jobRemainingSeconds = Math.max(
    0,
    parseInt(serverRemaining, 10) || 0
  );

  // Premier rendu immédiat
  renderCraftJobStatus();

  if (craftState.jobRemainingSeconds <= 0) {
    craftState.activeJob = null;
    renderCraftJobStatus();
    return;
  }

  // 🔁 On garde en mémoire à quel moment on a fait la dernière sync
  let lastSyncRemaining = craftState.jobRemainingSeconds;

  craftJobTimerId = setInterval(() => {
    if (craftState.jobRemainingSeconds > 0) {
      craftState.jobRemainingSeconds -= 1;
      renderCraftJobStatus();

      // 👉 Toutes les 5 secondes, on re-sync avec le backend
      if (
        craftState.jobRemainingSeconds > 0 &&
        lastSyncRemaining - craftState.jobRemainingSeconds >= 5
      ) {
        lastSyncRemaining = craftState.jobRemainingSeconds;

        // On relit /api/state, ce qui :
        //  - met à jour le job (remaining_units, quantity_done, seconds_remaining_total)
        //  - met à jour l'inventaire et les items
        refreshCraftData()
          .catch((e) => console.error("[craft] refreshCraftData (poll) error:", e));
        // ⚠️ refreshCraftData va rappeler setupCraftJobTimerFromState
        // et donc recréer un nouveau timer, donc on stoppe celui-ci.
        clearInterval(craftJobTimerId);
        craftJobTimerId = null;
        return;
      }

      // Fin du timer local
      if (craftState.jobRemainingSeconds <= 0) {
        clearInterval(craftJobTimerId);
        craftJobTimerId = null;

        // Dernière resync pour clôturer le job et rafraîchir inventaire + items
        refreshCraftData().catch((e) => {
          console.error("[craft] refreshCraftData after timer error:", e);
        });
      }
    } else {
      clearInterval(craftJobTimerId);
      craftJobTimerId = null;
    }
  }, 1000);
}






// ============================================================================
// Helpers: grid size & rebuild
// ============================================================================
function getCraftGridSlotCount() {
  const level = craftState.tableLevel || 0;
  if (level <= 0) return 0;
  if (level === 1) return 3;   // 1x3
  if (level === 2) return 6;   // 2x3
  return 9;                    // 3x3
}

function rebuildCraftGrid() {
  const grid = document.querySelector(".craft-grid");
  if (!grid) return;

  const slotsCount = getCraftGridSlotCount();

  craftState.expectedSlots = new Array(slotsCount).fill(null);
  craftState.filledSlots   = new Array(slotsCount).fill(null);

  grid.innerHTML = "";

  for (let i = 0; i < slotsCount; i++) {
    const slotEl = document.createElement("div");
    slotEl.className = "craft-slot";
    slotEl.dataset.slot = String(i);

    // Enable drag & drop on slots
    slotEl.addEventListener("dragover", (e) => e.preventDefault());
    slotEl.addEventListener("drop", (e) => onSlotDropped(e, i));

    grid.appendChild(slotEl);
  }

  renderCraftSlots();
}


// ============================================================================
// Init
// ============================================================================
function initCraftUI() {
  const modalEl          = $("craft-modal");
  const openBtn          = $("craft-open-btn");
  const closeBtn         = $("craft-close-btn");
  const performBtn       = $("craft-perform-btn");
  const recipesToggleBtn = $("craft-recipes-toggle-btn");

  // Only modal, openBtn and performBtn are strictly required
  if (!modalEl || !openBtn || !performBtn) {
    console.warn("[craft] Missing essential DOM elements for craft UI.");
    return;
  }

  if (!closeBtn) {
    console.warn("[craft] No close button found for craft modal. (Optional)");
  }

  // Open modal
  openBtn.addEventListener("click", () => openCraftModal());

  // Close modal (if close button exists)
  if (closeBtn) {
    closeBtn.addEventListener("click", () => closeCraftModal());
  }

  // Backdrop closes
  const backdrop = modalEl.querySelector(".craft-modal-backdrop");
  if (backdrop) {
    backdrop.addEventListener("click", () => closeCraftModal());
  }

  // Toggle recipes panel (book icon)
  if (recipesToggleBtn) {
    recipesToggleBtn.addEventListener("click", () => {
      craftState.showRecipes = !craftState.showRecipes;
      console.log("[craft] toggle recipes, showRecipes =", craftState.showRecipes);
      updateCraftPanelsVisibility();
    });
  } else {
    console.warn("[craft] craft-recipes-toggle-btn not found.");
  }

  // Perform craft
  performBtn.addEventListener("click", onCraftPerformClicked);

  // Initial load (state + grid + recipes)
  refreshCraftData().catch((e) => {
    console.error("[craft] refreshCraftData error:", e);
  });
}

// Auto-init even if script is loaded at end of <body>
/*
(function () {
  try {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initCraftUI);
    } else {
      initCraftUI();
    }
  } catch (e) {
    console.error("[craft] initCraftUI error:", e);
  }
})();*/


// ============================================================================
// Open / Close modal
// ============================================================================
function openCraftModal() {
  const modalEl = $("craft-modal");
  if (!modalEl) return;

  craftState.showRecipes = false;
  craftState.selectedRecipe = null;

  modalEl.classList.add("is-open");

  // Reload state when opening
  refreshCraftData().catch((e) => {
    console.error("[craft] refreshCraftData (open) error:", e);
  });
}

function closeCraftModal() {
  const modalEl = $("craft-modal");
  if (!modalEl) return;

  modalEl.classList.remove("is-open");
  craftState.selectedRecipe = null;
  craftState.filledSlots = craftState.filledSlots.map(() => null);
  updateCraftSelectionUI();
  renderCraftSlots();
}


// ============================================================================
// Load state + recipes
// ============================================================================
async function refreshCraftData() {
  // 1) Load player state
  const stateRes = await http("GET", "/api/state");
  if (!stateRes.ok) {
    console.error("[craft] Failed to load /api/state:", stateRes);
    return;
  }
  const state = stateRes.data || {};

  const craftBlock = state.craft || {};
  craftState.tableLevel =
    typeof craftBlock.craft_table_level === "number"
      ? craftBlock.craft_table_level
      : 0;

  console.log("[craft] tableLevel from /api/state =", craftState.tableLevel);
  // Resource definitions (icons, labels, etc.)
  craftState.resourceDefs =
    state.resources || state.resource_defs || state.resourceDefinitions || [];

  // Item definitions (from state.items)
  const itemsFromState = state.items || [];
  craftState.itemDefs = {};
  itemsFromState.forEach((it) => {
    const key = it.item_key;
    if (!key) return;
    craftState.itemDefs[key] = {
      key: key,
      label: it.label_fr || it.label_en || key,
      icon: it.icon || null,
      type: it.type || "item",
      category: it.category || null,
    };
  });

  // Build a merged inventory for the craft table:
  //  - resources from state.inventory
  //  - items from state.items
  const resInv = (state.inventory || []).map((rs) => ({
    key: rs.resource || rs.key,
    qty:
      typeof rs.qty === "number"
        ? rs.qty
        : typeof rs.quantity === "number"
        ? rs.quantity
        : 0,
    kind: "resource",
  }));

  const itemsInv = itemsFromState.map((it) => ({
    key: it.item_key,
    quantity: it.qty || it.quantity || 0,
    kind: "item",
  }));

  craftState.inventory = [...resInv, ...itemsInv];

  // NEW: load active job from backend state
  craftState.activeJob = craftBlock.active_job || null;
  console.log("[craft] activeJob from /api/state =", craftState.activeJob);


  const levelSpan = $("craft-table-level");
  if (levelSpan) {
    levelSpan.textContent = craftState.tableLevel;
  }

  // Rebuild grid according to table level
  rebuildCraftGrid();

  // FAB craft button visible only if tableLevel > 0
  const craftBtn = $("craft-open-btn");
  if (craftBtn) {
    craftBtn.style.display = craftState.tableLevel > 0 ? "" : "none";
  }

  // Render ingredients
  renderCraftIngredients(craftState.inventory);

  // NEW: update job status + timer
  setupCraftJobTimerFromState();

  // 2) Load recipes
  const recipesRes = await http(
    "GET",
    "/api/craft/recipes?location=craft_table"
  );

  if (!recipesRes.ok) {
    console.error("[craft] Failed to load /api/craft/recipes:", recipesRes);
    renderCraftRecipes([]);
    updateCraftPanelsVisibility();
    return;
  }

  const payload = recipesRes.data || {};
  const recipes = payload.recipes || [];

  craftState.recipes = recipes;

  renderCraftRecipes(craftState.recipes);
  updateCraftPanelsVisibility();
}



// ============================================================================
// Render ingredients panel (resources + crafted items)
// ============================================================================
function renderCraftIngredients(inventory) {
  const listEl = $("craft-ingredients-list");
  if (!listEl) return;

  listEl.innerHTML = "";

  if (!Array.isArray(inventory) || inventory.length === 0) {
    const empty = document.createElement("div");
    empty.textContent = "Aucune ressource.";
    empty.style.color = "#9ca3af";
    empty.style.fontSize = "0.85rem";
    listEl.appendChild(empty);
    return;
  }

  inventory.forEach((entry) => {
    const key = entry.key || entry.resource || "";
    if (!key) return;

    const kind = (entry.kind || "resource").toLowerCase();

    let labelText = key;
    let iconPath = null;

    // --- Si c'est un item crafté : on va chercher dans craftState.itemDefs ---
    if (kind === "item") {
      const itemDefs = craftState.itemDefs || {};
      const def = itemDefs[key] || null;
      if (def) {
        labelText = def.label || key;
        iconPath = def.icon || null;
      }
    } else {
      // --- Sinon : c'est une ressource classique ---
      const defs = craftState.resourceDefs || [];
      const def = defs.find((d) => d.key === key) || null;
      if (def) {
        labelText = def.label || key;
        iconPath = def.icon || null;
      }
    }

    const qtyVal =
      typeof entry.qty === "number"
        ? entry.qty
        : typeof entry.quantity === "number"
        ? entry.quantity
        : 0;

    const item = document.createElement("div");
    // Classe de base + surcouche dorée si c'est un item crafté
    item.className =
      "craft-ingredient-item" +
      (kind === "item" ? " craft-ingredient-item--crafted" : "");
    item.dataset.key = key;
    item.dataset.kind = kind;

    // Make ingredient draggable
    item.draggable = true;
    item.addEventListener("dragstart", (e) => {
      // If a craft job is active, we lock the grid
      if (isCraftJobActive()) {
        e.preventDefault();
        const errEl = $("craft-error");
        if (errEl) {
          errEl.style.display = "block";
          errEl.textContent =
            "Un craft est déjà en cours. Attends la fin avant de lancer un autre craft.";
        }
        return;
      }
      e.dataTransfer.setData("text/plain", key);
    });

    const left = document.createElement("div");
    left.className = "craft-ingredient-name";

    const iconWrap = document.createElement("div");
    iconWrap.className = "craft-ingredient-icon";

    if (iconPath) {
      const img = document.createElement("img");
      let src = iconPath;
      if (!src.startsWith("/") && !src.startsWith("http")) {
        src = "/" + src.replace(/^\/+/, "");
      }
      img.src = src;
      img.alt = labelText;
      iconWrap.appendChild(img);
    } else {
      iconWrap.textContent = kind === "item" ? "★" : "📦";
    }

    const label = document.createElement("div");
    label.textContent = labelText;

    left.appendChild(iconWrap);
    left.appendChild(label);

    const right = document.createElement("div");
    right.className = "craft-ingredient-qty";
    right.textContent = "x" + qtyVal;

    item.appendChild(left);
    item.appendChild(right);

    listEl.appendChild(item);
  });
}




// ============================================================================
// Render recipes list
// ============================================================================
function renderCraftRecipes(recipes) {
  const listEl = $("craft-recipes-list");
  if (!listEl) return;

  listEl.innerHTML = "";

  if (!recipes || recipes.length === 0) {
    const empty = document.createElement("div");
    empty.textContent = "Aucune recette disponible.";
    empty.style.color = "#9ca3af";
    empty.style.fontSize = "0.85rem";
    listEl.appendChild(empty);
    craftState.selectedRecipe = null;
    updateCraftSelectionUI();
    return;
  }

  // Sort: unlocked first, then by label
  const sorted = [...recipes].sort((a, b) => {
    const aUn = a.is_unlocked ? 1 : 0;
    const bUn = b.is_unlocked ? 1 : 0;
    if (aUn !== bUn) return bUn - aUn;

    const aLabel = a.label || a.item_key || "";
    const bLabel = b.label || b.item_key || "";
    return aLabel.localeCompare(bLabel);
  });

  sorted.forEach((r) => {
    const item = document.createElement("div");
    item.className = "craft-recipe-item";
    item.dataset.itemKey = r.item_key;

    const iconWrap = document.createElement("div");
    iconWrap.className = "craft-recipe-icon";

    if (r.icon) {
      const img = document.createElement("img");
      let src = r.icon;
      if (!src.startsWith("/") && !src.startsWith("http")) {
        src = "/" + src.replace(/^\/+/, "");
      }
      img.src = src;
      img.alt = r.label || r.item_key;
      iconWrap.appendChild(img);
    } else {
      iconWrap.textContent = "?";
    }

    const textWrap = document.createElement("div");
    const label = document.createElement("div");
    label.textContent = r.label || r.item_key;
    label.style.fontSize = "0.9rem";

    const sub = document.createElement("div");
    sub.textContent = "Tps: " + (r.recipe?.craft_time_seconds || 0) + "s";
    sub.style.fontSize = "0.75rem";
    sub.style.color = "#9ca3af";

    textWrap.appendChild(label);
    textWrap.appendChild(sub);

    if (!r.is_unlocked) {
      item.classList.add("craft-recipe-locked");
      item.style.opacity = "0.45";

      const lockMsg = document.createElement("div");
      lockMsg.textContent = "Recette verrouillée";
      lockMsg.style.fontSize = "0.7rem";
      lockMsg.style.color = "#f97373";
      textWrap.appendChild(lockMsg);
    }

    item.appendChild(iconWrap);
    item.appendChild(textWrap);

    // Click: select recipe + decode pattern into grid
    item.addEventListener("click", () => {
      // Si un job est actif, on ne laisse pas changer de recette
      if (isCraftJobActive()) {
        const errEl = $("craft-error");
        if (errEl) {
          errEl.style.display = "block";
          errEl.textContent =
            "Un craft est en cours sur cette table. Termine-le avant de choisir une nouvelle recette.";
        }
        return;
      }

      craftState.selectedRecipe = r;
      decodeRecipeIntoSlots(r);
      renderCraftSlots();
      updateCraftSelectionUI();
    });

    listEl.appendChild(item);
  });

  updateCraftSelectionUI();
}


// ============================================================================
// Decode recipe → expectedSlots (supports 1x3 / 2x3 / 3x3)
// ============================================================================
function decodeRecipeIntoSlots(r) {
  const cols = 3;

  const maxRowsByLevel = (() => {
    const lvl = craftState.tableLevel || 0;
    if (lvl <= 0) return 0;
    if (lvl === 1) return 1;
    if (lvl === 2) return 2;
    return 3;
  })();

  if (!r || !r.recipe || !Array.isArray(r.recipe.pattern)) {
    craftState.expectedSlots = [];
    craftState.filledSlots   = [];
    return;
  }

  const pattern = r.recipe.pattern;
  const legend  = r.recipe.legend || {};

  const rows = Math.min(pattern.length, maxRowsByLevel);
  const slotsCount = rows * cols;

  craftState.expectedSlots = new Array(slotsCount).fill(null);
  craftState.filledSlots   = new Array(slotsCount).fill(null);

  for (let row = 0; row < rows; row++) {
    const patternRow = pattern[row] || "";

    for (let col = 0; col < cols; col++) {
      const idx = row * cols + col;
      const symbol = patternRow[col] || ".";

      if (symbol === ".") {
        craftState.expectedSlots[idx] = null;
      } else if (legend[symbol]) {
        craftState.expectedSlots[idx] = {
          key: legend[symbol].key,
          qty: legend[symbol].quantity || 1,
        };
      } else {
        craftState.expectedSlots[idx] = null;
      }
    }
  }
  console.log("[craft] expectedSlots =", craftState.expectedSlots);
}


// ============================================================================
// Render craft slots (expected + filled, avec icône ghost pour les attentes)
// ============================================================================
function renderCraftSlots() {
  const slots = document.querySelectorAll(".craft-slot");

  slots.forEach((el) => {
    const idx = parseInt(el.dataset.slot, 10);
    if (Number.isNaN(idx)) return;

    const expected = craftState.expectedSlots[idx];
    const filled   = craftState.filledSlots[idx];

    el.innerHTML = "";

    // Pas d'attente sur ce slot → slot "vide" (gris)
    if (!expected) {
      el.style.opacity = "0.25";
      return;
    }

    el.style.opacity = "1";

    // ----------------------------------------------------------------------
    // 1) CAS REMPLI : on affiche l'icône "pleine" de l'item / ressource
    // ----------------------------------------------------------------------
    if (filled && filled.key) {
      let iconPath = null;

      // D'abord: item crafté ?
      const itemDef = craftState.itemDefs?.[filled.key];
      if (itemDef && itemDef.icon) {
        iconPath = itemDef.icon;
      } else {
        // Sinon: ressource classique
        const resDef = (craftState.resourceDefs || []).find(
          (d) => d.key === filled.key
        );
        if (resDef && resDef.icon) {
          iconPath = resDef.icon;
        }
      }

      if (iconPath) {
        const img = document.createElement("img");
        img.className = "craft-slot-img";

        let src = iconPath;
        if (!src.startsWith("/") && !src.startsWith("http")) {
          src = "/" + src.replace(/^\/+/, "");
        }

        img.src = src;
        img.alt = filled.key;
        el.appendChild(img);
      } else {
        const placeholder = document.createElement("div");
        placeholder.className = "craft-slot-placeholder";
        placeholder.textContent = filled.key;
        el.appendChild(placeholder);
      }

      return; // slot rempli → on s'arrête ici
    }

    // ----------------------------------------------------------------------
    // 2) CAS VIDE MAIS AVEC INGREDIENT ATTENDU :
    //    on affiche l'icône "ghost" + un badge xQty
    // ----------------------------------------------------------------------
    let iconPath = null;
    let labelText = expected.key || "";

    // D'abord: l'item crafté ?
    const ghostItemDef = craftState.itemDefs?.[expected.key];
    if (ghostItemDef) {
      labelText = ghostItemDef.label || labelText;
      iconPath = ghostItemDef.icon || iconPath;
    }

    // Sinon: ressource classique
    if (!iconPath) {
      const ghostResDef = (craftState.resourceDefs || []).find(
        (d) => d.key === expected.key
      );
      if (ghostResDef) {
        labelText = ghostResDef.label || labelText;
        iconPath = ghostResDef.icon || iconPath;
      }
    }

    const wrapper = document.createElement("div");
    wrapper.className = "craft-slot-ghost";

    if (iconPath) {
      const img = document.createElement("img");
      img.className = "craft-slot-img craft-slot-img-ghost";

      let src = iconPath;
      if (!src.startsWith("/") && !src.startsWith("http")) {
        src = "/" + src.replace(/^\/+/, "");
      }

      img.src = src;
      img.alt = labelText;
      wrapper.appendChild(img);
    } else {
      // Fallback texte si pas d'icône
      const placeholder = document.createElement("div");
      placeholder.className =
        "craft-slot-placeholder craft-slot-placeholder-ghost";
      placeholder.textContent = labelText;
      wrapper.appendChild(placeholder);
    }

    // Petit badge pour la quantité attendue
    const badge = document.createElement("div");
    badge.className = "craft-slot-qty-badge";
    badge.textContent = "x" + (expected.qty || 1);
    wrapper.appendChild(badge);

    el.appendChild(wrapper);
  });
}



// ============================================================================
// Drag & Drop handlers
// ============================================================================
function onSlotDropped(e, slotIndex) {
  e.preventDefault();
  const key = e.dataTransfer.getData("text/plain");
  if (!key) return;

  const expected = craftState.expectedSlots[slotIndex];
  if (!expected) return;
  console.log("[craft] dropping", key, "into slot", slotIndex, "expected =", expected);

  if (expected.key !== key) {
    flashSlotError(slotIndex);
    return;
  }

  craftState.filledSlots[slotIndex] = { key: key };

  renderCraftSlots();
  updateCraftSelectionUI();
}

function flashSlotError(idx) {
  const slot = document.querySelector('.craft-slot[data-slot="' + idx + '"]');
  if (!slot) return;

  const oldBorder = slot.style.borderColor;
  slot.style.borderColor = "#ef4444";
  setTimeout(() => {
    slot.style.borderColor = oldBorder || "";
  }, 300);
}


// ============================================================================
// Panels visibility (ingredients / recipes)
//  → version "bourrin" avec !important pour écraser tout le CSS
// ============================================================================
function updateCraftPanelsVisibility() {
  const ingredientsPanel = $("craft-ingredients-panel");
  const recipesPanel     = $("craft-recipes-panel");
    console.log("Updating craft panels visibility...");
  if (!ingredientsPanel || !recipesPanel) return;
    console.log("ingredientsPanels =", ingredientsPanel, "recipesPanel =", recipesPanel);

  console.log("craftState.showRecipes =", craftState.showRecipes);

  if (craftState.showRecipes) {
    console.log("Showing recipes panel, hiding ingredients panel.");
    ingredientsPanel.style.display = "none";
    recipesPanel.style.display     = "block";
  } else {
    console.log("Showing ingredients panel, hiding recipes panel.");
    ingredientsPanel.style.display = "block";
    recipesPanel.style.display     = "none";
  }
}


// ============================================================================
// Selection UI + enable/disable craft button
// ============================================================================
function updateCraftSelectionUI() {
  const performBtn = $("craft-perform-btn");
  const errEl      = $("craft-error");
  const successEl  = $("craft-success");

  if (errEl) {
    errEl.style.display = "none";
    errEl.textContent = "";
  }
  if (successEl) {
    successEl.style.display = "none";
    successEl.textContent = "";
  }

  // Highlight selected recipe in list
  const listEl = $("craft-recipes-list");
  if (listEl) {
    const items = listEl.querySelectorAll(".craft-recipe-item");
    items.forEach((el) => {
      const key = el.getAttribute("data-itemKey");
      if (
        craftState.selectedRecipe &&
        key === craftState.selectedRecipe.item_key
      ) {
        el.classList.add("is-selected");
      } else {
        el.classList.remove("is-selected");
      }
    });
  }

  if (!performBtn) return;

  // 🔒 NEW: si un job est actif, on verrouille le bouton
  if (isCraftJobActive()) {
    performBtn.disabled = true;
    return;
  }

  // No recipe selected
  if (!craftState.selectedRecipe) {
    performBtn.disabled = true;
    return;
  }

  // No table => cannot craft
  if (!craftState.tableLevel || craftState.tableLevel <= 0) {
    performBtn.disabled = true;
    return;
  }

  // Recipe is locked (level, card, table, etc.) => no craft
  if (!craftState.selectedRecipe.is_unlocked) {
    performBtn.disabled = true;
    return;
  }

  // All expected slots must be filled with the correct key
  console.log(
    "[craft] updateUI selected=",
    !!craftState.selectedRecipe,
    "expected=",
    craftState.expectedSlots,
    "filled=",
    craftState.filledSlots
  );
  const allGood = craftState.expectedSlots.every((exp, i) => {
    if (!exp) return true;
    const filled = craftState.filledSlots[i];
    return filled && filled.key === exp.key;
  });

  performBtn.disabled = !allGood;
}



// ============================================================================
// Perform craft
// ============================================================================
async function onCraftPerformClicked() {
  if (!craftState.selectedRecipe) return;

  const performBtn = $("craft-perform-btn");
  const errEl      = $("craft-error");
  const successEl  = $("craft-success");
  const qtyInput   = $("craft-quantity-input");

  if (errEl) {
    errEl.style.display = "none";
    errEl.textContent = "";
  }
  if (successEl) {
    successEl.style.display = "none";
    successEl.textContent = "";
  }

  // 🔒 NEW: empêcher un deuxième craft si un job est déjà actif
  if (isCraftJobActive()) {
    if (errEl) {
      errEl.style.display = "block";
      errEl.textContent =
        "Un craft est déjà en cours. Attends sa fin avant de lancer un autre craft.";
    }
    return;
  }

  // Quantity
  let times = 1;
  if (qtyInput) {
    const v = parseInt(qtyInput.value, 10);
    times = Number.isNaN(v) || v < 1 ? 1 : v;
    qtyInput.value = String(times);
  }

  if (performBtn) {
    performBtn.disabled = true;
  }

  const itemKey = craftState.selectedRecipe.item_key;

  const payload = {
    item_key: itemKey,
    craft_location: "craft_table",
    times: times,
  };

  console.log("[craft] perform =>", {
    ...payload,
    filledSlots: craftState.filledSlots,
    expectedSlots: craftState.expectedSlots,
  });

  const res = await http("POST", "/api/craft/perform", payload);

  if (!res.ok) {
    console.error("[craft] perform error:", res);
    if (performBtn) {
      performBtn.disabled = false;
    }
    if (errEl) {
      errEl.style.display = "block";

      const data = res.data || {};
      const code = data.error || "";

      if (code === "not_enough_resources") {
        const missing = data.missing || {};
        const parts = Object.entries(missing).map(
          ([k, v]) => v + " x " + k
        );
        errEl.textContent =
          "Pas assez de ressources: " + (parts.join(", ") || "inconnu");
      } else if (code === "craft_locked") {
        errEl.textContent = "Recette verrouillée.";
      } else if (code === "craft_table_too_low") {
        errEl.textContent = "Table de craft de niveau insuffisant.";
      } else if (code === "craft_in_progress") {
        errEl.textContent =
          "Un craft est déjà en cours sur cette table.";
      } else {
        errEl.textContent = "Erreur lors du craft.";
      }
    }
    return;
  }

  const data = res.data || {};
  const crafted = data.crafted_item || {};
  const delayed = !!data.delayed;

  // Success
  if (successEl) {
    const qty = crafted.quantity || times;
    const label =
      crafted.label ||
      crafted.item_key ||
      itemKey;

    successEl.style.display = "block";
    if (delayed) {
      successEl.textContent =
        "Craft lancé : x" + qty + " " + label + " (en cours...)";
    } else {
      successEl.textContent =
        "Craft réussi: x" + qty + " " + label;
    }
  }

  // Refresh ingredients, jobs & timer
  await refreshCraftData();

  // Reset filled slots but keep pattern for the selected recipe
  craftState.filledSlots = new Array(craftState.expectedSlots.length).fill(null);
  renderCraftSlots();

  // L'état du bouton sera recalculé par updateCraftSelectionUI (appelé depuis renderCraftRecipes)
}
