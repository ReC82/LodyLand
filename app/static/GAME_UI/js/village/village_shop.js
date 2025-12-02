// static/GAME_UI/js/village/village_shop.js
// ============================================================
// VILLAGE SHOP — Buy items/cards from the village offers
// ============================================================

/* global $, http */

document.addEventListener("DOMContentLoaded", () => {
  console.log("[village_shop] init");

  const buttons = document.querySelectorAll(".vs-buy-btn");
  if (!buttons.length) return;

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => handleBuy(btn));
  });

  async function handleBuy(btn) {
    const offerKey = btn.dataset.offerKey;
    if (!offerKey) {
      console.warn("Missing offerKey");
      return;
    }

    btn.disabled = true;
    const oldLabel = btn.textContent;
    btn.textContent = "Achat...";

    try {
      const r = await http("POST", "/village/shop/buy", { offer_key: offerKey });

      if (!r.ok) {
        const err = r.data || {};
        console.error("[village_shop] error:", err);

        btn.disabled = false;
        btn.textContent = oldLabel;

        alert("Achat impossible : " + (err.error || "Erreur inconnue"));
        return;
      }

      const data = r.data;

      // Mise à jour HUD (XP, coins, diams)
      if (window.VillageCommon && typeof VillageCommon.handlePlayerAndLevelFromResponse === "function") {
        VillageCommon.handlePlayerAndLevelFromResponse(data);
      }

      // Visuel : le bouton devient "Acheté"
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
});
