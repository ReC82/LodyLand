// ============================================================
// VILLAGE SHOP — Client-side Purchase Handler
// ------------------------------------------------------------
// This script attaches click events to all enabled "Acheter" 
// buttons (class .vs-buy-btn) in the village shop UI.
//
// The logic is intentionally simple:
//   1. Detect click on a buy button
//   2. Lock button (loading state)
//   3. Send POST request to /api/village/shop/buy
//   4. Display response (success or error)
//   5. Restore button state
//
// NOTE:
// Disabled items (btn.disabled=true in the template) DO NOT 
// receive click events — no need for extra checks here.
// ============================================================

document.addEventListener("DOMContentLoaded", () => {

  // ------------------------------------------------------------
  // Select all active buy buttons (the template only assigns 
  // .vs-buy-btn to buyable items)
  // ------------------------------------------------------------
  const buttons = document.querySelectorAll(".vs-buy-btn");
  if (!buttons.length) return; // No items buyable on this page

  // ------------------------------------------------------------
  // Iterate over each buy button and attach a click handler
  // ------------------------------------------------------------
  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {

      // Offer key uniquely identifies the village offer
      const offerKey = btn.getAttribute("data-offer-key");
      if (!offerKey) return; // Safety check

      // --------------------------------------------------------
      // Enter "loading" state
      // --------------------------------------------------------
      btn.disabled = true;
      btn.textContent = "Achat...";

      try {
        // ------------------------------------------------------
        // Send purchase request to backend
        // ------------------------------------------------------
        const res = await fetch("/api/village/shop/buy", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ offer_key: offerKey }),
        });

        // Server always returns JSON (success or error)
        const data = await res.json();

        // ------------------------------------------------------
        // Handle errors (logic errors, purchase rules, limits…)
        // ------------------------------------------------------
        if (!data.ok) {
          const err = data.error || "unknown_error";
          alert("Achat impossible: " + err);
        }

        // ------------------------------------------------------
        // Handle successful purchase
        // ------------------------------------------------------
        else {
          alert(
            `Achat réussi: ${data.card.label}\n` +
            `Tu en possèdes maintenant ${data.owned_qty}.`
          );

          // TODO (optional):
          // Update HUD coins/diams on the frontend 
          // if HUD DOM IDs are available.
        }

      } catch (e) {
        // ------------------------------------------------------
        // Handle network errors (backend unreachable, etc.)
        // ------------------------------------------------------
        console.error(e);
        alert("Erreur réseau pendant l'achat.");

      } finally {
        // ------------------------------------------------------
        // Restore button state
        // (Even after failure the button is re-enabled so the 
        // user may retry.)
        // ------------------------------------------------------
        btn.disabled = false;
        btn.textContent = "Acheter";
      }

    });
  });
});
