/*
  File: static/GAME_UI/js/shop_app.js
  Purpose: Logic for the Shop page (selling resources for coins).
  Notes:
  - Uses http() and $() helpers from common.js
  - Uses renderPlayer() / currentPlayer from game_app.js to refresh HUD
*/

const SHOP_SELL_PRICE_PER_UNIT = 1; // pour l'instant 1 coin par ressource

function formatPriceOption(price) {
  // price = { coins, diams, resources: { key: qty } }
  if (!price) return "Gratuit";

  const parts = [];
  const coins = price.coins || 0;
  const diams = price.diams || 0;
  const resCosts = price.resources || {};

  if (coins) parts.push(`${coins} 🪙`);
  if (diams) parts.push(`${diams} 💎`);

  Object.entries(resCosts).forEach(([resKey, qty]) => {
    parts.push(`${qty} ${resKey}`);
  });

  return parts.length ? parts.join(" + ") : "Gratuit";
}


async function loadShop() {
  const r = await http("GET", "/api/state");
  if (!r.ok) {
    alert("Impossible de charger la boutique.");
    return;
  }

  const state = r.data;

  // Map clé de ressource -> définition
  const defsByKey = {};
  (state.resources || []).forEach((res) => {
    defsByKey[res.key] = res;
  });

  renderSellTab(state.inventory || [], defsByKey);
}

function renderSellTab(inventory, defsByKey) {
  const container = $("shopSellList");
  if (!container) return;

  if (!inventory.length) {
    container.innerHTML = `<div class="shop-empty">
      Tu n'as aucune ressource à vendre pour l'instant.
    </div>`;
    return;
  }

  container.innerHTML = "";

  inventory.forEach((item) => {
    const def = defsByKey[item.resource] || {};
    const label = def.label || item.resource || "???";
    const icon = def.icon || null;
    const unitPrice = def.base_sell_price ?? 1;

    const row = document.createElement("div");
    row.className = "shop-sell-row";
    row.dataset.resource = item.resource;

    row.innerHTML = `
      <div class="shop-sell-main">
        <div class="shop-sell-icon">
          ${
            icon
              ? `<img src="${icon}" alt="${label}" style="width:24px;height:24px;">`
              : "📦"
          }
        </div>
        <div>
          <div class="shop-sell-name">${label}</div>
          <div class="shop-sell-sub">Tu en as ${item.qty}</div>
        </div>
      </div>
      <div class="shop-sell-controls">
        <input class="shop-sell-input" type="number"
               min="1" max="${item.qty}" value="1" />
        <div class="shop-sell-price">
          Prix : ${unitPrice} coin(s) / unité
        </div>
        <button class="shop-sell-btn">Vendre</button>
      </div>
    `;

    const input = row.querySelector(".shop-sell-input");
    const btn = row.querySelector(".shop-sell-btn");
    btn.addEventListener("click", async () => {
      const qty = parseInt(input.value, 10) || 0;
      await sellResource(item.resource, qty);
    });

    container.appendChild(row);
  });
}


async function loadSellInventory() {
  const listEl = $("shopSellList");
  const emptyEl = $("shopSellEmpty");

  if (!listEl || !emptyEl) return;

  listEl.innerHTML = "";
  emptyEl.classList.add("d-none");

  const r = await http("GET", "/api/inventory");
  if (!r.ok) {
    listEl.innerHTML =
      "<div class='text-danger'>Erreur de chargement de l'inventaire.</div>";
    return;
  }

  const inv = r.data || [];
  const sellable = inv.filter((item) => (item.quantity || item.qty || 0) > 0);

  if (!sellable.length) {
    emptyEl.classList.remove("d-none");
    return;
  }

  sellable.forEach((item) => {
    const key = item.resource_key || item.key || item.code;
    const label = item.label || key;
    const qty = item.quantity ?? item.qty ?? 0;
    const icon = item.icon || null;

    const card = document.createElement("div");
    card.className = "shop-sell-item";
    card.dataset.resourceKey = key;

    card.innerHTML = `
      <div class="shop-sell-header">
        <div class="shop-sell-icon">
          ${icon ? `<img src="${icon}" alt="${label}" style="width:24px;height:24px;">` : "📦"}
        </div>
        <div>
          <div class="shop-sell-name">${label}</div>
          <div class="shop-sell-qty">Tu en as <strong>${qty}</strong></div>
        </div>
      </div>
      <div class="shop-sell-footer">
        <input
          type="number"
          min="1"
          max="${qty}"
          value="1"
          class="form-control form-control-sm"
        />
        <div class="shop-sell-price">
          Prix: <span class="shop-sell-price-value">${SHOP_SELL_PRICE_PER_UNIT}</span> coin(s) / unité
        </div>
        <button class="shop-sell-button">Vendre</button>
      </div>
    `;

    const input = card.querySelector("input[type='number']");
    const btn = card.querySelector(".shop-sell-button");

    btn.addEventListener("click", async () => {
      const amount = Number(input.value);
      if (!amount || amount <= 0 || amount > qty) {
        alert("Quantité invalide.");
        return;
      }
      await sellResource(key, amount);
    });

    listEl.appendChild(card);
  });
}

