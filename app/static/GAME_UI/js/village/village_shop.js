// static/GAME_UI/js/village_shop.js
// Handle purchases in the village shop.

document.addEventListener("DOMContentLoaded", () => {
  const buttons = document.querySelectorAll(".vs-buy-btn");
  if (!buttons.length) return;

  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const offerKey = btn.getAttribute("data-offer-key");
      if (!offerKey) return;

      btn.disabled = true;
      btn.textContent = "Achat...";

      try {
        const res = await fetch("/api/village/shop/buy", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ offer_key: offerKey }),
        });

        const data = await res.json();

        if (!data.ok) {
          const err = data.error || "unknown_error";
          alert("Achat impossible: " + err);
        } else {
          alert(
            `Achat réussi: ${data.card.label}\nTu en possèdes maintenant ${data.owned_qty}.`
          );

          // TODO: update HUD (coins/diams) si tu as des IDs pour ça
        }
      } catch (e) {
        console.error(e);
        alert("Erreur réseau pendant l'achat.");
      } finally {
        btn.disabled = false;
        btn.textContent = "Acheter";
      }
    });
  });
});
