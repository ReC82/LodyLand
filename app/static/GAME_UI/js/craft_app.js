/* 
  File: static/GAME_UI/js/craft_app.js
  Purpose: Craft UI logic (popup, ingredients, recipes, drag & drop, perform craft).
  Notes:
  - Uses http() and $() helpers from common.js / game_app.js.
*/

/* global http, $ */

// ============================================================================
// Global craft state
// ============================================================================
let craftState = {
  recipes: [],
  selectedRecipe: null,

  // Craft table level:
  // 0: no table, 1: 1x3, 2: 2x3, 3: 3x3
  tableLevel: 0,

  // Player inventory from /api/state
  inventory: [],

  // ResourceDef list from /api/state
  resourceDefs: [],

  // Pattern decoded from recipe
  expectedSlots: [],

  // What the player dropped in slots
  filledSlots: [],

  // Toggle ingredients / recipes panel
  showRecipes: false,

  // Craft job state (single job per table)
  activeJob: null,        // current craft job
  jobRemainingSeconds: 0, // local countdown for UI

  // Filters (text input)
  ingredientsFilter: "",
  recipesFilter: "",
};

// Timer id for craft job countdown
let craftJobTimerId = null;

// Currently dragged ingredient key (for slot hover highlight)
let currentDraggedKey = null;


// ============================================================================
// Mobile / touch helpers
// ============================================================================

// Détection simpliste d’un device tactile
const isTouchDevice =
  ("ontouchstart" in window) || (navigator.maxTouchPoints || 0) > 0;

// Petit tooltip pour afficher le nom de l’ingrédient sur mobile
let craftMobileTooltipTimeout = null;

function showCraftMobileTooltip(text) {
  let tip = document.getElementById("craft-mobile-tooltip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "craft-mobile-tooltip";
    tip.className = "craft-mobile-tooltip";
    document.body.appendChild(tip);
  }

  tip.textContent = text;
  tip.classList.add("visible");

  if (craftMobileTooltipTimeout) {
    clearTimeout(craftMobileTooltipTimeout);
  }
  craftMobileTooltipTimeout = setTimeout(() => {
    tip.classList.remove("visible");
  }, 1500); // 1,5 seconde
}


// ============================================================================
// Generic helpers
// ============================================================================

/**
 * Format seconds as "mm:ss".
 */