async function sellResource(resourceKey, amount) {
  if (!amount || amount <= 0) {
    alert("Quantité invalide.");
    return;
  }

  const r = await http("POST", "/api/sell", {
    resource: resourceKey,
    qty: amount,
  });

  if (!r.ok) {
    const err = r.data || {};
    alert("Vente impossible : " + (err.error || `Erreur serveur (${r.status})`));
    console.error("Sell error payload:", err);
    return;
  }

  const d = r.data;

  // Utiliser d.sold.* (nouvelle structure)
  const sold = d.sold || {};
  alert(
    `Tu as vendu ${sold.qty}x ${sold.resource} pour +${sold.gain} coins.`
  );

  // MAJ HUD joueur
  if (d.player) {
    currentPlayer = {
      ...d.player,
      next_xp: d.player.next_xp ?? d.player.nextXp ?? null,
    };
    renderPlayer(currentPlayer);
  }

  // Recharger la liste de ressources
  await loadShop();
}


function setupShopTabs() {
  const tabSell = $("shopTabSell");
  const tabCards = $("shopTabCards");
  const panelSell = $("shopPanelSell");
  const panelCards = $("shopPanelCards")

  if (!tabSell || !panelSell) return;

  tabSell.addEventListener("click", () => {
    tabSell.classList.add("shop-tab-active");
    if (tabCards) tabCards.classList.remove("shop-tab-active");

    panelSell.classList.add("shop-panel-active");
    if (panelCards) panelCards.classList.remove("shop-panel-active");
  });

  if (tabCards && panelCards) {
    tabCards.addEventListener("click", () => {
      if (tabCards.disabled) return;
      tabCards.classList.add("shop-tab-active");
      tabSell.classList.remove("shop-tab-active");

      panelCards.classList.add("shop-panel-active");
      panelSell.classList.remove("shop-panel-active");
    });
  }
}

// Charge la liste des cartes depuis /api/cards et met à jour le HUD si besoin
async function loadCardShop() {
  console.log("Loading card shop...");
  const r = await http("GET", "/api/cards");
  if (!r.ok) {
    alert("Impossible de charger les cartes.");
    console.error("Card shop error:", r);
    return;
  }

  const cards = r.data || [];

  // On a déjà currentPlayer rempli par /api/me via game_app.js,
  // donc ici pas besoin de recharger le joueur.
  renderCardShopList(cards);
}

