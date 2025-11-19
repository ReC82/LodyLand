// static/GAME_UI/js/lands/beach_app.js
// Handle UI + collect logic for the Beach land page.

function baseUrl() {
  return `${location.protocol}//${location.host}`;
}

/**
 * Appelle /api/collect en mode "land" pour la Plage.
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
      credentials: "same-origin",
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
      if (statusEl) statusEl.textContent = msg;
      return;
    }

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

    // Toasts de loot (icône + quantité au format "+ 1.6")
    if (Array.isArray(data.loot) && data.loot.length > 0 && window.showLootToasts) {
      window.showLootToasts(data.loot);
    }

    if (data.player && window.renderPlayer) {
      renderPlayer({
        ...data.player,
        next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
      });
    }

    if (data.level_up) {
      const lvl = data.player?.level ?? 0;
      const rewards = data.level_rewards || [];
      showLevelUpModal(lvl, rewards);
    }

  } catch (err) {
    console.error("Beach collect request failed:", err);
    if (statusEl) {
      statusEl.textContent = "Erreur réseau";
    }
  }
}

function initBeachCollect() {
  const tiles = document.querySelectorAll(".slot-tile:not(.slot-add)");
  tiles.forEach((tile) => {
    tile.addEventListener("click", () => collectOnBeachSlot(tile));
  });
  console.log("[Beach] Land initialized with", tiles.length, "slots");
}

function initBeachAddSlot() {
  const addBtn = document.getElementById("add-slot-btn");
  if (!addBtn) return;

  addBtn.addEventListener("click", async (evt) => {
    evt.stopPropagation();

    const hasFree = addBtn.dataset.hasFree === "1";
    const nextCost = Number(addBtn.dataset.nextCost || "0");

    let message;
    if (hasFree) {
      message =
        "Utiliser une carte 'Beach Free Slot' pour débloquer un emplacement ?\n" +
        "(Cela ne coûtera pas de diams.)";
    } else {
      message = `Confirmer l'achat d'un emplacement Plage pour ${nextCost} 💎 ?`;
    }

    if (!confirm(message)) return;

    try {
      const r = await fetch(baseUrl() + "/api/lands/beach/slots/buy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({}),
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        console.warn("Buy beach slot error:", data);
        alert(data.error || "Erreur lors de l'ajout du slot.");
        return;
      }

      if (data.player && window.renderPlayer) {
        renderPlayer(data.player);
      }

      if (data.used_free_card) {
        alert("Carte 'Beach Free Slot' utilisée. Nouvel emplacement débloqué !");
      } else {
        alert("Emplacement Plage acheté avec des diams !");
      }

      location.reload();
    } catch (err) {
      console.error("Buy beach slot request failed:", err);
      alert("Erreur réseau lors de l'achat du slot.");
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initBeachCollect();
  initBeachAddSlot();
});
