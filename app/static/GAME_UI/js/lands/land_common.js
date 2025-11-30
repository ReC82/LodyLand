// static/GAME_UI/js/lands/land_common.js
// Common logic for all lands (forest, beach, lake, ...)

(function (window) {
  "use strict";

  // ---------------------------------------------------------------------------
  // Base helpers
  // ---------------------------------------------------------------------------

  function baseUrl() {
    return `${location.protocol}//${location.host}`;
  }

  // Expose globally (add-slot, etc. peuvent en avoir besoin)
  window.baseUrl = baseUrl;

  // ---------------------------------------------------------------------------
  // LandTools: tool selector + availability from /api/state
  // ---------------------------------------------------------------------------

  const LandTools = (function () {
    let currentTool = "hands";
    let buttonsCache = null;

    function lockToolButton(btn) {
      if (!btn) return;

      const toolKey = btn.getAttribute("data-tool") || "hands";

      // "hands" must always be visible
      if (toolKey === "hands") {
        btn.classList.remove("tool-locked");
        btn.disabled = false;
        btn.removeAttribute("title");
        btn.style.display = "flex";
        return;
      }

      btn.classList.add("tool-locked");
      btn.disabled = true;
      btn.setAttribute("title", "Tu dois d'abord crafter cet outil.");
      btn.style.display = "none"; // hide from dropdown
    }

    function unlockToolButton(btn) {
      if (!btn) return;
      btn.classList.remove("tool-locked");
      btn.disabled = false;
      btn.removeAttribute("title");
      btn.style.display = "flex"; // show in dropdown
    }



    /**
     * Enable/disable tools based on player's crafted items.
     * items = data.items from /api/state
     * -> On utilise aussi items.icon (depuis items.yml) pour afficher les icônes.
     */
    function applyAvailability(items) {
      const list = Array.isArray(items) ? items : [];

      // Map rapide item_key -> meta (avec icon, qty, labels, ...)
      const metaByKey = new Map();
      list.forEach((it) => {
        if (!it || !it.item_key) return;
        metaByKey.set(it.item_key, it);
      });

      const hasItem = (key) => {
        const meta = metaByKey.get(key);
        return !!meta && (meta.qty || 0) > 0;
      };

      const buttons = document.querySelectorAll(".land-tool-btn");
      buttonsCache = buttons;

      buttons.forEach((btn) => {
        const toolKey = btn.getAttribute("data-tool") || "hands";

        // Priority: explicit requires_item in HTML
        const explicitRequired = btn.dataset.requiresItem || null;
        const itemKeyAttr = btn.dataset.itemKey || null;
        let requiredItemKey = explicitRequired || itemKeyAttr;

        // Fallback convention:
        //  - pas de requires_item explicite
        //  - toolKey != "hands"
        //  - toolKey commence par "tool_"
        //  => requiredItemKey = toolKey
        if (!requiredItemKey && toolKey !== "hands" && toolKey.startsWith("tool_")) {
          requiredItemKey = toolKey;
        }

        // Mains (ou outil sans requirement) = toujours dispo
        if (!requiredItemKey || toolKey === "hands") {
          // Icône des mains normalement déjà câblée dans le HTML
          unlockToolButton(btn);
          return;
        }

        // Si on a des meta pour cet item_key → on pousse l'icône dans le bouton
        const meta = metaByKey.get(requiredItemKey);
        if (meta && meta.icon) {
          const label =
            meta.label_fr ||
            meta.label_en ||
            btn.getAttribute("data-label") ||
            toolKey;
          applyIconToButton(btn, meta.icon, label);
        }

        // Lock / unlock suivant présence dans l'inventaire
        if (hasItem(requiredItemKey)) {
          unlockToolButton(btn);
        } else {
          lockToolButton(btn);
        }
      });
    }


    /**
     * Load /api/state once and apply tool availability.
     */
    async function loadAvailability() {
      try {
        const res = await fetch(baseUrl() + "/api/state", {
          method: "GET",
          credentials: "same-origin",
        });

        const data = await res.json();
        if (!res.ok || data.error) {
          console.warn("[LandTools] /api/state error for tools:", data);
          return;
        }

        applyAvailability(data.items || []);
      } catch (err) {
        console.error("[LandTools] Failed to load tool availability:", err);
      }
    }

    /**
     * Init tool selector:
     *  - defaultTool: "hands" par défaut
     *  - ignore les boutons verrouillés
     */
    function initToolSelector(defaultTool = "hands") {
      const buttons = document.querySelectorAll(".land-tool-btn");
      if (!buttons.length) return;

      buttonsCache = buttons;

      // Default: on met defaultTool actif, le reste est lock jusqu'à /api/state
      buttons.forEach((btn) => {
        const toolKey = btn.getAttribute("data-tool") || "hands";
        if (toolKey === defaultTool) {
          currentTool = toolKey;
          btn.classList.add("active");
        } else {
          lockToolButton(btn);
        }
      });

      // Click handler
      buttons.forEach((btn) => {
        btn.addEventListener("click", () => {
          // Ignorer les outils verrouillés
          if (btn.disabled || btn.classList.contains("tool-locked")) {
            return;
          }

          const toolKey = btn.getAttribute("data-tool") || "hands";
          currentTool = toolKey;

          buttons.forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");

          console.log("[LandTools] Tool selected:", currentTool);
        });
      });
    }

    function resetToHands() {
      const buttons = buttonsCache || document.querySelectorAll(".land-tool-btn");
      if (!buttons.length) return;

      currentTool = "hands";
      buttons.forEach((btn) => {
        const toolKey = btn.getAttribute("data-tool") || "hands";
        if (toolKey === "hands") {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      });
    }

    function getCurrentTool() {
      return currentTool || "hands";
    }

    // public API
    return {
      initToolSelector,
      loadAvailability,
      applyAvailability,
      getCurrentTool,
      lockToolButton,
      unlockToolButton,
      resetToHands,
    };
  })();

  window.LandTools = LandTools;

  // ---------------------------------------------------------------------------
  // LandCooldown: per-slot cooldown + optional green bar
  // ---------------------------------------------------------------------------

  const LandCooldown = (function () {
    let intervalId = null;

    function ensureTicker() {
      if (intervalId) return;
      intervalId = setInterval(tick, 1000);
    }

    /**
     * Update a single slot according to data-* attributes.
     * Returns true if still on cooldown, false otherwise.
     */
    function updateOneSlot(slot) {
      const iso = slot.dataset.cooldownUntil;
      if (!iso) return false;

      const durationSec = Number(slot.dataset.cooldownDuration || "0");
      const statusEl = slot.querySelector(".slot-status");
      const barFill = slot.querySelector(".slot-cooldown-fill");

      const now = Date.now();
      const msEnd = new Date(iso).getTime();
      const diffSec = Math.ceil((msEnd - now) / 1000);

      // Text
      if (statusEl) {
        if (diffSec > 0) {
          statusEl.textContent = `Cooldown : ${diffSec}s`;
        } else {
          statusEl.textContent = "Prêt à fouiller.";
        }
      }

      // Green bar si on connait la durée
      if (durationSec > 0 && barFill) {
        const durationMs = durationSec * 1000;
        const remainingMs = Math.max(0, msEnd - now);
        const frac = Math.max(0, Math.min(1, remainingMs / durationMs));
        barFill.style.transform = `scaleX(${frac})`;
      }

      if (diffSec > 0) {
        slot.classList.add("slot-on-cooldown");
        return true;
      } else {
        slot.classList.remove("slot-on-cooldown");
        delete slot.dataset.cooldownUntil;
        delete slot.dataset.cooldownDuration;
        if (barFill) {
          barFill.style.transform = "scaleX(0)";
        }
        return false;
      }
    }

    function tick() {
      const slots = document.querySelectorAll(".slot-tile:not(.slot-add)");
      let any = false;

      slots.forEach((slot) => {
        if (slot.dataset.cooldownUntil) {
          if (updateOneSlot(slot)) {
            any = true;
          }
        }
      });

      if (!any && intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    }

    /**
     * Attach a cooldown to a given slot.
     * durationSec is optional (if absent, no bar, just text).
     */
    function setSlotCooldown(slotEl, iso, durationSec) {
      if (!slotEl || !iso) return;

      slotEl.dataset.cooldownUntil = iso;
      if (durationSec && durationSec > 0) {
        slotEl.dataset.cooldownDuration = String(durationSec);
      }

      ensureTicker();
      updateOneSlot(slotEl);
    }

    /**
     * Rebuild cooldowns at page load from data-* attributes.
     */
    function initFromDataset() {
      const slots = document.querySelectorAll(".slot-tile:not(.slot-add)");
      let found = false;

      slots.forEach((slot) => {
        const iso = slot.dataset.cooldownUntil;
        const durationSec = Number(slot.dataset.cooldownDuration || "0");
        if (iso) {
          setSlotCooldown(slot, iso, durationSec);
          found = true;
        }
      });

      if (found) ensureTicker();
    }

    return {
      setSlotCooldown,
      initFromDataset,
    };
  })();

  window.LandCooldown = LandCooldown;

  // ---------------------------------------------------------------------------
  // LandCollect: generic /api/collect logic for all lands
  // ---------------------------------------------------------------------------

  const LandCollect = (function () {
    async function collectOnSlot(slotEl) {
      const land = window.CURRENT_LAND || slotEl.dataset.land || null;
      const statusEl = slotEl.querySelector(".slot-status");
      const slotIndex = Number(slotEl.getAttribute("data-slot"));

      if (!land) {
        console.warn("[LandCollect] Missing CURRENT_LAND.");
        if (statusEl) statusEl.textContent = "Erreur : land inconnu";
        return;
      }

      if (Number.isNaN(slotIndex)) {
        console.warn("[LandCollect] Invalid slot index:", slotEl);
        if (statusEl) statusEl.textContent = "Erreur : slot invalide";
        return;
      }

      if (statusEl) {
        statusEl.textContent = "Fouille en cours...";
      }

      try {
        const payload = {
          land,
          slot: slotIndex,
        };

        // possibilité de désactiver les outils pour certains lands
        if (window.LAND_DISABLE_TOOLS !== true) {
          payload.tool = LandTools.getCurrentTool();
        }

        const response = await fetch(baseUrl() + "/api/collect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify(payload),
        });

        const data = await response.json();

        if (!response.ok || !data.ok) {
          console.warn("[LandCollect] collect error:", data);

          let msg = "Erreur de collecte";

          if (data.error === "land_locked") {
            msg = "Tu n'as pas la carte pour accéder à ce land.";
          } else if (data.error === "player_required") {
            msg = "Tu dois être connecté(e) pour fouiller ce land.";
          } else if (data.error === "on_cooldown" && data.until) {
            const duration = Number(data.cooldown_duration || 0);
            if (duration > 0) {
              LandCooldown.setSlotCooldown(slotEl, data.until, duration);
            }

            const msEnd = new Date(data.until).getTime();
            const diffSec = Math.ceil((msEnd - Date.now()) / 1000);
            msg =
              diffSec > 0
                ? `Slot en cooldown (${diffSec}s restants).`
                : "Slot presque prêt...";
          } else if (data.error === "tool_requires_item") {
            msg =
              "Tu n'as pas encore l'objet nécessaire pour utiliser cet outil.";
            LandTools.resetToHands();
          } else if (data.error) {
            msg = `Erreur: ${data.error}`;
          }

          if (statusEl) statusEl.textContent = msg;
          return;
        }

        // Loot summary
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

        // Toasts
        if (
          Array.isArray(data.loot) &&
          data.loot.length > 0 &&
          window.showLootToasts
        ) {
          window.showLootToasts(data.loot);
        }

        // HUD
        if (data.player && window.renderPlayer) {
          window.renderPlayer({
            ...data.player,
            next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
          });
        }

        // Level up
        if (data.level_up && window.showLevelUpModal) {
          const lvl = data.player?.level ?? 0;
          const rewards = data.level_rewards || [];
          window.showLevelUpModal(lvl, rewards);
        }

        // Cooldown visuel
        if (data.next) {
          const duration = Number(data.cooldown_duration || 0);
          LandCooldown.setSlotCooldown(slotEl, data.next, duration);
        }

        console.log("[LandCollect] OK:", land, "slot", slotIndex, data);
      } catch (err) {
        console.error("[LandCollect] request failed:", err);
        if (statusEl) {
          statusEl.textContent = "Erreur réseau";
        }
      }
    }

    function initCollect() {
      const tiles = document.querySelectorAll(".slot-tile:not(.slot-add)");
      tiles.forEach((tile) => {
        tile.addEventListener("click", () => collectOnSlot(tile));
      });
      console.log(
        "[LandCollect] initialized for land=",
        window.CURRENT_LAND,
        "slots=",
        tiles.length
      );
    }

    return {
      initCollect,
      collectOnSlot,
    };
  })();

  window.LandCollect = LandCollect;

  // ---------------------------------------------------------------------------
  // LandSlots: generic "+1 slot" logic
  // ---------------------------------------------------------------------------

  const LandSlots = (function () {
    function initAddSlot() {
      const addBtn = document.getElementById("add-slot-btn");
      if (!addBtn) return;

      const landKey = window.CURRENT_LAND || addBtn.dataset.land || null;
      if (!landKey) return;

      const landLabel =
        window.LAND_LABEL || addBtn.dataset.landLabel || landKey || "ce land";

      addBtn.addEventListener("click", async (evt) => {
        evt.stopPropagation();

        const hasFree = addBtn.dataset.hasFree === "1";
        const nextCost = Number(addBtn.dataset.nextCost || "0");

        let message;
        if (hasFree) {
          message =
            `Utiliser une carte emplacement gratuit pour débloquer un emplacement sur ${landLabel} ?\n` +
            "(Cela ne coûtera pas de diams.)";
        } else {
          message = `Confirmer l'achat d'un emplacement ${landLabel} pour ${nextCost} 💎 ?`;
        }

        if (!confirm(message)) return;

        try {
          const r = await fetch(
            baseUrl() + `/api/lands/${landKey}/slots/buy`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              credentials: "same-origin",
              body: JSON.stringify({}),
            }
          );

          const data = await r.json();

          if (!r.ok || !data.ok) {
            console.warn("[LandSlots] Buy slot error:", data);
            alert(data.error || "Erreur lors de l'ajout du slot.");
            return;
          }

          if (data.player && window.renderPlayer) {
            window.renderPlayer(data.player);
          }

          if (data.used_free_card) {
            alert(
              `Carte emplacement gratuit utilisée. Nouvel emplacement débloqué sur ${landLabel} !`
            );
          } else {
            alert(`Emplacement ${landLabel} acheté avec des diams !`);
          }

          location.reload();
        } catch (err) {
          console.error("[LandSlots] Buy slot request failed:", err);
          alert("Erreur réseau lors de l'achat du slot.");
        }
      });
    }

    return {
      initAddSlot,
    };
  })();

  window.LandSlots = LandSlots;

    // Normalize icon path from YAML to a usable URL
    function normalizeIconPath(iconPath) {
      if (!iconPath) return null;

      // Absolute URL (CDN, etc.)
      if (iconPath.startsWith("http://") || iconPath.startsWith("https://")) {
        return iconPath;
      }

      // Déjà en chemin absolu (/static/...)
      if (iconPath.startsWith("/")) {
        return iconPath;
      }

      // On enlève un éventuel "static/" au début, on préfixe par /static/
      const cleaned = iconPath.replace(/^\/?static\//, "");
      return "/static/" + cleaned;
    }

    // Apply icon + alt to a given tool button (if present)
    function applyIconToButton(btn, iconPath, label) {
      if (!btn) return;
      const url = normalizeIconPath(iconPath);
      if (!url) return;

      btn.dataset.icon = url;

      const img = btn.querySelector(".land-tool-icon");
      if (img) {
        img.src = url;
        if (label) {
          img.alt = label;
        }
      }
    }


  // ---------------------------------------------------------------------------
  // DOM Ready: wiring commun à tous les lands
  // ---------------------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", () => {
    // On ne fait rien si ce n'est pas une page de land
    if (!window.CURRENT_LAND) return;

    // Outil par défaut = mains
    LandTools.initToolSelector("hands");
    LandTools.loadAvailability();

    // Restaure les cooldowns (barre verte) depuis data-*
    LandCooldown.initFromDataset();

    // Clique sur les slots = collecte générique
    LandCollect.initCollect();

    // Achat de slots générique
    LandSlots.initAddSlot();
  });
})(window);
