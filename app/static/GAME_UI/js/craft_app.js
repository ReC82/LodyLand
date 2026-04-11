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

  // Craft table level: 0 / 1 / 2 / 3
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

  // Craft queue state
  activeJob: null,     // currently crafting
  queueJobs: [],       // waiting in queue
  maxQueueSlots: 2,    // base 2 + extra purchased
  extraSlots: 0,
  nextSlotCost: 2,

  // Filters (text input)
  ingredientsFilter: "",
  recipesFilter: "",
};

// Set of job IDs for which we've already shown a "done" toast
const _craftShownDoneIds = new Set();

// Interval ID for the progress/timer loop
let craftTimerLoopId = null;

// Track progress per job so the bar never goes backwards
let _craftProgressJobId = null;
let _craftProgressPct   = 0;

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
// Craft queue bar rendering
// ============================================================================

/** Format seconds as "mm:ss" */
function formatSecondsMMSS(total) {
  const sec = Math.max(0, parseInt(total, 10) || 0);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

/** Show/hide the craft FAB red dot */
function updateCraftFabDot(show) {
  const dot = document.getElementById("craft-fab-dot");
  if (!dot) return;
  dot.style.display = show ? "" : "none";
}

/** Show a "craft done" toast above the FAB button */
function showCraftDoneToast(label, qty) {
  let toast = document.querySelector(".craft-done-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "craft-done-toast";
    const icon = document.createElement("span");
    icon.className = "craft-done-toast-icon";
    icon.textContent = "✓";
    toast.appendChild(icon);
    const text = document.createElement("span");
    text.className = "craft-done-toast-text";
    toast.appendChild(text);
    document.body.appendChild(toast);
  }

  const text = toast.querySelector(".craft-done-toast-text");
  if (text) text.textContent = `Craft terminé : ×${qty} ${label}`;

  toast.classList.add("is-visible");
  setTimeout(() => toast.classList.remove("is-visible"), 3500);
}

/**
 * Render the queue bar (active job + queue slots + unlock button).
 * Called every second by the timer loop AND after each data refresh.
 */
function renderCraftQueueBar() {
  const bar = document.getElementById("craft-queue-bar");
  if (!bar) return;

  // Show the bar whenever the player has a craft table
  bar.style.display = craftState.tableLevel > 0 ? "flex" : "none";

  const job = craftState.activeJob;
  bar.classList.toggle("has-active-job", !!job);

  // --- Active job section ---
  const jobIcon  = document.getElementById("craft-job-icon");
  const jobIconFb = document.getElementById("craft-job-icon-fallback");
  const jobName  = document.getElementById("craft-job-name");
  const timerClock = document.getElementById("craft-timer-clock");
  const timerQty = document.getElementById("craft-timer-qty");
  const progressBar = document.getElementById("craft-progress-bar");

  if (job) {
    // Icon
    if (jobIcon) {
      if (job.icon) {
        let src = job.icon;
        if (!src.startsWith("/") && !src.startsWith("http")) src = "/" + src;
        jobIcon.src = src;
        jobIcon.style.display = "";
        if (jobIconFb) jobIconFb.style.display = "none";
      } else {
        jobIcon.style.display = "none";
        if (jobIconFb) jobIconFb.style.display = "";
      }
    }

    if (jobName) jobName.textContent = job.label || job.item_key || "—";

    // Compute remaining time from ends_at
    // Backend returns naive UTC strings (no "Z"), so we append it to force UTC parsing
    const _addZ = (s) => (s && !s.endsWith("Z") && !s.includes("+") ? s + "Z" : s);
    const now = Date.now() / 1000;
    const endsAt = new Date(_addZ(job.ends_at)).getTime() / 1000;
    const startedAt = new Date(_addZ(job.started_at)).getTime() / 1000;
    const totalSecs = Math.max(1, endsAt - startedAt);
    const remaining = Math.max(0, endsAt - now);
    const elapsed = totalSecs - remaining;
    const progress = Math.min(100, (elapsed / totalSecs) * 100);

    if (timerClock) timerClock.textContent = formatSecondsMMSS(Math.ceil(remaining));
    if (timerQty) timerQty.textContent = `×${job.quantity_total || 1}`;
    if (progressBar) {
      // Never allow progress to go backwards for the same job
      if (_craftProgressJobId !== job.id) {
        _craftProgressJobId = job.id;
        _craftProgressPct   = 0;
      }
      _craftProgressPct = Math.max(_craftProgressPct, progress);
      progressBar.style.width = _craftProgressPct + "%";
    }
  }

  // Show/hide the whole active-job display based on whether a job is running
  const activeDisplay = document.getElementById("craft-active-job-display");
  if (activeDisplay) activeDisplay.style.display = job ? "flex" : "none";

  // --- Queue slots (waiting) ---
  renderCraftQueueSlots();

  // --- Unlock slot button (always visible when table unlocked) ---
  const unlockBtn  = document.getElementById("craft-unlock-slot-btn");
  const costSpan   = document.getElementById("craft-unlock-slot-cost");
  if (unlockBtn) {
    unlockBtn.style.display = craftState.tableLevel > 0 ? "" : "none";
    if (costSpan) costSpan.textContent = `${craftState.nextSlotCost} ✦`;
  }
}

/** Render queue slot items (waiting jobs + empty slots) */
function renderCraftQueueSlots() {
  const container = document.getElementById("craft-queue-slots");
  if (!container) return;
  container.innerHTML = "";

  const queuedJobs = craftState.queueJobs || [];
  // Extra queue capacity beyond active slot = maxQueueSlots - 1
  const queueCapacity = Math.max(0, craftState.maxQueueSlots - 1);

  for (let i = 0; i < queueCapacity; i++) {
    const queued = queuedJobs[i] || null;
    const el = document.createElement("div");

    if (queued) {
      el.className = "craft-queue-slot-item";
      el.title = queued.label || queued.item_key;
      if (queued.icon) {
        const img = document.createElement("img");
        let src = queued.icon;
        if (!src.startsWith("/") && !src.startsWith("http")) src = "/" + src;
        img.src = src;
        img.alt = queued.label || queued.item_key;
        el.appendChild(img);
      } else {
        el.textContent = "⚙";
        el.style.fontSize = "1rem";
        el.style.color = "#9ca3af";
      }
    } else {
      el.className = "craft-queue-slot-empty";
      const icon = document.createElement("span");
      icon.className = "craft-queue-slot-empty-icon";
      icon.textContent = "·";
      el.appendChild(icon);
    }
    container.appendChild(el);
  }
}

/** Start (or restart) the 1-second timer loop that updates the queue bar */
function startCraftTimerLoop() {
  if (craftTimerLoopId) {
    clearInterval(craftTimerLoopId);
    craftTimerLoopId = null;
  }

  if (!craftState.activeJob) return;

  let ticksSinceSync = 0;

  craftTimerLoopId = setInterval(() => {
    renderCraftQueueBar();
    ticksSinceSync++;

    // Every 5 ticks (~5 seconds), resync with backend
    if (ticksSinceSync >= 5) {
      ticksSinceSync = 0;
      clearInterval(craftTimerLoopId);
      craftTimerLoopId = null;
      refreshCraftData().catch((e) =>
        console.error("[craft] timer resync error:", e)
      );
    }
  }, 1000);
}

/** Legacy stub (used in a few places) - now a no-op */
function setCraftStatus(text, tone) {
  // Queue bar replaced the old status box. No-op kept for compatibility.
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
// Legacy stubs (kept for compatibility with code paths that may call them)
// ============================================================================

function isCraftJobActive() {
  return !!(craftState.activeJob);
}

function renderCraftJobStatus() {
  renderCraftQueueBar();
}

function setupCraftJobTimerFromState() {
  startCraftTimerLoop();
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

  // Only wipe slot state + rebuild DOM when the grid size actually changes.
  // This prevents ghost icons disappearing on every 5-second resync.
  const domSlots = grid.querySelectorAll(".craft-slot").length;
  if (domSlots === slotsCount) {
    // Grid size unchanged — just re-render the existing slots
    renderCraftSlots();
    return;
  }

  // Grid size changed (or first build): reset and rebuild fully
  craftState.expectedSlots = new Array(slotsCount).fill(null);
  craftState.filledSlots   = new Array(slotsCount).fill(null);
  craftState.selectedRecipe = null;

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

  // Buy extra queue slot
  const unlockSlotBtn = $("craft-unlock-slot-btn");
  if (unlockSlotBtn) {
    unlockSlotBtn.addEventListener("click", onBuyQueueSlotClicked);
  }

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

  // Clear notification dot when opening
  updateCraftFabDot(false);

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
  // Sync global player for the main HUD (XP/level/etc.)
  if (state.player) {
    window.currentPlayer = state.player;
  }
  const craftBlock = state.craft || {};
  craftState.tableLevel =
    typeof craftBlock.craft_table_level === "number"
      ? craftBlock.craft_table_level
      : 0;

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

  // Build merged inventory
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

  // Queue state from backend
  craftState.activeJob   = craftBlock.active_job  || null;
  craftState.queueJobs   = craftBlock.queue_jobs  || [];
  craftState.maxQueueSlots = craftBlock.max_queue_slots || 2;
  craftState.extraSlots    = craftBlock.extra_slots || 0;
  craftState.nextSlotCost  = craftBlock.next_slot_cost || 2;

  // Recently-completed jobs → show toasts + red dot
  const recentDone = craftBlock.recently_completed || [];
  let hasNew = false;
  recentDone.forEach((rc) => {
    if (!_craftShownDoneIds.has(rc.id)) {
      _craftShownDoneIds.add(rc.id);
      showCraftDoneToast(rc.label || rc.item_key, rc.quantity_total || 1);
      hasNew = true;
    }
  });
  if (hasNew) {
    // Only show dot if modal is not currently open
    const modalEl = $("craft-modal");
    if (!modalEl || !modalEl.classList.contains("is-open")) {
      updateCraftFabDot(true);
    }
  }

  const levelSpan = $("craft-table-level");
  if (levelSpan) levelSpan.textContent = craftState.tableLevel;

  rebuildCraftGrid();

  // FAB craft button visible only if tableLevel > 0
  const craftBtn = $("craft-open-btn");
  if (craftBtn) {
    craftBtn.style.display = craftState.tableLevel > 0 ? "" : "none";
  }

  renderCraftIngredients(craftState.inventory);

  // Render queue bar + start timer loop
  renderCraftQueueBar();
  startCraftTimerLoop();

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
    recipesPanel.style.display     = "flex";
  } else {
    console.log("Showing ingredients panel, hiding recipes panel.");
    ingredientsPanel.style.display = "flex";
    recipesPanel.style.display     = "none";
  }
}


// ============================================================================
// Selection UI + enable/disable craft button
// ============================================================================

function updateCraftSelectionUI() {
  const performBtn = $("craft-perform-btn");

  renderCraftQueueBar();

  // Highlight selected recipe in list
  const listEl = $("craft-recipes-list");
  if (listEl) {
    const items = listEl.querySelectorAll(".craft-recipe-item");
    items.forEach((el) => {
      const key = el.getAttribute("data-itemKey");
      if (craftState.selectedRecipe && key === craftState.selectedRecipe.item_key) {
        el.classList.add("is-selected");
      } else {
        el.classList.remove("is-selected");
      }
    });
  }

  // Show duration hint for selected recipe
  const durationEl = $("craft-recipe-duration");
  const durationText = $("craft-duration-text");
  if (durationEl && durationText) {
    const recipe = craftState.selectedRecipe;
    const tps = recipe?.recipe?.craft_time_seconds || 0;
    if (recipe && tps > 0) {
      durationText.textContent = formatSecondsMMSS(tps) + " par item";
      durationEl.style.display = "flex";
    } else if (recipe && tps === 0) {
      durationText.textContent = "Instantané";
      durationEl.style.display = "flex";
    } else {
      durationEl.style.display = "none";
    }
  }

  if (!performBtn) return;

  // Button text
  performBtn.textContent = craftState.showRecipes ? "Choisir cette recette" : "Craft";

  // --- CASE 1: Recipes panel ---
  if (craftState.showRecipes) {
    performBtn.disabled = !craftState.selectedRecipe;
    return;
  }

  // --- CASE 2: Ingredients panel ---
  if (!craftState.selectedRecipe || !craftState.tableLevel || craftState.tableLevel <= 0) {
    performBtn.disabled = true;
    return;
  }

  if (!craftState.selectedRecipe.is_unlocked) {
    performBtn.disabled = true;
    return;
  }

  // Queue full check (only for delayed crafts)
  const tps = craftState.selectedRecipe?.recipe?.craft_time_seconds || 0;
  if (tps > 0) {
    const occupied = (craftState.activeJob ? 1 : 0) + craftState.queueJobs.length;
    if (occupied >= craftState.maxQueueSlots) {
      performBtn.disabled = true;
      return;
    }
  }

  // All expected slots must be filled
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

  // --- CASE 1: Recipes panel → switch to ingredients panel ---
  if (craftState.showRecipes) {
    if (!craftState.selectedRecipe) return;
    craftState.showRecipes = false;
    updateCraftPanelsVisibility();
    updateCraftSelectionUI();
    return;
  }

  // --- CASE 2: Ingredients panel → launch craft ---
  if (!craftState.selectedRecipe) return;

  if (performBtn) performBtn.disabled = true;

  const itemKey = craftState.selectedRecipe.item_key;
  const payload = { item_key: itemKey, craft_location: "craft_table", times: 1 };

  const res = await http("POST", "/api/craft/perform", payload);

  if (!res.ok) {
    if (performBtn) performBtn.disabled = false;

    const data = res.data || {};
    const code = data.error || "";

    let errMsg = "Erreur lors du craft.";
    if (code === "craft_queue_full") {
      errMsg = `File de craft pleine (${data.occupied}/${data.max_slots}). Débloque un emplacement supplémentaire.`;
    } else if (code === "not_enough_ingredients") {
      const missing = data.missing || {};
      const all = { ...(missing.resources || {}), ...(missing.items || {}) };
      const parts = Object.entries(all).map(([k, v]) => `${v} × ${k}`);
      errMsg = "Ingrédients manquants : " + (parts.join(", ") || "?");
    } else if (code === "craft_locked") {
      errMsg = "Recette verrouillée.";
    } else if (code === "craft_table_too_low") {
      errMsg = "Table de craft de niveau insuffisant.";
    }

    // Show inline error briefly in status area if it exists, otherwise alert
    const errEl = $("craft-error");
    if (errEl) {
      errEl.style.display = "block";
      errEl.textContent = errMsg;
      setTimeout(() => { errEl.style.display = "none"; }, 4000);
    } else {
      console.warn("[craft] error:", errMsg);
    }
    return;
  }

  const data = res.data || {};
  const rewards = data.rewards || null;
  if (rewards && rewards.level_up && typeof window.handleLevelUpFront === "function") {
    window.handleLevelUpFront(rewards.old_level, rewards.new_level, rewards.level_rewards || []);
  }

  // Refresh data (updates queue bar, inventory, etc.)
  await refreshCraftData();

  // Reset filled slots but keep pattern visible
  craftState.filledSlots = new Array(craftState.expectedSlots.length).fill(null);
  renderCraftSlots();
}

async function onBuyQueueSlotClicked() {
  const res = await http("POST", "/api/craft/queue/buy_slot", {});
  if (!res.ok) {
    const data = res.data || {};
    if (data.error === "not_enough_essence") {
      alert(`Essence insuffisante — il te faut ${data.required} ✦ (tu en as ${data.owned}).`);
    } else {
      console.error("[craft] buy_slot error:", data);
    }
    return;
  }
  await refreshCraftData();
}


// ============================================================================
// Background craft-done polling (runs even when modal is closed)
// ============================================================================

(function startCraftBackgroundPoll() {
  // Poll every 30 seconds when modal is closed (timer loop handles it when open)
  setInterval(async () => {
    const modalEl = document.getElementById("craft-modal");
    if (modalEl && modalEl.classList.contains("is-open")) return; // timer loop handles it
    if (!craftState.activeJob && craftState.queueJobs.length === 0) return; // nothing running

    try {
      const res = await http("GET", "/api/state");
      if (!res.ok) return;
      const craftBlock = (res.data || {}).craft || {};

      // Update queue state silently
      craftState.activeJob   = craftBlock.active_job  || null;
      craftState.queueJobs   = craftBlock.queue_jobs  || [];
      craftState.maxQueueSlots = craftBlock.max_queue_slots || 2;
      craftState.nextSlotCost  = craftBlock.next_slot_cost || 2;

      const recentDone = craftBlock.recently_completed || [];
      recentDone.forEach((rc) => {
        if (!_craftShownDoneIds.has(rc.id)) {
          _craftShownDoneIds.add(rc.id);
          showCraftDoneToast(rc.label || rc.item_key, rc.quantity_total || 1);
          updateCraftFabDot(true);
        }
      });
    } catch (e) {
      // silent
    }
  }, 30000);
})();

