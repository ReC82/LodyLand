// static/GAME_UI/js/village/village_shop.js
// ============================================================
// VILLAGE SHOP — Buy items/cards from the village offers
// + filters by type + search
// ============================================================

/* global $, http */

document.addEventListener("DOMContentLoaded", () => {
  console.log("[village_shop] init");

  setupBuyButtons();
  setupFiltersAndSearch();
});

/**
 * Attach click handlers on buy buttons.
 */
function setupBuyButtons() {
  const buttons = document.querySelectorAll(".vs-buy-btn");
  if (!buttons.length) return;

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => handleBuy(btn));
  });
}

/**
 * Handle a single buy click.
 * @param {HTMLButtonElement} btn
 */
async function handleBuy(btn) {
  const offerKey = btn.dataset.offerKey;
  console.log("[village_shop] clicked offerKey =", offerKey); // DEBUG

  if (!offerKey) {
    console.warn("[village_shop] Missing offerKey");
    return;
  }

  btn.disabled = true;
  const oldLabel = btn.textContent;
  btn.textContent = "Achat.";

  try {
    const r = await http("POST", "/api/village/cardshop/buy", {
      offer_key: offerKey,
    });

    if (!r.ok) {
      const err = r.data || {};
      console.error("[village_shop] error:", err);

      btn.disabled = false;
      btn.textContent = oldLabel;

      alert("Achat impossible : " + (err.error || "Erreur inconnue"));
      return;
    }

    const data = r.data;

    if (
      window.VillageCommon &&
      typeof VillageCommon.handlePlayerAndLevelFromResponse === "function"
    ) {
      VillageCommon.handlePlayerAndLevelFromResponse(data);
    }

    // Visual feedback on button
    btn.textContent = "Acheté ✔";
    btn.classList.remove("btn-success");
    btn.classList.add("btn-secondary");
    btn.style.opacity = 0.7;
  } catch (e) {
    console.error("[village_shop] network error", e);
    alert("Erreur réseau pendant l’achat.");
    btn.disabled = false;
    btn.textContent = oldLabel;
  }
}

/**
 * Setup tabs and search input for filtering cards.
 */
function setupFiltersAndSearch() {
  const tabs = document.querySelectorAll(".vs-filter-tab");
  const searchInput = document.getElementById("vsCardSearch");

  if (tabs.length) {
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        // Update active tab CSS
        tabs.forEach((t) => t.classList.remove("vs-filter-active"));
        tab.classList.add("vs-filter-active");

        applyCardFilters();
      });
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      applyCardFilters();
    });
  }

  // Initial pass
  applyCardFilters();
}

/**
 * Apply current tab + search filter on all offer cards.
 */
function applyCardFilters() {
  const activeTab = document.querySelector(".vs-filter-tab.vs-filter-active");
  const activeFilterType = activeTab
    ? (activeTab.dataset.filterType || "all").toLowerCase()
    : "all";

  const searchInput = document.getElementById("vsCardSearch");
  const query = (searchInput?.value || "").trim().toLowerCase();

  const cards = document.querySelectorAll(".vs-offer-card");
  if (!cards.length) return;

  cards.forEach((card) => {
    const cardFilterType = (card.dataset.filterType || "other").toLowerCase();
    const cardSearchText = (card.dataset.search || "").toLowerCase();

    let visible = true;

    // Filter by type tab
    if (activeFilterType !== "all") {
      visible = cardFilterType === activeFilterType;
    }

    // Filter by search query
    if (visible && query) {
      visible = cardSearchText.indexOf(query) !== -1;
    }

    card.style.display = visible ? "" : "none";
  });
}
