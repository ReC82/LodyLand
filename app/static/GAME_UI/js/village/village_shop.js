// static/GAME_UI/js/village/village_shop.js
// ============================================================
// VILLAGE SHOP — filters, search, buy, card detail modal
// ============================================================

/* global http, VillageCommon, VS_I18N */

const RARITY_COLORS = {
  basic:     { bg: "#6c757d", text: "#fff" },
  common:    { bg: "#6c757d", text: "#fff" },
  uncommon:  { bg: "#22c55e", text: "#fff" },
  rare:      { bg: "#3b82f6", text: "#fff" },
  epic:      { bg: "#a855f7", text: "#fff" },
  legendary: { bg: "#f59e0b", text: "#000" },
};

// Build a lookup map from the JSON injected by the template
const ITEMS_BY_KEY = {};
(window.VS_ITEMS || []).forEach((item) => {
  ITEMS_BY_KEY[item.offer_key] = item;
});

// ============================================================
// Modal d'info / erreur thémée (remplace les alert() natifs)
// ============================================================
function showShopInfoModal({ icon = "⚠️", title = "", msg = "" } = {}) {
  const overlay = document.getElementById("shopInfoOverlay");
  if (!overlay) { alert(msg); return; }
  document.getElementById("shopInfoIcon").textContent  = icon;
  document.getElementById("shopInfoTitle").textContent = title;
  document.getElementById("shopInfoMsg").textContent   = msg;
  overlay.style.display = "flex";
}

function closeShopInfoModal() {
  const overlay = document.getElementById("shopInfoOverlay");
  if (overlay) overlay.style.display = "none";
}

// ============================================================
// Init
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  setupFiltersAndSearch();
  setupBuyButtons();
  setupCardModal();
  setupShopInfoModal();
});

function setupShopInfoModal() {
  const overlay = document.getElementById("shopInfoOverlay");
  const closeBtn = document.getElementById("shopInfoCloseBtn");
  if (!overlay) return;

  closeBtn?.addEventListener("click", closeShopInfoModal);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeShopInfoModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && overlay.style.display === "flex") closeShopInfoModal();
  });
}

// ============================================================
// Buy buttons
// ============================================================
function setupBuyButtons() {
  document.querySelectorAll(".vs-buy-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation(); // don't open modal when clicking buy
      handleBuy(btn);
    });
  });
}

async function handleBuy(btn) {
  const offerKey = btn.dataset.offerKey;
  if (!offerKey || btn.disabled) return;

  btn.disabled = true;
  const oldLabel = btn.textContent;
  const i18n = window.VS_I18N?.modal || {};
  btn.textContent = i18n.buying || "…";

  try {
    const r = await http("POST", "/api/village/cardshop/buy", { offer_key: offerKey });

    if (!r.ok) {
      btn.disabled = false;
      btn.textContent = oldLabel;
      const errData = r.data || {};

      if (errData.error === "prerequisite_card_required") {
        const reqLabel = errData.requires_card_label || (errData.requires_card || "").replace(/_/g, " ");
        showShopInfoModal({
          icon: "🔒",
          title: i18n.err_prereq_title || "Prérequis manquant",
          msg: (i18n.err_prereq_msg || "Tu dois d'abord posséder la carte :") + " « " + reqLabel + " »",
        });
      } else if (errData.error === "craft_access_already_upgraded") {
        const higherLabel = errData.owns_higher_card_label || (errData.owns_higher_card || "").replace(/_/g, " ");
        showShopInfoModal({
          icon: "⬆️",
          title: i18n.err_upgraded_title || "Déjà amélioré",
          msg: (i18n.err_upgraded_msg || "Tu possèdes déjà une version supérieure :") + " « " + higherLabel + " »",
        });
      } else {
        showShopInfoModal({
          icon: "❌",
          title: i18n.buy_error || "Achat impossible",
          msg: errData.error || "?",
        });
      }
      return;
    }

    if (window.VillageCommon?.handlePlayerAndLevelFromResponse) {
      VillageCommon.handlePlayerAndLevelFromResponse(r.data);
    }

    btn.textContent = i18n.bought || "✔";
    btn.classList.replace("btn-success", "btn-secondary");
  } catch (e) {
    console.error("[village_shop] network error", e);
    showShopInfoModal({
      icon: "📡",
      title: i18n.network_error || "Erreur réseau",
      msg: String(e?.message || e || "?"),
    });
    btn.disabled = false;
    btn.textContent = oldLabel;
  }
}

