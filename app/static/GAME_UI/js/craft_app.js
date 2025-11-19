/* 
  File: static/GAME_UI/js/craft_app.js
  Purpose: Craft UI logic (popup, ingredients, recipes, drag & drop, perform craft).
  Notes:
  - Uses http() and $() helpers from common.js / game_app.js.
*/

// ============================================================================
// Global craft state
// ============================================================================
let craftState = {
  recipes: [],
  selectedRecipe: null,
  tableLevel: 1,

  inventory: [],       // player stock
  resourceDefs: [],    // ResourceDef from /api/state

  expectedSlots: [null, null, null],  // decoded pattern (3 slots)
  filledSlots:  [null, null, null],   // player drops

  showRecipes: false,
};


// ============================================================================
// Init
// ============================================================================
function initCraftUI() {
  const modalEl          = $("craft-modal");
  const openBtn          = $("craft-open-btn");
  const closeBtn         = $("craft-close-btn");
  const performBtn       = $("craft-perform-btn");
  const recipesToggleBtn = $("craft-recipes-toggle-btn");

  if (!modalEl || !openBtn || !closeBtn || !performBtn) {
    console.warn("[craft] Missing DOM elements for craft UI.");
    return;
  }

  // Open
  openBtn.addEventListener("click", () => openCraftModal());

  // Close
  closeBtn.addEventListener("click", () => closeCraftModal());

  // Backdrop closes
  const backdrop = modalEl.querySelector(".craft-modal-backdrop");
  if (backdrop) {
    backdrop.addEventListener("click", () => closeCraftModal());
  }

  // Toggle recipes panel
  if (recipesToggleBtn) {
    recipesToggleBtn.addEventListener("click", () => {
      craftState.showRecipes = !craftState.showRecipes;
      updateCraftPanelsVisibility();
    });
  }

  // Perform craft
  performBtn.addEventListener("click", onCraftPerformClicked);

  // Init drag & drop listeners for slots
  document.querySelectorAll(".craft-slot").forEach((slotEl, index) => {
    slotEl.dataset.slot = index;

    slotEl.addEventListener("dragover", (e) => e.preventDefault());
    slotEl.addEventListener("drop", (e) => onSlotDropped(e, index));
  });
}


// ============================================================================
// Open / Close modal
// ============================================================================
function openCraftModal() {
  const modalEl = $("craft-modal");
  if (!modalEl) return;

  craftState.showRecipes = false;
  craftState.selectedRecipe = null;
  craftState.expectedSlots = [null, null, null];
  craftState.filledSlots  = [null, null, null];

  modalEl.classList.add("is-open");
  refreshCraftData();
}

function closeCraftModal() {
  const modalEl = $("craft-modal");
  if (!modalEl) return;

  modalEl.classList.remove("is-open");
  craftState.selectedRecipe = null;
  craftState.filledSlots = [null, null, null];
  updateCraftSelectionUI();
  renderCraftSlots();
}


// ============================================================================
// Load state + recipes
// ============================================================================
async function refreshCraftData() {
  // 1) Load state
  const stateRes = await http("GET", "/api/state");
  if (!stateRes.ok) {
    console.error("[craft] Failed to load /api/state:", stateRes);
    return;
  }
  const state = stateRes.data;

  craftState.tableLevel   = state.craft?.craft_table_level || 1;
  craftState.inventory    = state.inventory || [];
  craftState.resourceDefs = state.resources || [];

  const levelSpan = $("craft-table-level");
  if (levelSpan) levelSpan.textContent = craftState.tableLevel;

  // Render ingredients
  renderCraftIngredients(craftState.inventory);

  // 2) Load recipes
  const recipesRes = await http("GET", "/api/craft/recipes?location=craft_table");
  if (!recipesRes.ok) {
    console.error("[craft] Failed to load /api/craft/recipes:", recipesRes);
    renderCraftRecipes([]);
    updateCraftPanelsVisibility();
    return;
  }

  craftState.recipes = recipesRes.data.recipes || [];
  renderCraftRecipes(craftState.recipes);

  updateCraftPanelsVisibility();
}


