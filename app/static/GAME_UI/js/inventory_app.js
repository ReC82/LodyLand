/*
  File: static/GAME_UI/js/inventory_app.js
  Purpose: UI Inventaire (ressources + trésors + items + cartes)
  Rules:
  - Resources tab  : ResourceDef.kind === "resource"
  - Treasure tab   : ResourceDef.kind === "treasure"
  - Items tab      : non-resource items only
*/

let invResources = [];
let invTreasureResources = [];
let invResourceDefsByKey = {};

let invItems = [];
let invItemDefsByKey = {};

let invCards = [];

/* ---------------------------------------------------------------------------
   Helpers
--------------------------------------------------------------------------- */

function isResourceKind(kind, expected) {
  return String(kind || "").toLowerCase() === expected;
}

/* ---------------------------------------------------------------------------
   Cards helpers
--------------------------------------------------------------------------- */

function normalizeCardCategory(cardTypeRaw) {
  const t = String(cardTypeRaw || "").toLowerCase();
  if (t.includes("recipe")) return "recipe";
  if (t.includes("land")) return "land_access";
  if (t.includes("building")) return "building";
  if (t.includes("boost") || t.includes("cooldown") || t.includes("xp"))
    return "boost";
  return "other";
}

function getCardCategoryLabel(catKey) {
  return {
    land_access: "Lands",
    boost: "Boosts",
    recipe: "Recettes",
    building: "Bâtiments",
    other: "Autres",
  }[catKey] || "Autres";
}

function populateCardTypeFilterOptions() {
  const selectEl = $("invCardTypeFilter");
  if (!selectEl) return;

  const currentValue = (selectEl.value || "all").toLowerCase();
  const owned = invCards.filter((c) => (c.owned_qty || 0) > 0);

  const present = new Set(
    owned.map((c) => normalizeCardCategory(c.type))
  );

  const ordered = ["land_access", "boost", "recipe", "building", "other"];

  selectEl.innerHTML = "";
  selectEl.appendChild(new Option("Tous les types", "all"));

  ordered.forEach((cat) => {
    if (present.has(cat)) {
      selectEl.appendChild(new Option(getCardCategoryLabel(cat), cat));
    }
  });

  const exists = [...selectEl.options].some(
    (o) => o.value === currentValue
  );
  selectEl.value = exists ? currentValue : "all";
}

/* ---------------------------------------------------------------------------
   Rendering – Resources & Treasures
--------------------------------------------------------------------------- */

function renderResourceGrid(listId, emptyId, data, filterText = "") {
  const listEl = $(listId);
  const emptyEl = $(emptyId);
  if (!listEl || !emptyEl) return;

  const term = filterText.toLowerCase().trim();

  const filtered = data.filter((it) => {
    const def = invResourceDefsByKey[it.resource] || {};
    const label = (def.label || "").toLowerCase();
    return !term || label.includes(term) || it.resource.includes(term);
  });

  listEl.innerHTML = "";
  emptyEl.classList.toggle("d-none", filtered.length > 0);

  filtered.forEach((it) => {
    const def = invResourceDefsByKey[it.resource] || {};
    const row = document.createElement("div");
    row.className = "inv-resource-item inv-tooltip";

    row.innerHTML = `
      <div class="inv-resource-icon-wrapper">
        ${
          def.icon
            ? `<img src="${def.icon}" alt="${def.label}" />`
            : `<div class="inv-resource-placeholder">📦</div>`
        }
        <span class="inv-resource-qty-badge">${it.qty}</span>
      </div>

      <div class="inv-tooltip-content">
        <div class="inv-tooltip-title">${def.label || it.resource}</div>
        <div class="inv-tooltip-sub">${it.resource}</div>
        <div class="inv-tooltip-body">
          ${def.description || ""}
        </div>
      </div>
    `;
    listEl.appendChild(row);
  });
}

function renderResourceList(term = "") {
  renderResourceGrid("invResourcesList", "invResourcesEmpty", invResources, term);
}

function renderTreasureList(term = "") {
  renderResourceGrid(
    "invTreasuresList",
    "invTreasuresEmpty",
    invTreasureResources,
    term
  );
}

/* ---------------------------------------------------------------------------
   Rendering – Items
--------------------------------------------------------------------------- */

