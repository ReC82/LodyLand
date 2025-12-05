// static/GAME_UI/js/village/village_trades.js
// ============================================================
// VILLAGE TRADES — logique d'affichage et d'exécution des trades
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  console.log("[village_trades] init");

  const filtersContainer = document.getElementById("village-trades-land-filters");
  const listContainer = document.getElementById("village-trades-list");

  if (!filtersContainer || !listContainer) {
    console.warn("[village_trades] containers not found in DOM");
    return;
  }

  let currentLandFilter = "all";

  async function fetchTrades(landSlug = "all") {
    const params = new URLSearchParams();
    if (landSlug && landSlug !== "all") {
      params.set("land", landSlug);
    }

    const url = "/api/village/trades" + (params.toString() ? `?${params.toString()}` : "");

    listContainer.innerHTML = `
      <p class="text-muted small mb-0">Chargement des échanges...</p>
    `;

    try {
      const resp = await fetch(url, { method: "GET", headers: { "Accept": "application/json" } });
      if (!resp.ok) {
        listContainer.innerHTML = `
          <div class="alert alert-danger mb-0">
            Impossible de charger les échanges (code ${resp.status}).
          </div>
        `;
        return;
      }

      const data = await resp.json();
      if (!data.ok) {
        listContainer.innerHTML = `
          <div class="alert alert-danger mb-0">
            Impossible de charger les échanges : ${data.error || "erreur inconnue"}.
          </div>
        `;
        return;
      }

      renderFilters(data.available_lands || []);
      renderTrades(data.trades || []);
    } catch (err) {
      console.error("[village_trades] fetch error:", err);
      listContainer.innerHTML = `
        <div class="alert alert-danger mb-0">
          Erreur réseau lors du chargement des échanges.
        </div>
      `;
    }
  }

  function renderFilters(availableLands) {
    filtersContainer.innerHTML = "";

    if (!availableLands.length) {
      filtersContainer.innerHTML = `
        <span class="text-muted small">Aucun échange disponible pour le moment.</span>
      `;
      return;
    }

    availableLands.forEach((land) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm village-trade-land-btn";
      if (land.slug === currentLandFilter || (currentLandFilter === "all" && land.slug === "all")) {
        btn.classList.add("active");
      }
      btn.dataset.landSlug = land.slug;
      btn.innerHTML = `
        ${land.label || land.slug}
        <span class="badge bg-secondary ms-1">${land.count ?? 0}</span>
      `;
      btn.addEventListener("click", () => {
        currentLandFilter = land.slug;
        // Refresh active state
        document.querySelectorAll(".village-trade-land-btn").forEach((b) => {
          b.classList.toggle("active", b.dataset.landSlug === currentLandFilter);
        });
        fetchTrades(currentLandFilter);
      });
      filtersContainer.appendChild(btn);
    });
  }

  function renderTrades(trades) {
    if (!trades.length) {
      listContainer.innerHTML = `
        <p class="text-muted small mb-0">
          Aucun échange disponible pour ce filtre. Récolte davantage de ressources rares pour débloquer plus d'options.
        </p>
      `;
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.className = "village-trades-list";

    trades.forEach((t) => {
      const canBuy = !!t.can_buy;
      const reason = t.cant_buy_reason || "";
      const res = t.resource_cost || {};
      const rarity = (t.rarity || "common").toLowerCase();

      const card = document.createElement("div");
      card.className = "village-trade-card vq-card mb-2";

      card.innerHTML = `
        <div class="village-trade-main">
          <div class="village-trade-left">
            <div class="village-trade-image-wrapper rarity-${rarity}">
              ${t.image ? `<img src="${t.image}" alt="${t.label || t.card_key}" class="village-trade-image" />` : ""}
            </div>
            <div class="village-trade-text">
              <div class="village-trade-title-row">
                <h3 class="h6 mb-1">${t.label || t.card_key}</h3>
                <span class="badge bg-dark text-uppercase village-trade-rarity">${t.rarity || "?"}</span>
              </div>
              <p class="text-muted small mb-1">${t.description || ""}</p>
              <p class="text-muted small mb-0">
                Land : <strong>${t.land_tag || "?"}</strong>
              </p>
            </div>
          </div>

          <div class="village-trade-right">
            <div class="mb-2 small">
              <div class="mb-1">
                <span class="text-muted">Coût :</span>
                ${res.icon ? `<img src="${res.icon}" class="village-trade-resource-icon ms-1 me-1" alt="${res.label || res.resource_key}" />` : ""}
                <strong>${res.amount ?? "?"}</strong>
                <span class="text-muted">x</span>
                <span>${res.label || res.resource_key}</span>
              </div>
              <div class="text-muted">
                Tu as : <strong>${(res.player_qty ?? 0).toFixed(0)}</strong>
              </div>
            </div>

            <div class="mb-2 small">
              ${t.stock_global >= 0
                ? `<span class="text-muted">Stock global : </span><strong>${t.stock_global}</strong>`
                : `<span class="text-muted">Stock global : </span><strong>∞</strong>`
              }
            </div>

            <button
              type="button"
              class="btn btn-sm btn-success village-trade-btn"
              data-card-key="${t.card_key}"
              ${canBuy ? "" : "disabled"}
            >
              Échanger
            </button>

            ${!canBuy && reason
              ? `<div class="text-danger small mt-1">${reason}</div>`
              : ""
            }
          </div>
        </div>
      `;

      wrapper.appendChild(card);
    });

    listContainer.innerHTML = "";
    listContainer.appendChild(wrapper);

    // Hook des boutons "Échanger"
    listContainer.querySelectorAll(".village-trade-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cardKey = btn.dataset.cardKey;
        if (!cardKey) return;
        performTrade(cardKey, btn);
      });
    });
  }

  async function performTrade(cardKey, buttonEl) {
    if (!confirm("Confirmer cet échange ?")) {
      return;
    }

    buttonEl.disabled = true;
    buttonEl.textContent = "Échange...";

    try {
      const resp = await fetch("/api/village/trades/execute", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({ card_key: cardKey }),
      });

      const data = await resp.json().catch(() => ({}));

      if (!resp.ok || !data.ok) {
        const msg = data.error || "Erreur lors de l'échange.";
        alert(msg);
        buttonEl.disabled = false;
        buttonEl.textContent = "Échanger";
        return;
      }

      // Succès: on re-charge la liste (pour mettre à jour stock & can_buy)
      await fetchTrades(currentLandFilter);
    } catch (err) {
      console.error("[village_trades] performTrade error:", err);
      alert("Erreur réseau lors de l'échange.");
      buttonEl.disabled = false;
      buttonEl.textContent = "Échanger";
    }
  }

  // Initial load
  fetchTrades(currentLandFilter);
});