// ============================================================
// Card detail modal
// ============================================================
function setupCardModal() {
  const modalEl   = document.getElementById("cardDetailModal");
  const overlayEl = document.getElementById("cardDetailOverlay");
  if (!modalEl || !overlayEl) {
    console.error("[village_shop] modal elements not found");
    return;
  }

  const mdlBuyBtn = document.getElementById("mdl-buy-btn");
  let currentOfferKey = null;

  function openModal() { overlayEl.style.display = "flex"; }
  function closeModal() { overlayEl.style.display = "none"; }

  // Close on overlay click (outside modal box)
  overlayEl.addEventListener("click", (e) => {
    if (e.target === overlayEl) closeModal();
  });

  // Close buttons
  document.querySelectorAll("[data-close-card-modal]").forEach((btn) => {
    btn.addEventListener("click", closeModal);
  });

  // ESC key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  // Open on card click (not on buy button)
  document.getElementById("vsOffersGrid").addEventListener("click", (e) => {
    if (e.target.closest(".vs-buy-btn")) return;
    const card = e.target.closest(".vs-offer-card");
    if (!card) return;

    currentOfferKey = card.dataset.offerKey;
    const item = ITEMS_BY_KEY[currentOfferKey];
    if (!item) return;

    populateModal(item);
    openModal();
  });

  // Buy from modal
  mdlBuyBtn.addEventListener("click", () => {
    if (!currentOfferKey) return;
    const realBtn = document.querySelector(`.vs-buy-btn[data-offer-key="${currentOfferKey}"]`);
    if (realBtn && !realBtn.disabled) realBtn.click();
    closeModal();
  });
}

function populateModal(item) {
  // Image
  const imgWrap = document.getElementById("mdl-img-wrap");
  const img     = document.getElementById("mdl-img");
  if (item.icon) {
    img.src = item.icon;
    img.alt = item.title || "";
    imgWrap.style.display = "";
  } else {
    imgWrap.style.display = "none";
  }

  // Rareté
  const rarity   = (item.rarity || "").toLowerCase();
  const rarityEl = document.getElementById("mdl-rarity");
  const rc        = RARITY_COLORS[rarity] || RARITY_COLORS.basic;
  rarityEl.textContent       = rarity;
  rarityEl.style.background  = rc.bg;
  rarityEl.style.color       = rc.text;
  rarityEl.style.display     = rarity ? "" : "none";

  // Titre + description
  document.getElementById("mdl-title").textContent = item.title || item.label || "";
  document.getElementById("mdl-desc").textContent  = item.description || "";

  // Gameplay / effet
  const gpHtml  = renderGameplay(item.card_gameplay || {});
  const gpBlock = document.getElementById("mdl-gameplay-block");
  if (gpHtml) {
    document.getElementById("mdl-gameplay-content").innerHTML = gpHtml;
    gpBlock.style.display = "";
  } else {
    gpBlock.style.display = "none";
  }

  // Prérequis d'achat
  const prereqBlock = document.getElementById("mdl-prereq-block");
  const prereqName  = document.getElementById("mdl-prereq-name");
  if (prereqBlock && prereqName) {
    if (item.requires_card_label) {
      prereqName.textContent  = item.requires_card_label;
      prereqBlock.style.display = "";
    } else {
      prereqBlock.style.display = "none";
    }
  }

  // Prix
  const coins = item.price_coins || 0;
  const diams  = item.price_diams  || 0;
  document.getElementById("mdl-price-coins").style.display = coins > 0 ? "" : "none";
  document.getElementById("mdl-price-diams").style.display = diams  > 0 ? "" : "none";
  document.getElementById("mdl-price-free").style.display  = (coins <= 0 && diams <= 0) ? "" : "none";
  document.getElementById("mdl-price-coins-val").textContent = coins;
  document.getElementById("mdl-price-diams-val").textContent = diams;

  // Possédé / limite
  document.getElementById("mdl-owned").textContent    = item.owned_qty ?? 0;
  document.getElementById("mdl-max-owned").textContent = item.max_owned != null ? item.max_owned : "∞";

  // Bouton achat
  const mdlBuyBtn   = document.getElementById("mdl-buy-btn");
  const cantReasonEl = document.getElementById("mdl-cant-buy-reason");

  const mi18n = window.VS_I18N?.modal || {};
  if (item.can_buy) {
    mdlBuyBtn.disabled    = false;
    mdlBuyBtn.textContent = mi18n.buy || "Buy";
    mdlBuyBtn.style.background = "#198754";
    cantReasonEl.style.display = "none";
  } else {
    mdlBuyBtn.disabled    = true;
    mdlBuyBtn.textContent = mi18n.unavailable || "—";
    mdlBuyBtn.style.background = "#6c757d";
    if (item.cant_buy_reason) {
      cantReasonEl.textContent   = item.cant_buy_reason;
      cantReasonEl.style.display = "";
    } else {
      cantReasonEl.style.display = "none";
    }
  }
}

