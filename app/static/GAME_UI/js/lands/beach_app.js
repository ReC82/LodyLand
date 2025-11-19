// static/GAME_UI/js/lands/beach_app.js
// Handle UI + collect logic for the Beach land page.

/**
 * Build base URL (protocol + host).
 */
function baseUrl() {
  return `${location.protocol}//${location.host}`;
}

/**
 * Call /api/collect in "land" mode for the Beach.
 * @param {HTMLElement} slotEl - The clicked slot tile element.
 */
async function collectOnBeachSlot(slotEl) {
  const slotIndex = Number(slotEl.getAttribute("data-slot"));
  const statusEl = slotEl.querySelector(".slot-status");

  if (Number.isNaN(slotIndex)) {
    console.warn("Invalid slot index on beach tile:", slotEl);
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
        land: "beach",
        slot: slotIndex,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      console.warn("Beach collect error:", data);

      let msg = "Erreur de collecte";
      if (data.error === "land_locked") {
        msg = "Tu n'as pas la carte 'Accès Plage'.";
      } else if (data.error === "player_required") {
        msg = "Tu dois être connecté(e) pour fouiller la plage.";
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

        // 🔥 Mise à jour HUD
    if (data.player) {
      renderPlayer({
        ...data.player,
        next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
      });
    }

    // 🌟 Level-up modal
    if (data.level_up) {
      const lvl = data.player?.level ?? 0;
      const rewards = data.level_rewards || [];
      showLevelUpModal(lvl, rewards);
    }

    console.log("Beach collect OK:", data);
  } catch (err) {
    console.error("Beach collect request failed:", err);
    if (statusEl) {
      statusEl.textContent = "Erreur réseau";
    }
  }
}

/**
 * Init click handlers on all beach slots.
 */
function initBeachLand() {
  const tiles = document.querySelectorAll(".slot-tile");
  tiles.forEach((tile) => {
    tile.addEventListener("click", () => collectOnBeachSlot(tile));
  });
  console.log("[Beach] Land initialized with", tiles.length, "slots");
}

// Wait for DOM ready
document.addEventListener("DOMContentLoaded", initBeachLand);
