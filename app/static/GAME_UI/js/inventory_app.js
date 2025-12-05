/*
  File: static/GAME_UI/js/inventory_app.js
  Purpose: UI Inventaire (ressources + cartes) pour le GAME_UI.
  Notes:
  - Utilise http() et $() de common.js
  - Utilise currentPlayer / renderPlayer de game_app.js (si besoin plus tard)
*/

let invResources = [];
let invResourceDefsByKey = {};
let invCards = [];
// NEW: crafted items
let invItems = [];
let invItemDefsByKey = {};

const INV_ITEM_LOCAL_DEFS = {
  wooden_stick: {
    label: "Bâton en bois",
    type: "component",
    icon: "/static/assets/img/items/wooden_stick.png",
    description: "Un simple bâton en bois, utile pour fabriquer des outils ou des armes rudimentaires."
  },
  };

// ---------------------------------------------------------------------------
// Helpers de rendu
// ---------------------------------------------------------------------------

function renderResourceList(filterText = "") {
  const listEl = $("invResourcesList");
  const emptyEl = $("invResourcesEmpty");
  if (!listEl || !emptyEl) return;

  const term = (filterText || "").toLowerCase().trim();

  const items = invResources.filter((item) => {
    const def = invResourceDefsByKey[item.resource] || {};
    const label = (def.label || item.resource || "").toLowerCase();
    const key = (item.resource || "").toLowerCase();
    if (!term) return true;
    return label.includes(term) || key.includes(term);
  });

  listEl.innerHTML = "";
  if (!items.length) {
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");

  items.forEach((item) => {
    const def = invResourceDefsByKey[item.resource] || {};
    const label = def.label || item.resource || "???";
    const icon = def.icon || null;
    const qty = item.qty ?? item.quantity ?? 0;
    const description = def.description || "Pas de description disponible.";
    const baseSellPrice = def.base_sell_price ?? null;
    const row = document.createElement("div");

    if(def.icon == null)
    {
      console.log(def.icon);
    }

    // Tile-style + tooltip
    row.className = "inv-resource-item inv-tooltip";
    row.innerHTML = `
      <div class="inv-resource-icon-wrapper">
        ${
          icon
            ? `<img src="${icon}" alt="${label}" />`
            : `<div class="inv-resource-placeholder">📦</div>`
        }
        <span class="inv-resource-qty-badge">${qty}</span>
      </div>

      <div class="inv-tooltip-content">
        <div class="inv-tooltip-title">${label}</div>
        <div class="inv-tooltip-sub">${item.resource}</div>
        <div class="inv-tooltip-body">
          ${description}
          ${
            baseSellPrice != null
              ? `<div class="inv-tooltip-extra">Valeur de base : ${baseSellPrice} coins</div>`
              : ""
          }
        </div>
      </div>
    `;

    listEl.appendChild(row);
  });
}

function renderItemList(filterText = "") {
  const listEl = $("invItemsList");
  const emptyEl = $("invItemsEmpty");
  if (!listEl || !emptyEl) return;

  const term = (filterText || "").toLowerCase().trim();

  // Optional type filter from dropdown
  const typeSelect = $("invItemTypeFilter");
  const typeFilter = typeSelect ? (typeSelect.value || "all").toLowerCase() : "all";

  // Build enriched items array from stacks + defs
  const enriched = invItems.map((stack) => {
    const key = stack.item_key;
    const def = invItemDefsByKey[key] || {};
    console.log("Item definition for", key, def, INV_ITEM_LOCAL_DEFS[key]);
    
    return {
      key,
      quantity: stack.quantity ?? stack.qty ?? 0,
      label: def.label || key,
      icon: def.icon || null,
      type: (def.type || "misc").toLowerCase(),
      category: def.category || null,
      description: def.description || "Item crafté.",
    };
  });

  // Apply filters (text + type)
  const filtered = enriched.filter((it) => {
    // Type filter
    if (typeFilter !== "all" && it.type !== typeFilter) {
      return false;
    }

    if (!term) return true;

    const label = (it.label || "").toLowerCase();
    const key = (it.key || "").toLowerCase();
    const desc = (it.description || "").toLowerCase();

    return (
      label.includes(term) ||
      key.includes(term) ||
      desc.includes(term)
    );
  });

  listEl.innerHTML = "";
  if (!filtered.length) {
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");

  filtered.forEach((it) => {
    const row = document.createElement("div");
    // Same visual style as resources: tile + tooltip
    row.className = "inv-resource-item inv-tooltip inv-item-crafted";

    // Small readable tag for type/category
    const typeLabel = it.type || "misc";
    const categoryLabel = it.category ? ` • ${it.category}` : "";

    row.innerHTML = `
      <div class="inv-resource-icon-wrapper">
        ${
          it.icon
            ? `<img src="${it.icon}" alt="${it.label}" />`
            : `<div class="inv-resource-placeholder">-</div>`
        }
        <span class="inv-resource-qty-badge">${it.quantity}</span>
      </div>

      <div class="inv-tooltip-content">
        <div class="inv-tooltip-title">${it.label}</div>
        <div class="inv-tooltip-sub">
          ${it.key} • ${typeLabel}${categoryLabel}
        </div>
        <div class="inv-tooltip-body">
          ${it.description}
        </div>
      </div>
    `;

    listEl.appendChild(row);
  });
}

function renderCardList(filterText = "") {
  const listEl = $("invCardsList");
  const emptyEl = $("invCardsEmpty");
  if (!listEl || !emptyEl) return;

  const term = (filterText || "").toLowerCase().trim();

  // Current type filter from dropdown
  const typeSelect = $("invCardTypeFilter");
  const typeFilter = typeSelect ? (typeSelect.value || "all").toLowerCase() : "all";

  // Only owned cards
  const owned = invCards.filter((c) => (c.owned_qty || 0) > 0);

  const items = owned.filter((card) => {
    const label = (card.label || "").toLowerCase();
    const desc = (card.description || "").toLowerCase();
    const type = (card.type || "").toLowerCase();
    const key = (card.key || "").toLowerCase();

    // Text search
    if (term) {
      const matchText =
        label.includes(term) ||
        desc.includes(term) ||
        type.includes(term) ||
        key.includes(term);
      if (!matchText) return false;
    }

    // Type filter (if not "all")
    if (typeFilter !== "all" && type !== typeFilter) {
      return false;
    }

    return true;
  });

  listEl.innerHTML = "";
  if (!items.length) {
    emptyEl.classList.remove("d-none");
    return;
  }
  emptyEl.classList.add("d-none");

  items.forEach((card) => {
    const icon = card.icon || null;
    const qty = card.owned_qty || 0;

    const row = document.createElement("div");
    // Grid tile + tooltip
    row.className = "inv-card-tile inv-tooltip";

    row.innerHTML = `
      <div class="inv-card-image-wrapper">
        ${
          icon
            ? `<img src="${icon}" alt="${card.label || card.key}" />`
            : `<div class="inv-card-placeholder">🃏</div>`
        }
        <span class="inv-card-qty-badge">x${qty}</span>
      </div>
      <div class="inv-card-name">${card.label || card.key}</div>

      <div class="inv-tooltip-content">
        <div class="inv-tooltip-title">${card.label || card.key}</div>
        <div class="inv-tooltip-sub">
          Type : ${card.type || "?"}
          ${
            card.target_resource
              ? ` • Cible : ${card.target_resource}`
              : ""
          }
        </div>
        ${
          card.description
            ? `<div class="inv-tooltip-body">${card.description}</div>`
            : ""
        }
      </div>
    `;

    listEl.appendChild(row);
  });
}


// ---------------------------------------------------------------------------
// Tabs + filtres
// ---------------------------------------------------------------------------

function setupInventoryTabs() {
  const tabRes = $("invTabResources");
  const tabCards = $("invTabCards");
  const panelRes = $("invPanelResources");
  const panelCards = $("invPanelCards");
  const tabItems = $("invTabItems");
  const panelItems = $("invPanelItems");

  if (!tabRes || !tabCards || !panelRes || !panelCards || !tabItems || !panelItems) return;

  tabRes.addEventListener("click", () => {
    tabRes.classList.add("inv-tab-active");
    panelRes.classList.add("inv-panel-active");

    tabCards.classList.remove("inv-tab-active");
    panelCards.classList.remove("inv-panel-active");
    tabItems.classList.remove("inv-tab-active");
    panelItems.classList.remove("inv-panel-active");
  });

  tabCards.addEventListener("click", () => {
    tabCards.classList.add("inv-tab-active");
    panelCards.classList.add("inv-panel-active");
    
    tabRes.classList.remove("inv-tab-active");
    panelRes.classList.remove("inv-panel-active");
    tabItems.classList.remove("inv-tab-active");
    panelItems.classList.remove("inv-panel-active");
  });


  tabItems.addEventListener("click", () => {
    tabItems.classList.add("inv-tab-active");
    panelItems.classList.add("inv-panel-active");

    tabRes.classList.remove("inv-tab-active");
    tabCards.classList.remove("inv-tab-active");   
    panelRes.classList.remove("inv-panel-active");
    panelCards.classList.remove("inv-panel-active");
  }); 
}

function setupFilters() {
  const resFilter = $("invResourceFilter");
  const cardFilter = $("invCardFilter");
  const cardTypeFilter = $("invCardTypeFilter");

  const itemFilter = $("invItemFilter");
  const itemTypeFilter = $("invItemTypeFilter");

  if (resFilter) {
    resFilter.addEventListener("input", () => {
      renderResourceList(resFilter.value);
    });
  }

  if (cardFilter) {
    cardFilter.addEventListener("input", () => {
      renderCardList(cardFilter.value);
    });
  }

  if (cardTypeFilter) {
    // When type changes, we re-render with current text filter
    cardTypeFilter.addEventListener("change", () => {
      const textTerm = cardFilter ? cardFilter.value : "";
      renderCardList(textTerm);
    });
  }

    if (itemFilter) {
    itemFilter.addEventListener("input", () => {
      renderItemList(itemFilter.value);
    });
  }

  if (itemTypeFilter) {
    itemTypeFilter.addEventListener("change", () => {
      const textTerm = itemFilter ? itemFilter.value : "";
      renderItemList(textTerm);
    });
  } 

}


// ---------------------------------------------------------------------------
// Chargement des données
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Chargement des données
// ---------------------------------------------------------------------------

async function loadInventoryData() {
  // 1) état global pour ressources + defs + items + cartes
  const s = await http("GET", "/api/state");
  if (!s.ok) {
    alert("Impossible de charger l'inventaire (state).");
    console.error("Inventory /api/state error:", s);
    return;
  }

  const state = s.data || {};

  // -----------------------------
  // RESSOURCES
  // -----------------------------
  invResources = state.inventory || [];
  invResourceDefsByKey = {};
  (state.resources || []).forEach((r) => {
    if (!r.key) return;
    invResourceDefsByKey[r.key] = r;
  });

  renderResourceList("");

  // -----------------------------
  // ITEMS (craftés)
  // backend => items_payload:
  // {
  //   "item_key": it.item_key,
  //   "qty": it.quantity,
  //   "label_fr": ...,
  //   "label_en": ...,
  //   "icon": ...,
  //   "type": ...,
  //   "category": ...
  // }
  // -----------------------------
  invItems = [];
  invItemDefsByKey = {};

  (state.items || []).forEach((it) => {
    const key = it.item_key;
    if (!key) return;

    // Stack de quantité "brut"
    invItems.push({
      item_key: key,
      quantity: it.qty ?? it.quantity ?? 0,
    });

    // Déf de l'item (icône, label, type, description...)
    invItemDefsByKey[key] = {
      key,
      label: it.label_fr || it.label_en || key,
      icon: it.icon || null,
      type: (it.type || "misc").toLowerCase(),
      category: it.category || null,
      description: it.description || "Item crafté.",
    };
  });

  renderItemList("");

  // -----------------------------
  // CARTES
  // state.cards contient déjà toutes les infos utiles
  // (clé, label, type, description, icon, qty_owned, etc.)
  // -----------------------------
  invCards = state.cards || [];
  renderCardList("");
}



// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  setupInventoryTabs();
  setupFilters();
  await loadInventoryData();
});
