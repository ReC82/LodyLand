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

  if (!tabRes || !tabCards || !panelRes || !panelCards) return;

  tabRes.addEventListener("click", () => {
    tabRes.classList.add("inv-tab-active");
    tabCards.classList.remove("inv-tab-active");
    panelRes.classList.add("inv-panel-active");
    panelCards.classList.remove("inv-panel-active");
  });

  tabCards.addEventListener("click", () => {
    tabCards.classList.add("inv-tab-active");
    tabRes.classList.remove("inv-tab-active");
    panelCards.classList.add("inv-panel-active");
    panelRes.classList.remove("inv-panel-active");
  });
}

function setupFilters() {
  const resFilter = $("invResourceFilter");
  const cardFilter = $("invCardFilter");
  const cardTypeFilter = $("invCardTypeFilter");

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
}


// ---------------------------------------------------------------------------
// Chargement des données
// ---------------------------------------------------------------------------

async function loadInventoryData() {
  // 1) état global pour ressources + inventaire
  const s = await http("GET", "/api/state");
  if (!s.ok) {
    alert("Impossible de charger l'inventaire (state).");
    console.error("Inventory /api/state error:", s);
    return;
  }

  const state = s.data || {};
  invResources = state.inventory || [];
  invResourceDefsByKey = {};
  (state.resources || []).forEach((r) => {
    invResourceDefsByKey[r.key] = r;
  });

  renderResourceList("");

  // 2) cartes pour ce joueur
  const c = await http("GET", "/api/cards");
  if (!c.ok) {
    // On log l'erreur mais on n'empêche pas les ressources d'apparaître
    console.error("Inventory /api/cards error:", c);
    return;
  }

  invCards = c.data || [];
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
