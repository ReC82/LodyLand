// static/GAME_UI/js/village/village_market.js
// ============================================================
// VILLAGE MARKET — Sell resources to villagers
// ------------------------------------------------------------
// - Uses /village/market/resources to list sellable resources
// - Uses /api/sell to perform sales (same logic as shop_app.js)
// - Uses VillageCommon.handlePlayerAndLevelFromResponse to refresh HUD
// ============================================================

/* global http, $ */

document.addEventListener("DOMContentLoaded", () => {
  console.log("[village_market] init");

  const tbody = $("market-rows");
  const msgBox = $("market-messages");

  if (!tbody) {
    console.warn("[village_market] #market-rows not found");
    return;
  }

  // ----------------------------------------------------------
  // Helpers
  // ----------------------------------------------------------

  function showMessage(type, text) {
    // type: "success" | "error" | "info"
    if (!msgBox) return;

    const cls =
      type === "success"
        ? "alert-success"
        : type === "error"
        ? "alert-danger"
        : "alert-secondary";

    msgBox.innerHTML = `
      <div class="alert ${cls} py-2 mb-2">
        ${text}
      </div>
    `;
  }

  function resourceIconPath(key) {
    // Simple convention: /static/assets/img/resources/<key>.png
    // Adapt if your project uses another naming strategy.
    return `/static/assets/img/resources/${key}.png`;
  }

  // ----------------------------------------------------------
  // Load sellable resources for current player
  // ----------------------------------------------------------

  function loadMarketResources() {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="text-center text-muted py-4">
          Chargement des ressources vendables...
        </td>
      </tr>
    `;

    http("GET", "/village/market/resources")
      .then((res) => {
        if (!res.ok) {
          console.error("[village_market] /village/market/resources error", res);
          tbody.innerHTML = `
            <tr>
              <td colspan="5" class="text-center text-danger py-4">
                Impossible de charger tes ressources vendables.
              </td>
            </tr>
          `;
          return;
        }

        const data = res.data || {};
        const resources = data.resources || [];

        if (!resources.length) {
          tbody.innerHTML = `
            <tr>
              <td colspan="5" class="text-center text-muted py-4">
                Tu n'as aucune ressource vendable pour l'instant.
              </td>
            </tr>
          `;
          return;
        }

        // Render rows
        tbody.innerHTML = resources
          .map((r) => {
            const displayQty = Number(r.qty)
              .toFixed(2)
              .replace(/\.00$/, "");
            const displayPrice = Number(r.unit_sell_price)
              .toFixed(2)
              .replace(/\.00$/, "");

            const label = r.label || r.resource;

            return `
              <tr data-res="${r.resource}">
                <td>
                  <div class="d-flex align-items-center gap-2">
                    <img
                      src="${resourceIconPath(r.resource)}"
                      alt="${label}"
                      class="resource-icon-sm"
                    />
                    <span class="resource-label">
                      ${r.emoji ? `${r.emoji} ` : ""}${label}
                    </span>
                  </div>
                </td>

                <td class="text-end">
                  <span class="market-stock" data-field="stock">
                    ${displayQty}
                  </span>
                </td>

                <td class="text-end">
                  <span class="market-price">
                    ${displayPrice} 🪙
                  </span>
                </td>

                <td class="text-end">
                  <input
                    type="number"
                    class="form-control form-control-sm market-qty-input"
                    min="1"
                    max="${r.qty}"
                    value="1"
                  />
                </td>

                <td class="text-end">
                  <button
                    type="button"
                    class="btn btn-sm btn-success market-sell-btn"
                  >
                    Vendre
                  </button>
                </td>
              </tr>
            `;
          })
          .join("");

        bindSellButtons();
      })
      .catch((err) => {
        console.error("[village_market] error loading resources", err);
        tbody.innerHTML = `
          <tr>
            <td colspan="5" class="text-center text-danger py-4">
              Erreur inattendue lors du chargement du marché.
            </td>
          </tr>
        `;
      });
  }

  // ----------------------------------------------------------
  // Bind sell buttons
  // ----------------------------------------------------------

  function bindSellButtons() {
    const rows = tbody.querySelectorAll("tr[data-res]");

    rows.forEach((tr) => {
      const key = tr.getAttribute("data-res");
      const btn = tr.querySelector(".market-sell-btn");
      const input = tr.querySelector(".market-qty-input");
      const stockSpan = tr.querySelector(".market-stock");

      if (!btn || !input || !stockSpan || !key) return;

      btn.addEventListener("click", async () => {
        const rawValue = input.value;
        let qty = parseInt(rawValue, 10);

        if (isNaN(qty) || qty <= 0) {
          showMessage("error", "Quantité invalide.");
          return;
        }

        const currentStock = parseFloat(
          stockSpan.textContent.replace(",", ".")
        );
        if (qty > currentStock) {
          showMessage("error", "Tu n'as pas autant de stock.");
          return;
        }

        btn.disabled = true;
        const oldLabel = btn.textContent;
        btn.textContent = "Vente...";

        try {
          const r = await http("POST", "/api/sell", {
            resource: key,
            qty: qty,
          });

          if (!r.ok) {
            const err = r.data || {};
            console.error("[village_market] sell error", err);
            const msg =
              err.error === "not_enough_stock"
                ? "Tu n'as pas assez de stock."
                : "Vente impossible : " +
                  (err.error || `Erreur serveur (${r.status})`);
            showMessage("error", msg);
            btn.disabled = false;
            btn.textContent = oldLabel;
            return;
          }

          const d = r.data || {};
          const sold = d.sold || {};

          // Update HUD via VillageCommon helper (XP, shards, essence, etc.)
          if (
            window.VillageCommon &&
            typeof VillageCommon.handlePlayerAndLevelFromResponse ===
              "function"
          ) {
            VillageCommon.handlePlayerAndLevelFromResponse(d);
          }

          // Update stock in table
          const newQty =
            d.stock && typeof d.stock.qty === "number"
              ? d.stock.qty
              : currentStock - qty;

          const displayNewQty = Number(newQty)
            .toFixed(2)
            .replace(/\.00$/, "");
          stockSpan.textContent = displayNewQty;

          if (newQty <= 0) {
            input.disabled = true;
            btn.disabled = true;
            btn.textContent = "Épuisé";
          } else {
            input.max = newQty;
            if (qty > newQty) {
              input.value = newQty;
            }
            btn.disabled = false;
            btn.textContent = oldLabel;
          }

          showMessage(
            "success",
            `Vente réussie : +${sold.gain || qty * (sold.unit_price || 0)} shards pour ${sold.qty || qty} × ${sold.resource || key}.`
          );
        } catch (e) {
          console.error("[village_market] network error", e);
          showMessage(
            "error",
            "Erreur réseau pendant la vente. Réessaie plus tard."
          );
          btn.disabled = false;
          btn.textContent = oldLabel;
        }
      });
    });
  }

  // Kickstart
  loadMarketResources();
});