function formatSecondsMMSS(total) {
  const sec = Math.max(0, parseInt(total, 10) || 0);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

// ============================================================================
// Craft status (top UI)
// ============================================================================

function setCraftStatus(text, tone) {
  const box = document.getElementById("craft-status");
  const textEl = document.getElementById("craft-status-text");
  if (!box || !textEl) return;

  // Reset tones
  box.classList.remove(
    "craft-status--neutral",
    "craft-status--running",
    "craft-status--error",
    "craft-status--success"
  );

  const t = (tone || "neutral").toLowerCase();
  box.classList.add("craft-status--" + t);

  textEl.textContent = text || "Aucun craft en cours.";
}


// ============================================================================
// Hover helpers for slots (currently not used directly)
// ============================================================================

function clearCraftSlotsHover() {
  const slots = document.querySelectorAll(".craft-slot");
  slots.forEach((s) => {
    s.classList.remove("craft-slot--droppable");
  });
}

function updateSlotHover(slotIndex, isOver) {
  const slot = document.querySelector(`.craft-slot[data-slot="${slotIndex}"]`);
  if (!slot) return;

  const expected = craftState.expectedSlots[slotIndex];
  if (!expected) {
    slot.classList.remove("craft-slot--droppable");
    return;
  }

  // Only highlight if the dragged key matches expected ingredient
  if (isOver && craftDragKey && craftDragKey === expected.key) {
    slot.classList.add("craft-slot--droppable");
  } else {
    slot.classList.remove("craft-slot--droppable");
  }
}


// ============================================================================
// Craft job status + timer
// ============================================================================

/**
 * Check if the current job is actually still active (units + seconds).
 */
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

/**
 * Update the craft job status UI box.
 */
function renderCraftJobStatus() {
  const job = craftState.activeJob;

  // No job running
  if (!job || !isCraftJobActive()) {
    setCraftStatus("Aucun craft en cours.", "neutral");
    return;
  }

  const label = job.label || job.item_key || "Item";

  const remainingUnits =
    job.remaining_units != null
      ? job.remaining_units
      : Math.max(0, (job.quantity_total || 0) - (job.quantity_done || 0));

  const serverRemaining =
    typeof job.seconds_remaining_total === "number"
      ? job.seconds_remaining_total
      : 0;

  const sec =
    craftState.jobRemainingSeconds > 0
      ? craftState.jobRemainingSeconds
      : serverRemaining;

  setCraftStatus(
    `Craft en cours : ${remainingUnits} × ${label} — temps restant : ${formatSecondsMMSS(sec)}`,
    "running"
  );
}


/**
 * Setup / reset local countdown from activeJob (including periodic resync).
 */
function setupCraftJobTimerFromState() {
  // Clear previous timer
  if (craftJobTimerId) {
    clearInterval(craftJobTimerId);
    craftJobTimerId = null;
  }

  const job = craftState.activeJob;

  // If no job or already finished → clean state
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

  // First render immediately
  renderCraftJobStatus();

  if (craftState.jobRemainingSeconds <= 0) {
    craftState.activeJob = null;
    renderCraftJobStatus();
    return;
  }

  // Keep track of last remaining seconds when we synced
  let lastSyncRemaining = craftState.jobRemainingSeconds;

  craftJobTimerId = setInterval(() => {
    if (craftState.jobRemainingSeconds > 0) {
      craftState.jobRemainingSeconds -= 1;
      renderCraftJobStatus();

      // Every 5 seconds, re-sync with backend (/api/state)
      if (
        craftState.jobRemainingSeconds > 0 &&
        lastSyncRemaining - craftState.jobRemainingSeconds >= 5
      ) {
        lastSyncRemaining = craftState.jobRemainingSeconds;

        // This will refresh job, inventory, etc.
        refreshCraftData()
          .catch((e) => console.error("[craft] refreshCraftData (poll) error:", e));

        // refreshCraftData will call setupCraftJobTimerFromState again
        // so we stop the current timer.
        clearInterval(craftJobTimerId);
        craftJobTimerId = null;
        return;
      }

      // End of local timer
      if (craftState.jobRemainingSeconds <= 0) {
        clearInterval(craftJobTimerId);
        craftJobTimerId = null;

        // Final resync to close job and update inventory/items
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

/**
 * Return number of slots according to table level.
 */
function getCraftGridSlotCount() {
  const level = craftState.tableLevel || 0;
  if (level <= 0) return 0;
  if (level === 1) return 3;   // 1x3
  if (level === 2) return 6;   // 2x3
  return 9;                    // 3x3
}

/**
 * Rebuild the craft grid DOM according to table level,
 * and wire drag/drop logic on slots.
 */
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

    // --- DRAG & DROP ON SLOTS ---

    // dragover: allow drop + highlight slot if key matches
    slotEl.addEventListener("dragover", (e) => {
      e.preventDefault();

      const expected = craftState.expectedSlots[i];
      if (!expected || !expected.key) {
        slotEl.classList.remove("craft-slot--droppable");
        return;
      }

      // If a craft job is active, do not allow drop
      if (craftState.activeJob) {
        slotEl.classList.remove("craft-slot--droppable");
        return;
      }

      // Highlight only if dragged ingredient matches expected key
      if (currentDraggedKey && currentDraggedKey === expected.key) {
        slotEl.classList.add("craft-slot--droppable");
      } else {
        slotEl.classList.remove("craft-slot--droppable");
      }
    });

    // dragleave: remove highlight
    slotEl.addEventListener("dragleave", () => {
      slotEl.classList.remove("craft-slot--droppable");
    });

    // drop: route to onSlotDropped + cleanup
    slotEl.addEventListener("drop", (e) => {
      slotEl.classList.remove("craft-slot--droppable");
      onSlotDropped(e, i);
    });

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

  // Filter inputs
  const ingredientsFilterInput = $("craft-ingredients-filter");
  const recipesFilterInput     = $("craft-recipes-filter");

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
      updateCraftSelectionUI();
    });
  } else {
    console.warn("[craft] craft-recipes-toggle-btn not found.");
  }

  // Perform craft / change panel
  performBtn.addEventListener("click", onCraftPerformClicked);

  // Filters
  if (ingredientsFilterInput) {
    ingredientsFilterInput.addEventListener("input", (e) => {
      craftState.ingredientsFilterText = (e.target.value || "").trim();
      renderCraftIngredients(craftState.inventory);
    });
  }

  if (recipesFilterInput) {
    recipesFilterInput.addEventListener("input", (e) => {
      craftState.recipesFilterText = (e.target.value || "").trim();
      renderCraftRecipes(craftState.recipes);
    });
  }

  // Initial load (state + grid + recipes)
  refreshCraftData().catch((e) => {
    console.error("[craft] refreshCraftData error:", e);
  });
}

// Auto-init, if needed (currently disabled)
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
})();
*/


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

  // Build merged inventory for craft table:
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
    qty: it.qty || it.quantity || 0,
    kind: "item",
  }));

  craftState.inventory = [...resInv, ...itemsInv];

  // Active job from backend state
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

  // Render ingredients (with filter)
  renderCraftIngredients(craftState.inventory);

  // Update job status + timer
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
// Layout helper
// ============================================================================

