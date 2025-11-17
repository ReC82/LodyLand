// static/GAME_UI/js/lands/forest_app.js
// Handle UI + collect logic for the Forest land page.

/**
 * Build base URL (protocol + host).
 */
function baseUrl() {
  return `${location.protocol}//${location.host}`;
}

/**
 * Call /api/collect in "land" mode for the Forest.
 * @param {HTMLElement} slotEl - The clicked slot tile element.
 */
async function collectOnForestSlot(slotEl) {
  const slotIndex = Number(slotEl.getAttribute("data-slot"));
  const statusEl = slotEl.querySelector(".slot-status");

  if (Number.isNaN(slotIndex)) {
    console.warn("Invalid slot index on forest tile:", slotEl);
    if (statusEl) {
      statusEl.textContent = "Erreur : slot invalide";
    }
    return;
  }

  if (statusEl) {
    statusEl.textContent = "Fouille en cours...";
  }

  try {
    const response = await fetch(baseUrl() + "/api/collect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin", // needed for player_id cookie
      body: JSON.stringify({
        land: "forest",
        slot: slotIndex,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      console.warn("Forest collect error:", data);

      let msg = "Erreur de collecte";
      if (data.error === "land_locked") {
        msg = "Tu n'as pas la carte 'Accès Forêt'.";
      } else if (data.error === "player_required") {
        msg = "Tu dois être connecté(e) pour fouiller la forêt.";
      } else if (data.error) {
        msg = `Erreur: ${data.error}`;
      }

      if (statusEl) {
        statusEl.textContent = msg;
      }
      return;
    }

    // Build loot summary
    let summary = "Rien trouvé...";
    if (Array.isArray(data.loot) && data.loot.length > 0) {
      summary = data.loot
        .map((entry) => {
          const amount =
            typeof entry.final_amount === "number"
              ? entry.final_amount
              : entry.base_amount;
          return `${amount}x ${entry.resource}`;
        })
        .join(", ");
    }

    if (statusEl) {
      statusEl.textContent = `Tu as trouvé : ${summary}`;
    }

    console.log("Forest collect OK:", data);
  } catch (err) {
    console.error("Forest collect request failed:", err);
    if (statusEl) {
      statusEl.textContent = "Erreur réseau";
    }
  }
}

/**
 * Init click handlers on all forest slots.
 */
function initForestLand() {
  const tiles = document.querySelectorAll(".slot-tile");
  tiles.forEach((tile) => {
    tile.addEventListener("click", () => collectOnForestSlot(tile));
  });
  console.log("[Forest] Land initialized with", tiles.length, "slots");
}

// Wait for DOM ready
document.addEventListener("DOMContentLoaded", initForestLand);