function renderCardShopList(cards) {
  console.log("Rendering card shop list:", cards);
  const container = document.getElementById("shopCardsList");
  if (!container) return;

  if (!cards.length) {
    container.innerHTML = `
      <div class="shop-empty text-muted">
        Aucune carte disponible pour le moment.
      </div>`;
    return;
  }

  const coins = currentPlayer?.coins ?? 0;
  const diams = currentPlayer?.diams ?? 0;

  const html = cards
    .map((card) => {
      const prices = card.prices || [];
      const shopCfg = card.shop || {};
      const owned = card.owned_qty || 0;
      const maxOwned = shopCfg.max_owned;

      // Sécurité : si aucun prix défini → une option "gratuite"
      const effectivePrices = prices.length ? prices : [{}];

      const hasMultiplePrices = effectivePrices.length > 1;
      const firstPrice = effectivePrices[0];

      const priceText = formatPriceOption(firstPrice);

      let canBuy = true;
      let btnLabel = "Acheter";

      // On ne bloque que si tu as atteint le max_owned.
      // Les vérifs de coins/diams/ressources sont faites par le backend.
      if (maxOwned !== null && maxOwned !== undefined && owned >= maxOwned) {
        canBuy = false;
        btnLabel = "Max atteint";
      }

      const priceSelectHtml = hasMultiplePrices
        ? `
          <select class="shop-card-price-select">
            ${effectivePrices
              .map(
                (p, idx) =>
                  `<option value="${idx}">${formatPriceOption(p)}</option>`
              )
              .join("")}
          </select>
        `
        : `<div class="shop-card-price">${priceText}</div>`;

      return `
        <div class="shop-card-row" data-card-key="${card.key}">
          <div class="shop-card-main">
            <div class="shop-card-icon">
              ${
                card.icon
                  ? `<img src="${card.icon}" alt="${card.label}" />`
                  : "🃏"
              }
            </div>
            <div class="shop-card-text">
              <div class="shop-card-title">${card.label}</div>
              <div class="shop-card-desc">${card.description || ""}</div>
              <div class="shop-card-meta">
                Type : ${card.type}
                ${
                  owned > 0
                    ? ` • Tu en possèdes <strong>${owned}</strong>`
                    : ""
                }
              </div>
            </div>
          </div>

          <div class="shop-card-side">
            ${priceSelectHtml}
            <button
              class="shop-card-buy-btn"
              ${canBuy ? "" : "disabled"}
            >
              ${btnLabel}
            </button>
          </div>
        </div>
      `;
    })
    .join("");

  container.innerHTML = html;

  // Hook sur les boutons "Acheter"
  container.querySelectorAll(".shop-card-row").forEach((row) => {
    const key = row.dataset.cardKey;
    const btn = row.querySelector(".shop-card-buy-btn");
    const select = row.querySelector(".shop-card-price-select");

    if (!btn || !key || btn.disabled) return;

    btn.addEventListener("click", () => {
      let priceIndex = 0;
      if (select) {
        priceIndex = parseInt(select.value, 10) || 0;
      }
      buyCard(key, priceIndex);
    });
  });
}


async function buyCard(cardKey, priceIndex = 0) {
  if (!cardKey) return;

  const confirmBuy = confirm("Acheter cette carte ?");
  if (!confirmBuy) return;

  console.log("Buying card", cardKey, "with priceIndex", priceIndex);

  const r = await http("POST", "/api/cards/buy", {
    card_key: cardKey,
    price_index: priceIndex,
    // pas besoin de playerId côté GAME_UI, le backend prend le cookie
  });

  if (!r.ok) {
    const err = r.data || {};
    let msg = `Achat impossible : ${err.error || `Erreur serveur (${r.status})`}`;

    if (err.error === "not_enough_coins") {
      msg = "Tu n'as pas assez de coins.";
    } else if (err.error === "not_enough_diams") {
      msg = "Tu n'as pas assez de diams.";
    } else if (err.error === "max_owned_reached") {
      msg = "Tu possèdes déjà le nombre maximum de cette carte.";
    }

    alert(msg);
    console.error("Buy card error:", err);
    return;
  }

  const d = r.data;
  const c = d.card || {};

  alert(`Tu as acheté 1x "${c.label || c.key}".`);

  // MAJ HUD à partir de la réponse
  if (d.player) {
    currentPlayer = {
      ...currentPlayer,
      coins: d.player.coins,
      diams: d.player.diams,
    };
    renderPlayer(currentPlayer);
  }

  // Recharger la liste de cartes pour mettre à jour owned_qty / boutons
  await loadCardShop();
}



document.addEventListener("DOMContentLoaded", async () => {
  setupShopTabs();
 
  loadCardShop();
  
  await loadShop();
});