function renderGameplay(gp) {
  if (!gp || typeof gp !== "object") return null;
  const g = window.VS_I18N?.gameplay || {};
  const lines = [];

  // boost de ressource
  const b = gp.boost;
  if (b && b.type && b.amount) {
    const pct = (b.amount > 0 ? "+" : "") + Math.round(b.amount * 100) + "%";
    lines.push(`${g.harvest_bonus || "Bonus"} : <strong>${pct}</strong> — <em>${b.type.replace(/_/g, " ")}</em>`);
  }

  // passive boost (XP, coins)
  const pb = gp.passive_boost;
  if (pb) {
    if (pb.xp_multiplier && pb.xp_multiplier !== 1)
      lines.push(`${g.xp_multiplier || "XP ×"} <strong>${pb.xp_multiplier}</strong> ${g.xp_suffix || ""}`);
    if (pb.coin_multiplier && pb.coin_multiplier !== 1)
      lines.push(`${g.coin_multiplier || "Coins ×"} <strong>${pb.coin_multiplier}</strong> ${g.xp_suffix || ""}`);
  }

  // ressource cible
  if (gp.target_resource)
    lines.push(`${g.target_resource || "Target"} : <strong>${gp.target_resource.replace(/_/g, " ")}</strong>`);

  // accès / débloque
  if (gp.unlocks)
    lines.push(`${g.unlocks || "Unlocks"} : <strong>${String(gp.unlocks).replace(/_/g, " ")}</strong>`);

  return lines.length ? lines.join("<br>") : null;
}

// ============================================================
// Filters + search
// ============================================================
function setupFiltersAndSearch() {
  const tabs = document.querySelectorAll(".vs-filter-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("vs-filter-active"));
      tab.classList.add("vs-filter-active");
      applyCardFilters();
    });
  });

  const searchInput = document.getElementById("vsCardSearch");
  if (searchInput) searchInput.addEventListener("input", applyCardFilters);

  applyCardFilters();
}

function applyCardFilters() {
  const activeTab     = document.querySelector(".vs-filter-tab.vs-filter-active");
  const activeType    = (activeTab?.dataset.filterType || "all").toLowerCase();
  const query         = (document.getElementById("vsCardSearch")?.value || "").trim().toLowerCase();

  document.querySelectorAll(".vs-offer-card").forEach((card) => {
    const cardType   = (card.dataset.filterType || "other").toLowerCase();
    const cardSearch = (card.dataset.search || "").toLowerCase();

    let visible = (activeType === "all" || cardType === activeType);
    if (visible && query) visible = cardSearch.includes(query);

    card.style.display = visible ? "" : "none";
  });
}