// ============================================================================
// Render ingredients panel
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

  inventory.forEach((res) => {
    const key = res.key || res.resource || "";
    const defs = craftState.resourceDefs || [];
    const def = defs.find((d) => d.key === key) || null;

    const labelText = def?.label || key || "Ingrédient";
    const qtyVal = typeof res.qty === "number" ? res.qty : 0;
    const iconPath = def?.icon || null;

    const item = document.createElement("div");
    item.className = "craft-ingredient-item";
    item.dataset.key = key;

    // Make ingredient draggable
    item.draggable = true;
    item.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", key);
    });

    const left = document.createElement("div");
    left.className = "craft-ingredient-name";

    const iconWrap = document.createElement("div");
    iconWrap.className = "craft-ingredient-icon";

    if (iconPath) {
      const img = document.createElement("img");
      let src = iconPath;
      if (!iconPath.startsWith("/") && !iconPath.startsWith("http")) {
        src = "/" + iconPath.replace(/^\/+/, "");
      }
      img.src = src;
      img.alt = labelText;
      iconWrap.appendChild(img);
    } else {
      iconWrap.textContent = labelText.charAt(0).toUpperCase();
    }

    const label = document.createElement("span");
    label.textContent = labelText;

    left.appendChild(iconWrap);
    left.appendChild(label);

    const qty = document.createElement("div");
    qty.className = "craft-ingredient-qty";
    qty.textContent = `x${qtyVal}`;

    item.appendChild(left);
    item.appendChild(qty);

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

  recipes.forEach((r) => {
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
      iconWrap.appendChild(img);
    } else {
      iconWrap.textContent = "?";
    }

    const textWrap = document.createElement("div");
    const label = document.createElement("div");
    label.textContent = r.label_fr || r.label_en || r.item_key;
    label.style.fontSize = "0.9rem";

    const sub = document.createElement("div");
    sub.textContent = `Tps: ${r.recipe?.craft_time_seconds || 0}s`;
    sub.style.fontSize = "0.75rem";
    sub.style.color = "#9ca3af";

    textWrap.appendChild(label);
    textWrap.appendChild(sub);

    item.appendChild(iconWrap);
    item.appendChild(textWrap);

    // CLICK = select recipe + decode pattern into slots
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
// Decode recipe → expectedSlots
// ============================================================================
function decodeRecipeIntoSlots(r) {
  craftState.expectedSlots = [null, null, null];
  craftState.filledSlots   = [null, null, null];

  if (!r || !r.recipe || !r.recipe.pattern || !r.recipe.legend) return;

  const pattern = r.recipe.pattern;
  const legend  = r.recipe.legend;

  const row = pattern[0] || "";

  for (let i = 0; i < 3; i++) {
    const symbol = row[i] || ".";
    if (symbol === ".") {
      craftState.expectedSlots[i] = null;
    } else {
      craftState.expectedSlots[i] = {
        key: legend[symbol].key,
        qty: legend[symbol].quantity || 1,
      };
    }
  }
}


// ============================================================================
// Render craft slots
// ============================================================================
function renderCraftSlots() {
  const slots = document.querySelectorAll(".craft-slot");

  slots.forEach((el, idx) => {
    const expected = craftState.expectedSlots[idx];
    const filled   = craftState.filledSlots[idx];

    el.innerHTML = "";
    el.style.opacity = expected ? 1 : 0.3;

    if (!expected) return;

    if (filled) {
      const def = craftState.resourceDefs.find(d => d.key === filled.key);
      if (def && def.icon) {
        const img = document.createElement("img");
        img.className = "craft-slot-img";

        let src = def.icon;
        if (!src.startsWith("/") && !src.startsWith("http")) {
          src = "/" + src.replace(/^\/+/, "");
        }

        img.src = src;
        img.dataset.key = filled.key;
        el.appendChild(img);
      }
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "craft-slot-placeholder";
      placeholder.textContent = `${expected.key} x${expected.qty}`;
      el.appendChild(placeholder);
    }
  });
}


// ============================================================================
// Drag & Drop: on drop into slot
// ============================================================================
function onSlotDropped(e, slotIndex) {
  e.preventDefault();
  const key = e.dataTransfer.getData("text/plain");

  const expected = craftState.expectedSlots[slotIndex];
  if (!expected) return;

  if (expected.key !== key) {
    flashSlotError(slotIndex);
    return;
  }

  craftState.filledSlots[slotIndex] = { key };
  renderCraftSlots();
  updateCraftSelectionUI();
}


// ============================================================================
// Flash slot red (wrong ingredient)
// ============================================================================
function flashSlotError(idx) {
  const slot = document.querySelector(`.craft-slot[data-slot="${idx}"]`);
  if (!slot) return;

  slot.style.borderColor = "#ef4444";
  setTimeout(() => {
    slot.style.borderColor = "";
  }, 300);
}


// ============================================================================
// Toggle ingredients/recipes panels
// ============================================================================
function updateCraftPanelsVisibility() {
  const ingredientsPanel = $("craft-ingredients-panel");
  const recipesPanel     = $("craft-recipes-panel");

  if (!ingredientsPanel || !recipesPanel) return;

  if (craftState.showRecipes) {
    ingredientsPanel.style.display = "none";
    recipesPanel.style.display     = "block";
  } else {
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

  if (!performBtn) return;

  // Reset messages
  if (errEl)     { errEl.style.display = "none"; errEl.textContent = ""; }
  if (successEl) { successEl.style.display = "none"; successEl.textContent = ""; }

  // Update highlight in recipe list
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

  // No recipe selected
  if (!craftState.selectedRecipe) {
    performBtn.disabled = true;
    return;
  }

  // All slots must be correctly filled
  const allGood = craftState.expectedSlots.every((exp, i) => {
    if (!exp) return true;
    return craftState.filledSlots[i] && craftState.filledSlots[i].key === exp.key;
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

  if (errEl)     { errEl.style.display = "none"; errEl.textContent = ""; }
  if (successEl) { successEl.style.display = "none"; successEl.textContent = ""; }

  // Quantity
  let times = 1;
  if (qtyInput) {
    const v = parseInt(qtyInput.value, 10);
    times = Number.isNaN(v) || v < 1 ? 1 : v;
    qtyInput.value = String(times);
  }

  performBtn.disabled = true;

  const itemKey = craftState.selectedRecipe.item_key;

  const res = await http("POST", "/api/craft/perform", {
    item_key: itemKey,
    craft_location: "craft_table",
    times,
  });

  performBtn.disabled = false;

  // Handle errors
  if (!res.ok) {
    console.error("[craft] perform error", res);
    if (errEl) {
      errEl.style.display = "block";
      if (res.data && res.data.error === "not_enough_resources") {
        const missing = res.data.missing || {};
        const parts = Object.entries(missing).map(
          ([k, v]) => `${v} x ${k}`
        );
        errEl.textContent = "Pas assez de ressources: " + parts.join(", ");
      } else {
        errEl.textContent = "Erreur lors du craft.";
      }
    }
    return;
  }

  // Success
  if (successEl) {
    const crafted = res.data?.crafted_item;
    const qty     = crafted?.quantity || times;
    const label   =
      crafted?.label_fr ||
      crafted?.label_en ||
      crafted?.item_key ||
      itemKey;

    successEl.style.display = "block";
    successEl.textContent = `Craft réussi: x${qty} ${label}`;
  }

  // Refresh ingredients & slots
  await refreshCraftData();

  // Reset filled slots after craft
  craftState.filledSlots = [null, null, null];
  renderCraftSlots();
}
