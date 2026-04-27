// static/GAME_UI/js/lands/land_common.js
// Common logic for all lands (forest, beach, lake, ...)

(function (window) {
  "use strict";

  // ==========================================================================
  // Base helpers
  // ==========================================================================

  /**
   * Build base URL for API calls.
   * Example: https://example.com
   */
  function baseUrl() {
    return `${location.protocol}//${location.host}`;
  }

  // Expose globally (add-slot, etc. may need it)
  window.baseUrl = baseUrl;

  // ==========================================================================
  // Icon helpers (used by LandTools)
  // ==========================================================================

  /**
   * Normalize icon path from YAML (items.yml) into a usable browser URL.
   *
   * Supports:
   *  - Absolute URLs (http/https)
   *  - Already absolute paths starting with "/"
   *  - Relative paths with / without "static/" prefix
   */
  function normalizeIconPath(iconPath) {
    if (!iconPath) return null;

    // Absolute URL (CDN, etc.)
    if (iconPath.startsWith("http://") || iconPath.startsWith("https://")) {
      return iconPath;
    }

    // Already absolute (/static/...)
    if (iconPath.startsWith("/")) {
      return iconPath;
    }

    // Remove possible leading "static/" and prefix with "/static/"
    const cleaned = iconPath.replace(/^\/?static\//, "");
    return "/static/" + cleaned;
  }

  /**
   * Apply icon + alt text to a given tool button, if present.
   *
   * @param {HTMLButtonElement} btn
   * @param {string} iconPath - Icon path from items.yml
   * @param {string} label - Fallback label for alt text
   */
  function applyIconToButton(btn, iconPath, label) {
    if (!btn) return;
    const url = normalizeIconPath(iconPath);
    if (!url) return;

    // Store on dataset for other scripts (e.g. dropdown)
    btn.dataset.icon = url;

    const img = btn.querySelector(".land-tool-icon");
    if (img) {
      img.src = url;
      if (label) {
        img.alt = label;
      }
    }
  }

  // ==========================================================================
  // LandTools: tool selector + availability from /api/state
  // ==========================================================================

  const LandTools = (function () {
    let currentTool = "hands";
    let buttonsCache = null;

    /**
     * Lock a tool button:
     *  - "hands" must always remain visible and usable
     *  - other tools will be hidden from the dropdown if not crafted
     */
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

    /**
     * Unlock a tool button:
     *  - it becomes visible and clickable in the dropdown
     */
    function unlockToolButton(btn) {
      if (!btn) return;
      btn.classList.remove("tool-locked");
      btn.disabled = false;
      btn.removeAttribute("title");
      btn.style.display = "flex"; // show in dropdown
    }

    /**
     * Enable/disable tools based on player's crafted items.
     *
     * items = data.items from /api/state
     * -> Uses items.icon (from items.yml) to display icons for tools.
     */
    function applyAvailability(items) {
      const list = Array.isArray(items) ? items : [];

      // Fast map: item_key -> meta (with icon, qty, labels, ...)
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
        //  - no explicit requires_item
        //  - toolKey != "hands"
        //  - toolKey starts with "tool_"
        //  => requiredItemKey = toolKey
        if (!requiredItemKey && toolKey !== "hands" && toolKey.startsWith("tool_")) {
          requiredItemKey = toolKey;
        }

        // Hands (or a tool without requirement) = always available
        if (!requiredItemKey || toolKey === "hands") {
          // Hands icon is normally wired directly in the HTML
          unlockToolButton(btn);
          return;
        }

        // If we have meta for this item_key → push icon into the button
        const meta = metaByKey.get(requiredItemKey);
        if (meta && meta.icon) {
          const label =
            meta.label_fr ||
            meta.label_en ||
            btn.getAttribute("data-label") ||
            toolKey;
          applyIconToButton(btn, meta.icon, label);
        }

        // Lock / unlock depending on inventory
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
     *  - defaultTool: "hands" by default
     *  - ignore locked buttons
     */
    function initToolSelector(defaultTool = "hands") {
      const buttons = document.querySelectorAll(".land-tool-btn");
      if (!buttons.length) return;

      buttonsCache = buttons;

      // Default behavior:
      //  - set defaultTool active
      //  - lock all others until /api/state is loaded
      buttons.forEach((btn) => {
        const toolKey = btn.getAttribute("data-tool") || "hands";
        if (toolKey === defaultTool) {
          currentTool = toolKey;
          btn.classList.add("active");
        } else {
          lockToolButton(btn);
        }
      });

      // Click handler: switch current tool if not locked
      buttons.forEach((btn) => {
        btn.addEventListener("click", () => {
          // Ignore locked tools
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

    /**
     * Force current tool back to "hands" (used when a tool requires an item).
     */
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

    /**
     * Return current tool key.
     */
    function getCurrentTool() {
      return currentTool || "hands";
    }

    // Public API
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

  // ==========================================================================
  // LandCooldown: per-slot cooldown + optional green bar
  // ==========================================================================

  const LandCooldown = (function () {
    let intervalId = null;

    /**
     * Ensure there is a ticking interval updating cooldowns.
     */
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
      const statusEl  = slot.querySelector(".slot-status");
      const barFill   = slot.querySelector(".slot-cooldown-fill");
      const timerEl   = slot.querySelector(".slot-timer");

      const now = Date.now();
      const msEnd = new Date(iso).getTime();
      const diffSec = Math.ceil((msEnd - now) / 1000);

      // Texte de statut
      if (statusEl) {
        statusEl.textContent = diffSec > 0 ? "Cooldown…" : "Prêt à fouiller.";
      }

      // Timer mm:ss en coin supérieur droit
      if (timerEl) {
        if (diffSec > 0) {
          const m = Math.floor(diffSec / 60);
          const s = diffSec % 60;
          timerEl.textContent = `${m}:${String(s).padStart(2, "0")}`;
        } else {
          timerEl.textContent = "";
        }
      }

      // Green bar if we know total duration
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
        if (barFill) barFill.style.transform = "scaleX(0)";
        if (timerEl) timerEl.textContent = "";
        return false;
      }
    }

    /**
     * Ticking callback: updates all slots currently on cooldown.
     */
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

    // Public API
    return {
      setSlotCooldown,
      initFromDataset,
    };
  })();

  window.LandCooldown = LandCooldown;

  // ==========================================================================
  // LandCollect: generic /api/collect logic for all lands
  // ==========================================================================

  const LandCollect = (function () {
    /**
     * Perform /api/collect for a given slot element.
     */
    async function collectOnSlot(slotEl) {
      const land = window.CURRENT_LAND || slotEl.dataset.land || null;
      const statusEl = slotEl.querySelector(".slot-status");
      const slotIndex = Number(slotEl.getAttribute("data-slot"));

      // Level BEFORE collect (used to detect gained levels)
      const oldLevel =
        window.currentPlayer ? Number(window.currentPlayer.level || 0) : 0;

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
        const payload = { land, slot: slotIndex };

        // Possibility to disable tools for some lands
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

        // -----------------------------------------------------------
        // Error handling
        // -----------------------------------------------------------
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
            msg = "Tu n'as pas encore l'objet nécessaire pour utiliser cet outil.";
            LandTools.resetToHands();
          } else if (data.error) {
            msg = `Erreur: ${data.error}`;
          }

          if (statusEl) statusEl.textContent = msg;
          return;
        }

        // -----------------------------------------------------------
        // Success: loot + HUD
        // -----------------------------------------------------------
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

        // Loot toasts
        if (
          Array.isArray(data.loot) &&
          data.loot.length > 0 &&
          window.showLootToasts
        ) {
          window.showLootToasts(data.loot);
        }

        // First-resource notifications
        if (Array.isArray(data.loot) && typeof window.GameNotif !== "undefined") {
          const known = window._knownResourceKeys;
          const isFirstEver = known instanceof Set && known.size === 0;
          data.loot.forEach((entry) => {
            const key = entry.resource;
            if (key && known instanceof Set && !known.has(key)) {
              known.add(key);
              window.GameNotif.firstResource(key, entry.label || key, entry.icon || null, entry.final_amount ?? entry.base_amount ?? 1);
            }
          });
          // Tutorial: first ever collect
          if (isFirstEver && data.loot.length > 0 && typeof window.TutorialApp !== "undefined") {
            window.TutorialApp.onFirstCollect();
          }
        }

        // Quest ready toasts
        if (
          Array.isArray(data.quests_ready) &&
          data.quests_ready.length > 0 &&
          window.showQuestReadyToasts
        ) {
          window.showQuestReadyToasts(data.quests_ready);
        }

        // Player HUD update
        if (data.player && window.renderPlayer) {
          window.renderPlayer({
            ...data.player,
            next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
          });
        }

        // Recompute features (daily chest, shop, etc.)
        if (typeof window.recomputeFeaturesFromLevels === "function") {
          window.recomputeFeaturesFromLevels();
        }

        // -----------------------------------------------------------
        // Level up: story queue + level up modal
        // -----------------------------------------------------------
        if (data.level_up) {
          const newLevel = data.player?.level ?? oldLevel;

          // Level up modal + notifications + stories (via central orchestrator)
          if (typeof window.handleLevelUpFront === "function") {
            window.handleLevelUpFront(oldLevel, Number(newLevel), data.level_rewards || []);
          } else if (window.showLevelUpModal) {
            window.showLevelUpModal(newLevel, data.level_rewards || []);
          }
        }

        // -----------------------------------------------------------
        // Visual cooldown on the slot
        // -----------------------------------------------------------
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

    /**
     * Attach click handlers to all non-add slots.
     */
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

    // Public API
    return {
      initCollect,
      collectOnSlot,
    };
  })();

  window.LandCollect = LandCollect;

  // ==========================================================================
  // LandSlots: generic "+1 slot" logic
  // ==========================================================================

  const LandSlots = (function () {
    // -----------------------------------------------------------------------
    // Local state for modals
    // -----------------------------------------------------------------------
    let confirmModalEl = null;
    let confirmMsgEl = null;
    let confirmOkBtn = null;
    let confirmCancelBtn = null;
    let confirmHandler = null;

    let resultModalEl = null;
    let resultTitleEl = null;
    let resultMsgEl = null;
    let resultOkBtn = null;
    let resultHandler = null;

    /**
     * Initialize references and click handlers for slot modals.
     * If elements are missing, we silently fall back to confirm/alert.
     */
    function setupModals() {
      // Confirm modal
      confirmModalEl = document.getElementById("slot-confirm-modal");
      confirmMsgEl = document.getElementById("slot-confirm-message");
      confirmOkBtn = confirmModalEl
        ? confirmModalEl.querySelector('[data-slot-confirm="ok"]')
        : null;
      confirmCancelBtn = confirmModalEl
        ? confirmModalEl.querySelector('[data-slot-confirm="cancel"]')
        : null;

      if (confirmOkBtn) {
        confirmOkBtn.addEventListener("click", () => {
          const handler = confirmHandler;
          confirmHandler = null;
          closeConfirmModal();
          if (typeof handler === "function") {
            handler();
          }
        });
      }

      if (confirmCancelBtn) {
        confirmCancelBtn.addEventListener("click", () => {
          confirmHandler = null;
          closeConfirmModal();
        });
      }

      // Result modal
      resultModalEl = document.getElementById("slot-result-modal");
      resultTitleEl = document.getElementById("slot-result-title");
      resultMsgEl = document.getElementById("slot-result-message");
      resultOkBtn = document.getElementById("slot-result-ok");

      if (resultOkBtn) {
        resultOkBtn.addEventListener("click", () => {
          const handler = resultHandler;
          resultHandler = null;
          closeResultModal();
          if (typeof handler === "function") {
            handler();
          }
        });
      }
    }

    /**
     * Open the confirmation modal with a given message.
     * If modal is not available, fallback to window.confirm().
     */
    function openConfirmModal(message, onConfirm) {
      // Fallback: native confirm
      if (!confirmModalEl || !confirmMsgEl) {
        if (window.confirm(message)) {
          if (typeof onConfirm === "function") onConfirm();
        }
        return;
      }

      confirmMsgEl.textContent = message;
      confirmHandler = typeof onConfirm === "function" ? onConfirm : null;

      confirmModalEl.hidden = false;
      confirmModalEl.classList.add("is-visible");
    }

    /**
     * Close the confirmation modal.
     */
    function closeConfirmModal() {
      if (!confirmModalEl) return;
      confirmModalEl.classList.remove("is-visible");
      confirmModalEl.hidden = true;
    }

    /**
     * Open the result modal (success / error) with title + message.
     * If modal is not available, fallback to alert().
     */
    function openResultModal(title, message, onClose) {
      // Fallback: native alert
      if (!resultModalEl || !resultMsgEl || !resultOkBtn) {
        window.alert(message);
        if (typeof onClose === "function") onClose();
        return;
      }

      if (resultTitleEl && title) {
        resultTitleEl.textContent = title;
      }
      resultMsgEl.textContent = message;

      resultHandler = typeof onClose === "function" ? onClose : null;

      resultModalEl.hidden = false;
      resultModalEl.classList.add("is-visible");
    }

    /**
     * Close the result modal.
     */
    function closeResultModal() {
      if (!resultModalEl) return;
      resultModalEl.classList.remove("is-visible");
      resultModalEl.hidden = true;
    }

    /**
     * Attach click handler for "+1 slot" button.
     */
    function initAddSlot() {
      const addBtn = document.getElementById("add-slot-btn");
      if (!addBtn) return;

      // Prepare modal references (non-blocking if missing)
      setupModals();

      const landKey = window.CURRENT_LAND || addBtn.dataset.land || null;
      if (!landKey) return;

      const landLabel =
        window.LAND_LABEL || addBtn.dataset.landLabel || landKey || "ce land";

      addBtn.addEventListener("click", (evt) => {
        evt.stopPropagation();

        const hasFree = addBtn.dataset.hasFree === "1";
        const nextCost = Number(addBtn.dataset.nextCost || "0");

        let message;
        if (hasFree) {
          message =
            `Utiliser une carte emplacement gratuit pour débloquer un emplacement sur ${landLabel} ? ` +
            `(${I18n.t("game.lands.unlock_with")} ${I18n.currencyLabel("premium", 0).toLowerCase()}.)`;
        } else {
          message = `Confirmer l'achat d'un emplacement sur ${landLabel} pour ${nextCost} 💎 ?`;
        }

        // Ask for confirmation via custom modal (or confirm fallback)
        openConfirmModal(message, async () => {
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
              const errMsg =
                data.error || "Erreur lors de l'ajout de l'emplacement.";
              openResultModal("Erreur", errMsg);
              return;
            }

            // Update player HUD if provided
            if (data.player && window.renderPlayer) {
              window.renderPlayer(data.player);
            }

            // Success message
            let successMessage;
            if (data.used_free_card) {
              successMessage = `Carte emplacement gratuit utilisée. Nouvel emplacement débloqué sur ${landLabel} !`;
            } else {
              successMessage = `Nouvel emplacement débloqué sur ${landLabel} !`;
            }

            openResultModal("Emplacement débloqué", successMessage, () => {
              // Reload to refresh slot grid / cost / free card state
              window.location.reload();
            });
          } catch (err) {
            console.error("[LandSlots] Buy slot request failed:", err);
            openResultModal(
              "Erreur réseau",
              "Erreur réseau lors de l'achat de l'emplacement."
            );
          }
        });
      });
    }

    // Public API
    return {
      initAddSlot,
    };
  })();

  window.LandSlots = LandSlots;

  // ==========================================================================
  // Bootstrap on DOM ready
  // ==========================================================================

  document.addEventListener("DOMContentLoaded", () => {
    // Do nothing if not on a land page
    if (!window.CURRENT_LAND) return;

    // Default tool = hands
    LandTools.initToolSelector("hands");
    LandTools.loadAvailability();

    // Restore cooldowns (green bar) from data-* attributes
    LandCooldown.initFromDataset();

    // Click on slots = generic collect logic
    LandCollect.initCollect();

    // "+1 slot" generic logic
    LandSlots.initAddSlot();

    // Story "on_enter_land" (if configured)
    if (typeof window.handleStoryOnEnterLand === "function") {
      const slug =
        typeof window.CURRENT_LAND === "string" ? window.CURRENT_LAND : null;

      // Priority to explicit variable (you can define it in the template)
      // Example in village HTML:
      // <script>window.LAND_CARD_KEY = "land_village";</script>
      const storyLandKey =
        window.LAND_CARD_KEY ||
        window.LAND_STORY_KEY ||
        (slug ? `land_${slug}` : null);

      if (storyLandKey) {
        window.handleStoryOnEnterLand(storyLandKey);
      }
    }
  });
})(window);
