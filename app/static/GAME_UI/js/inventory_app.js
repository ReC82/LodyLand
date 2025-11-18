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

    const row = document.createElement("div");
    row.className = "inv-card-row";

    row.innerHTML = `
      <div class="inv-card-main">
        <div class="inv-card-icon">
          ${
            icon
              ? `<img src="${icon}" alt="${label}" />`
              : "📦"
          }
        </div>
        <div class="inv-card-text">
          <div class="inv-card-title">${label}</div>
          <div class="inv-card-sub">${item.resource}</div>
        </div>
      </div>
      <div class="inv-card-side">
        <div class="inv-card-qty-label">Quantité</div>
        <div class="inv-card-qty-value">${qty}</div>
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

  // On ne garde que les cartes possédées
  const owned = invCards.filter((c) => (c.owned_qty || 0) > 0);

  const items = owned.filter((card) => {
    if (!term) return true;
    const label = (card.label || "").toLowerCase();
    const desc = (card.description || "").toLowerCase();
    const type = (card.type || "").toLowerCase();
    const key = (card.key || "").toLowerCase();
    return (
      label.includes(term) ||
      desc.includes(term) ||
      type.includes(term) ||
      key.includes(term)
    );
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
    row.className = "inv-card-row";

    row.innerHTML = `
      <div class="inv-card-main">
        <div class="inv-card-icon">
          ${
            icon
              ? `<img src="${icon}" alt="${card.label || card.key}" />`
              : "🃏"
          }
        </div>
        <div class="inv-card-text">
          <div class="inv-card-title">${card.label || card.key}</div>
          <div class="inv-card-sub">
            Type : ${card.type || "?"}
            ${
              card.target_resource
                ? ` • Cible : ${card.target_resource}`
                : ""
            }
          </div>
          ${
            card.description
              ? `<div class="inv-card-desc">${card.description}</div>`
              : ""
          }
        </div>
      </div>
      <div class="inv-card-side">
        <div class="inv-card-qty-label">Possédées</div>
        <div class="inv-card-qty-value">${qty}</div>
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