function isCraftMobileLayout() {
  return window.matchMedia("(max-width: 768px)").matches;
}

// ============================================================================
// Render ingredients panel (resources + crafted items) – grille carrée
// ============================================================================

function renderCraftIngredients(inventory) {
  const listEl = $("craft-ingredients-list");
  if (!listEl) return;

  // Classe pour activer la grille en CSS
  listEl.innerHTML = "";
  listEl.classList.add("craft-ingredients-grid");

  if (!Array.isArray(inventory) || inventory.length === 0) {
    const empty = document.createElement("div");
    empty.textContent = "Aucun ingrédient.";
    empty.style.color = "#9ca3af";
    empty.style.fontSize = "0.85rem";
    listEl.appendChild(empty);
    return;
  }

  const term = (craftState.ingredientsFilterText || "").toLowerCase().trim();

  inventory.forEach((entry) => {
    const key = entry.key || entry.resource || "";
    if (!key) return;

    const kind = (entry.kind || "resource").toLowerCase();

    let labelText = key;
    let iconPath = null;

    // Item crafté → itemDefs
    if (kind === "item") {
      const def = (craftState.itemDefs || {})[key] || null;
      if (def) {
        labelText = def.label || key;
        iconPath = def.icon || null;
      }
    } else {
      // Ressource → resourceDefs
      const defs = craftState.resourceDefs || [];
      const def = defs.find((d) => d.key === key) || null;
      if (def) {
        labelText = def.label || key;
        iconPath = def.icon || null;
      }
    }

    // Filtre texte
    if (term) {
      const searchStr = (labelText + " " + key).toLowerCase();
      if (!searchStr.includes(term)) {
        return;
      }
    }

    const qtyVal =
      typeof entry.qty === "number"
        ? entry.qty
        : typeof entry.quantity === "number"
        ? entry.quantity
        : 0;

    const item = document.createElement("div");
    item.className =
      "craft-ingredient-item" +
      (kind === "item" ? " craft-ingredient-item--crafted" : "");
    item.dataset.key = key;
    item.dataset.kind = kind;
    item.title = labelText; // tooltip natif desktop

    // Icône centrée
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
    item.appendChild(iconWrap);

    // Badge quantité vert en bas à droite
    const qtyBadge = document.createElement("div");
    qtyBadge.className = "craft-ingredient-qty-badge";
    qtyBadge.textContent = "x" + qtyVal;
    item.appendChild(qtyBadge);

    // --- Desktop : drag & drop ---
    if (!isCraftMobileLayout()) {
      item.draggable = true;

      item.addEventListener("dragstart", (e) => {
        if (craftState.activeJob) {
          e.preventDefault();
          const errEl = $("craft-error");
          if (errEl) {
            errEl.style.display = "block";
            errEl.textContent =
              "Un craft est déjà en cours. Attends la fin avant de lancer un autre craft.";
          }
          return;
        }
        currentDraggedKey = key;
        e.dataTransfer.setData("text/plain", key);
      });

      item.addEventListener("dragend", () => {
        currentDraggedKey = null;
        const slots = document.querySelectorAll(".craft-slot");
        slots.forEach((slot) =>
          slot.classList.remove("craft-slot--droppable")
        );
      });
    }

    // --- Mobile : simple clic → remplir un slot + petit toast ---
    item.addEventListener("click", () => {
      if (!craftState.selectedRecipe) return; // rien de sélectionné
      onIngredientClickedMobile(key);
      showCraftIngredientToast(labelText);
    });

    listEl.appendChild(item);
  });
}

// ============================================================================
// Mobile helpers: click ingrédient = remplir un slot compatible
// ============================================================================

function onIngredientClickedMobile(key) {
  if (craftState.activeJob) return;

  const expected = craftState.expectedSlots || [];
  const filled = craftState.filledSlots || [];

  if (!expected.length) return;

  let targetIndex = -1;

  for (let i = 0; i < expected.length; i++) {
    const exp = expected[i];
    if (!exp) continue;
    if (exp.key !== key) continue;
    if (!filled[i]) {
      targetIndex = i;
      break;
    }
  }

  if (targetIndex === -1) {
    // aucun slot compatible libre
    return;
  }

  craftState.filledSlots[targetIndex] = { key };
  renderCraftSlots();
  updateCraftSelectionUI();
}
let craftIngredientToastTimeout = null;