function renderItemList(filterText = "") {
  const listEl = $("invItemsList");
  const emptyEl = $("invItemsEmpty");
  if (!listEl || !emptyEl) return;

  const term = filterText.toLowerCase().trim();

  const items = invItems
    .map((st) => {
      const def = invItemDefsByKey[st.item_key] || {};
      return {
        ...def,
        qty: st.quantity,
        key: st.item_key,
      };
    })
    .filter((it) => it.type !== "resource")
    .filter(
      (it) =>
        !term ||
        it.label?.toLowerCase().includes(term) ||
        it.key.includes(term)
    );

  listEl.innerHTML = "";
  emptyEl.classList.toggle("d-none", items.length > 0);

  items.forEach((it) => {
    const row = document.createElement("div");
    row.className = "inv-resource-item inv-tooltip inv-item-crafted";

    row.innerHTML = `
      <div class="inv-resource-icon-wrapper">
        ${
          it.icon
            ? `<img src="${it.icon}" alt="${it.label}" />`
            : `<div class="inv-resource-placeholder">-</div>`
        }
        <span class="inv-resource-qty-badge">${it.qty}</span>
      </div>

      <div class="inv-tooltip-content">
        <div class="inv-tooltip-title">${it.label || it.key}</div>
        <div class="inv-tooltip-sub">${it.key}</div>
        <div class="inv-tooltip-body">${it.description || ""}</div>
      </div>
    `;
    listEl.appendChild(row);
  });
}

/* ---------------------------------------------------------------------------
   Rendering – Cards
--------------------------------------------------------------------------- */

function renderCardList(filterText = "") {
  const listEl = $("invCardsList");
  const emptyEl = $("invCardsEmpty");
  if (!listEl || !emptyEl) return;

  const term = filterText.toLowerCase().trim();
  const typeFilter = ($("invCardTypeFilter")?.value || "all").toLowerCase();

  const items = invCards.filter((c) => {
    if ((c.owned_qty || 0) <= 0) return false;
    if (term && !c.label.toLowerCase().includes(term)) return false;
    if (typeFilter !== "all") {
      return normalizeCardCategory(c.type) === typeFilter;
    }
    return true;
  });

  listEl.innerHTML = "";
  emptyEl.classList.toggle("d-none", items.length > 0);

  items.forEach((c) => {
    const row = document.createElement("div");
    row.className = "inv-card-tile";
    row.style.cursor = "pointer";

    row.innerHTML = `
      <div class="inv-card-image-wrapper">
        <img src="${c.icon}" alt="${c.label}" />
        <span class="inv-card-qty-badge">x${c.owned_qty}</span>
      </div>
      <div class="inv-card-name">${c.label}</div>
    `;

    row.addEventListener("click", () => openCardModal(c));
    listEl.appendChild(row);
  });
}

/* ---------------------------------------------------------------------------
   Tabs & filters
--------------------------------------------------------------------------- */

function setupInventoryTabs() {
  const map = {
    invTabResources: "invPanelResources",
    invTabTreasure: "invPanelTreasure",
    invTabItems: "invPanelItems",
    invTabCards: "invPanelCards",
  };

  Object.entries(map).forEach(([tabId, panelId]) => {
    $(tabId)?.addEventListener("click", () => {
      Object.keys(map).forEach((t) =>
        $(t)?.classList.remove("inv-tab-active")
      );
      Object.values(map).forEach((p) =>
        $(p)?.classList.remove("inv-panel-active")
      );
      $(tabId).classList.add("inv-tab-active");
      $(panelId).classList.add("inv-panel-active");
    });
  });
}

function setupFilters() {
  $("invResourceFilter")?.addEventListener("input", (e) =>
    renderResourceList(e.target.value)
  );
  $("invTreasureFilter")?.addEventListener("input", (e) =>
    renderTreasureList(e.target.value)
  );
  $("invItemFilter")?.addEventListener("input", (e) =>
    renderItemList(e.target.value)
  );
  $("invCardFilter")?.addEventListener("input", (e) =>
    renderCardList(e.target.value)
  );
  $("invCardTypeFilter")?.addEventListener("change", () =>
    renderCardList($("invCardFilter")?.value || "")
  );
}

/* ---------------------------------------------------------------------------
   Data loading
--------------------------------------------------------------------------- */

