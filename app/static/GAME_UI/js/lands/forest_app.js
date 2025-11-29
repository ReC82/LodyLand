  // static/GAME_UI/js/lands/forest_app.js
  // Handle UI + collect logic for the Forest land page.

  function baseUrl() {
    return `${location.protocol}//${location.host}`;
  }

  // ---------------------------------------------------------------------------
  // Simple cooldown manager for Forest slots (per slot timer)
  // ---------------------------------------------------------------------------

  let forestCooldownInterval = null;

  /**
   * Ensure we have a running interval that updates cooldown labels.
   */
  function ensureForestCooldownTicker() {
    if (forestCooldownInterval) return;
    forestCooldownInterval = setInterval(updateForestCooldownUI, 1000);
  }

  /**
   * Attach a cooldown to a given forest slot element.
   * @param {HTMLElement} slotEl - Slot tile element.
   * @param {string} iso - ISO datetime string (cooldown end).
   */
  function setForestSlotCooldown(slotEl, iso) {
    if (!slotEl || !iso) return;

    slotEl.dataset.cooldownUntil = iso;
    ensureForestCooldownTicker();

    const statusEl = slotEl.querySelector(".slot-status");
    if (!statusEl) return;

    const msEnd = new Date(iso).getTime();
    const diffSec = Math.ceil((msEnd - Date.now()) / 1000);

    if (diffSec > 0) {
      statusEl.textContent = `Cooldown : ${diffSec}s`;
    } else {
      statusEl.textContent = "Prêt à fouiller.";
    }
  }

  /**
   * Tick function called every second to refresh cooldown text.
   */
  function updateForestCooldownUI() {
    const slots = document.querySelectorAll(".slot-tile:not(.slot-add)");
    let hasCooldown = false;

    const now = Date.now();

    slots.forEach((slot) => {
      const iso = slot.dataset.cooldownUntil;
      const statusEl = slot.querySelector(".slot-status");
      if (!iso || !statusEl) return;

      const msEnd = new Date(iso).getTime();
      const diffSec = Math.ceil((msEnd - now) / 1000);

      if (diffSec > 0) {
        hasCooldown = true;
        statusEl.textContent = `Cooldown : ${diffSec}s`;
        slot.classList.add("slot-on-cooldown");
      } else {
        statusEl.textContent = "Prêt à fouiller.";
        slot.classList.remove("slot-on-cooldown");
        delete slot.dataset.cooldownUntil;
      }
    });

    // Stop interval if there is no active cooldown
    if (!hasCooldown && forestCooldownInterval) {
      clearInterval(forestCooldownInterval);
      forestCooldownInterval = null;
    }
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
        } else if (data.error === "on_cooldown" && data.until) {
          // Slot is on cooldown server-side -> sync cooldown with UI
          setForestSlotCooldown(slotEl, data.until);
          const msEnd = new Date(data.until).getTime();
          const diffSec = Math.ceil((msEnd - Date.now()) / 1000);
          msg =
            diffSec > 0
              ? `Slot en cooldown (${diffSec}s restants).`
              : "Slot presque prêt...";
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

      // Toasts de loot (icône + quantité au format "+ 1.6")
      if (Array.isArray(data.loot) && data.loot.length > 0 && window.showLootToasts) {
        window.showLootToasts(data.loot);
      }

      // 🔥 UPDATE HUD
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

      // 🕒 Visual cooldown for this slot
      if (data.next) {
        setForestSlotCooldown(slotEl, data.next);
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
   * Init click handlers on all forest slots (except the + tile).
   */
  function initForestCollect() {
    // On exclut la tuile "add slot"
    const tiles = document.querySelectorAll(".slot-tile:not(.slot-add)");
    tiles.forEach((tile) => {
      tile.addEventListener("click", () => collectOnForestSlot(tile));
    });
    console.log("[Forest] Land initialized with", tiles.length, "slots");
  }

  /**
   * Init "add slot" button logic.
   */
  function initForestAddSlot() {
    const addBtn = document.getElementById("add-slot-btn");
    if (!addBtn) return;

    addBtn.addEventListener("click", async (evt) => {
      evt.stopPropagation(); // évite tout clic parasite

      const hasFree = addBtn.dataset.hasFree === "1";
      const nextCost = Number(addBtn.dataset.nextCost || "0");

      let message;
      if (hasFree) {
        message =
          "Utiliser une carte 'Forest Free Slot' pour débloquer un emplacement ?\n" +
          "(Cela ne coûtera pas de diams.)";
      } else {
        message = `Confirmer l'achat d'un emplacement Forêt pour ${nextCost} 💎 ?`;
      }

      if (!confirm(message)) return;

      try {
        const r = await fetch(baseUrl() + "/api/lands/forest/slots/buy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({}),
        });

        const data = await r.json();

        if (!r.ok || !data.ok) {
          console.warn("Buy slot error:", data);
          alert(data.error || "Erreur lors de l'ajout du slot.");
          return;
        }

        // Mettre à jour le HUD (diams)
        if (data.player && window.renderPlayer) {
          renderPlayer(data.player);
        }

        // Petit message informatif (optionnel)
        if (data.used_free_card) {
          alert("Carte 'Forest Free Slot' utilisée. Nouvel emplacement débloqué !");
        } else {
          alert("Emplacement Forêt acheté avec des diams !");
        }

        // Recharger pour afficher le nouveau nombre de slots + nouvel état du bouton
        location.reload();
      } catch (err) {
        console.error("Buy slot request failed:", err);
        alert("Erreur réseau lors de l'achat du slot.");
      }
    });
  }

  // Wait for DOM ready
  document.addEventListener("DOMContentLoaded", () => {
    initForestCollect();
    initForestAddSlot();
  });