/**
 * Petit toast au centre haut du modal avec le nom de l’ingrédient (mobile).
 */
function showCraftIngredientToast(labelText) {
  let toast = document.querySelector(".craft-ingredient-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "craft-ingredient-toast";
    document.body.appendChild(toast);
  }

  toast.textContent = labelText;
  toast.classList.add("is-visible");

  if (craftIngredientToastTimeout) {
    clearTimeout(craftIngredientToastTimeout);
  }

  craftIngredientToastTimeout = setTimeout(() => {
    toast.classList.remove("is-visible");
  }, 1500);
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

  const term = (craftState.recipesFilterText || "").toLowerCase().trim();

  // 1) On NE GARDE QUE les recettes déverrouillées
  const unlocked = recipes.filter((r) => r.is_unlocked);

  if (unlocked.length === 0) {
    const empty = document.createElement("div");
    empty.textContent = "Aucune recette déverrouillée pour l’instant.";
    empty.style.color = "#9ca3af";
    empty.style.fontSize = "0.85rem";
    listEl.appendChild(empty);
    craftState.selectedRecipe = null;
    updateCraftSelectionUI();
    return;
  }

  // 2) Tri alpha sur le label
  const sorted = [...unlocked].sort((a, b) => {
    const aLabel = a.label || a.item_key || "";
    const bLabel = b.label || b.item_key || "";
    return aLabel.localeCompare(bLabel);
  });

  // 3) Filtre texte
  const filtered = term
    ? sorted.filter((r) => {
        const label = (r.label || r.item_key || "").toLowerCase();
        const key = (r.item_key || "").toLowerCase();
        const kind = (r.kind || "").toLowerCase();
        return (
          label.includes(term) ||
          key.includes(term) ||
          kind.includes(term)
        );
      })
    : sorted;

  if (filtered.length === 0) {
    const empty = document.createElement("div");
    empty.textContent = "Aucune recette ne correspond à ce filtre.";
    empty.style.color = "#9ca3af";
    empty.style.fontSize = "0.85rem";
    listEl.appendChild(empty);
    craftState.selectedRecipe = null;
    updateCraftSelectionUI();
    return;
  }

  filtered.forEach((r) => {
    const item = document.createElement("div");
    item.className = "craft-recipe-item";
    item.dataset.itemKey = r.item_key;

    // --- Icône à gauche ---
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

    // --- Ligne unique : "Nom  ·  8s" ---
    const mainLine = document.createElement("div");
    mainLine.className = "craft-recipe-mainline";

    const labelSpan = document.createElement("span");
    labelSpan.className = "craft-recipe-label";
    labelSpan.textContent = r.label || r.item_key;

    const timeSpan = document.createElement("span");
    timeSpan.className = "craft-recipe-time";
    const tps = r.recipe?.craft_time_seconds || 0;
    timeSpan.textContent = `${tps}s`;

    mainLine.appendChild(labelSpan);
    mainLine.appendChild(timeSpan);

    item.appendChild(iconWrap);
    item.appendChild(mainLine);

    // Click: sélection de la recette
    item.addEventListener("click", () => {
      if (craftState.activeJob) {
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
// Render craft slots (expected + filled, with ghost icons)
// ============================================================================

function renderCraftSlots() {
  const slots = document.querySelectorAll(".craft-slot");

  slots.forEach((el) => {
    const idx = parseInt(el.dataset.slot, 10);
    if (Number.isNaN(idx)) return;

    const expected = craftState.expectedSlots[idx];
    const filled   = craftState.filledSlots[idx];

    el.innerHTML = "";

    // No expected ingredient → "empty" grey slot
    if (!expected) {
      el.style.opacity = "0.25";
      return;
    }

    el.style.opacity = "1";

    // ----------------------------------------------------------------------
    // 1) FILLED CASE: show full icon (item or resource)
    // ----------------------------------------------------------------------
    if (filled && filled.key) {
      let iconPath = null;

      // Crafted item?
      const itemDef = craftState.itemDefs?.[filled.key];
      if (itemDef && itemDef.icon) {
        iconPath = itemDef.icon;
      } else {
        // Resource
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

      return; // slot filled → stop here
    }

    // ----------------------------------------------------------------------
    // 2) EMPTY BUT EXPECTED: show ghost icon + qty badge
    // ----------------------------------------------------------------------
    let iconPath = null;
    let labelText = expected.key || "";

    // Crafted item?
    const ghostItemDef = craftState.itemDefs?.[expected.key];
    if (ghostItemDef) {
      labelText = ghostItemDef.label || labelText;
      iconPath = ghostItemDef.icon || iconPath;
    }

    // Resource
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
      // Text fallback if no icon
      const placeholder = document.createElement("div");
      placeholder.className =
        "craft-slot-placeholder craft-slot-placeholder-ghost";
      placeholder.textContent = labelText;
      wrapper.appendChild(placeholder);
    }

    // Quantity badge
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

  // Do not allow drop if a craft job is running
  if (craftState.activeJob) {
    const errEl = $("craft-error");
    if (errEl) {
      errEl.style.display = "block";
      errEl.textContent =
        "Un craft est déjà en cours. Attends la fin avant de lancer un autre craft.";
    }
    return;
  }

  const key = e.dataTransfer.getData("text/plain") || currentDraggedKey;
  if (!key) return;

  const expected = craftState.expectedSlots[slotIndex];
  if (!expected) return;

  console.log(
    "[craft] dropping",
    key,
    "into slot",
    slotIndex,
    "expected =",
    expected
  );

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
// ============================================================================

function updateCraftPanelsVisibility() {
  const ingredientsPanel = $("craft-ingredients-panel");
  const recipesPanel     = $("craft-recipes-panel");

  console.log("Updating craft panels visibility...");
  if (!ingredientsPanel || !recipesPanel) return;

  console.log("ingredientsPanel =", ingredientsPanel, "recipesPanel =", recipesPanel);
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

  renderCraftJobStatus();

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

  // Button text depends on current panel
  if (craftState.showRecipes) {
    performBtn.textContent = "Crafter cette recette";
  } else {
    performBtn.textContent = "Craft";
  }

  // If a craft job is active, always disable button
  if (craftState.activeJob) {
    performBtn.disabled = true;
    return;
  }

  // --- CASE 1: Recipes panel ----------------------------------------------
  // Here the button is only a "continue" to ingredients, not a real POST yet.
  if (craftState.showRecipes) {
    if (!craftState.selectedRecipe) {
      performBtn.disabled = true;
    } else {
      performBtn.disabled = false;
    }
    return;
  }

  // --- CASE 2: Ingredients panel (normal craft flow) ----------------------

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

  // Recipe locked (level, card, table, etc.)
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
  const performBtn = $("craft-perform-btn");
  const qtyInput   = $("craft-quantity-input");

  // If a job is active → nothing to do
  if (craftState.activeJob) {
    setCraftStatus(
      "Un craft est déjà en cours. Attends sa fin avant de lancer un autre craft.",
      "error"
    );
    return;
  }

  // --- CASE 1: Recipes panel ----------------------------------------------
  // Here, "Crafter cette recette" only switches to ingredients panel.
  if (craftState.showRecipes) {
    if (!craftState.selectedRecipe) {
      // No recipe selected → nothing
      return;
    }

    craftState.showRecipes = false;
    updateCraftPanelsVisibility();
    updateCraftSelectionUI();
    return;
  }

  // --- CASE 2: Ingredients panel (launch craft) ---------------------------
  if (!craftState.selectedRecipe) return;

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

    const data = res.data || {};
    const code = data.error || "";

    if (code === "not_enough_resources") {
      const missing = data.missing || {};
      const parts = Object.entries(missing).map(([k, v]) => `${v} x ${k}`);
      setCraftStatus(
        "Pas assez de ressources: " + (parts.join(", ") || "inconnu"),
        "error"
      );
    } else if (code === "craft_locked") {
      setCraftStatus("Recette verrouillée.", "error");
    } else if (code === "craft_table_too_low") {
      setCraftStatus("Table de craft de niveau insuffisant.", "error");
    } else if (code === "craft_in_progress") {
      setCraftStatus("Un craft est déjà en cours sur cette table.", "error");
    } else {
      setCraftStatus("Erreur lors du craft.", "error");
    }

    return;
  }

  const data = res.data || {};
  const crafted = data.crafted_item || {};
  const delayed = !!data.delayed;

  // Reset quantity input to 1 after craft
  if (qtyInput) {
    qtyInput.value = "1";
  }

  // Success message in top status
  const qty = crafted.quantity || times;
  const label = crafted.label || crafted.item_key || itemKey;

  if (delayed) {
    setCraftStatus(`Craft lancé : x${qty} ${label} (en cours...)`, "success");
  } else {
    setCraftStatus(`Craft réussi : x${qty} ${label}`, "success");
  }

  // Refresh ingredients, jobs & timer
  await refreshCraftData();

  // After refresh, show the job timer if a job is now active
  renderCraftJobStatus();

  // Reset filled slots but keep pattern
  craftState.filledSlots = new Array(craftState.expectedSlots.length).fill(null);
  renderCraftSlots();
}