async function loadInventoryData() {
  const s = await http("GET", "/api/state");
  if (!s.ok) return alert("Erreur inventaire");

  const state = s.data || {};

  // ✅ DEBUG : Vérifier les données reçues
  console.log("[INV] State received:", state);
  console.log("[INV] Resources sample:", state.resources?.slice(0, 3));

  // Resource defs
  invResourceDefsByKey = {};
  (state.resources || []).forEach((r) => {
    // ✅ DEBUG : Vérifier chaque ressource
    if (r.key === 'branch') {
      console.log("[INV] Branch resource:", r);
    }
    invResourceDefsByKey[r.key] = r;
  });

  // ✅ DEBUG : Vérifier invResourceDefsByKey après chargement
  console.log("[INV] invResourceDefsByKey['branch']:", invResourceDefsByKey['branch']);

  // Inventory split by kind
  invResources = [];
  invTreasureResources = [];

  (state.inventory || []).forEach((st) => {
    const def = invResourceDefsByKey[st.resource];
    if (!def) return;

    if (isResourceKind(def.kind, "treasure")) {
      invTreasureResources.push(st);
    } else if (isResourceKind(def.kind, "resource")) {
      invResources.push(st);
    }
  });

  renderResourceList("");
  renderTreasureList("");

  // Items ✅ MODIFIÉ : Utiliser it.label au lieu de it.label_fr/label_en
  invItems = [];
  invItemDefsByKey = {};
  (state.items || []).forEach((it) => {
    invItems.push({ item_key: it.item_key, quantity: it.qty });
    invItemDefsByKey[it.item_key] = {
      label: it.label || it.item_key,  // ✅ Déjà traduit par le backend
      icon: it.icon,
      type: it.type,
      category: it.category,
      description: it.description || '',  // ✅ Déjà traduit par le backend
    };
  });
  renderItemList("");

  // Cards
  invCards = state.cards || [];
  populateCardTypeFilterOptions();
  renderCardList("");
}

/* ---------------------------------------------------------------------------
   Card detail modal
--------------------------------------------------------------------------- */

const RARITY_LABELS = {
  common:    { label: "Commune",    color: "#94a3b8" },
  uncommon:  { label: "Peu commune", color: "#4ade80" },
  rare:      { label: "Rare",       color: "#60a5fa" },
  epic:      { label: "Épique",     color: "#a78bfa" },
  legendary: { label: "Légendaire", color: "#fbbf24" },
};

const TYPE_LABELS = {
  land_access:     "Accès Terre",
  craft_recipe:    "Recette Craft",
  craft_access:    "Accès Craft",
  land_loot_boost: "Boost Récolte",
  resource_boost:  "Boost Ressource",
  xp_boost:        "Boost XP",
  cooldown_boost:  "Boost Cooldown",
  building_access: "Bâtiment",
  land_slot:       "Emplacement",
  passive_boost:   "Boost Passif",
};

function openCardModal(card) {
  const modal    = $("invCardModal");
  const imgEl    = $("invCardModalImg");
  const qtyEl    = $("invCardModalQty");
  const rarityEl = $("invCardModalRarity");
  const titleEl  = $("invCardModalTitle");
  const typeEl   = $("invCardModalType");
  const descEl   = $("invCardModalDesc");
  const gpEl     = $("invCardModalGameplay");
  if (!modal) return;

  if (imgEl)  { imgEl.src = card.icon || ""; imgEl.alt = card.label || ""; }
  if (qtyEl)  { qtyEl.textContent = `x${card.owned_qty}`; }

  const rarity = RARITY_LABELS[card.rarity] || null;
  if (rarityEl) {
    rarityEl.textContent = rarity ? rarity.label : "";
    rarityEl.style.color = rarity ? rarity.color : "#94a3b8";
    rarityEl.hidden = !rarity;
  }

  if (titleEl) titleEl.textContent = card.label || card.key || "";
  if (typeEl)  typeEl.textContent  = TYPE_LABELS[card.type] || card.type || "";
  if (descEl)  descEl.textContent  = card.description || "";

  // Gameplay bonuses
  if (gpEl) {
    const gp = card.gameplay || {};
    const entries = Object.entries(gp);
    if (entries.length) {
      gpEl.innerHTML = entries.map(([k, v]) =>
        `<div class="inv-card-modal-gp-row"><span>${k.replace(/_/g, " ")}</span><strong>${v}</strong></div>`
      ).join("");
      gpEl.hidden = false;
    } else {
      gpEl.hidden = true;
    }
  }

  modal.hidden = false;
}

function closeCardModal() {
  const modal = $("invCardModal");
  if (modal) modal.hidden = true;
}

/* ---------------------------------------------------------------------------
   Init
--------------------------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", async () => {
  setupInventoryTabs();
  setupFilters();
  await loadInventoryData();

  $("invCardModalClose")?.addEventListener("click", closeCardModal);
  $("invCardModal")?.addEventListener("click", (e) => {
    if (e.target === $("invCardModal")) closeCardModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeCardModal();
  });

  // First-visit tutorial for this page
  if (typeof window.TutorialApp !== "undefined") {
    // Small delay so the page renders fully before the spotlight measures the tabs
    setTimeout(() => window.TutorialApp.onInventoryVisit(), 600);
  }
});
