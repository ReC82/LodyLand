// static/GAME_UI/js/tutorial_app.js
// Interactive spotlight tutorial for LodyLand.
// Uses PlayerStoryFlag (via markStoryEventSeen / hasSeenStoryEvent) to persist progress.
// Steps are shown in sequence; each step highlights a DOM element + shows a tooltip bubble.

(function (window) {
  "use strict";

  // ---------------------------------------------------------------------------
  // Language helper
  // ---------------------------------------------------------------------------
  function _lang() { return document.documentElement.lang || "fr"; }
  function _t(obj) {
    if (!obj) return "";
    const l = _lang();
    return obj[l] || obj.fr || obj.en || "";
  }

  // ---------------------------------------------------------------------------
  // Step definitions
  // Each step:
  //   id        — unique key (stored as seen via markStoryEventSeen)
  //   target()  — returns DOM element to spotlight (or null for centered modal)
  //   title     — { fr, en }
  //   text      — { fr, en }
  //   advance   — "click_target" | "manual"
  //   position  — "right" | "left" | "top" | "bottom" | "centered"
  //   stepLabel — { fr, en } e.g. "Étape 1/6"
  // ---------------------------------------------------------------------------
  const STEPS = {

    tutorial_forest_collect: {
      // Target the first available (non-cooldown) slot tile, fallback to any slot tile
      target: () =>
        document.querySelector(".slot-tile:not(.slot-add):not(.slot-on-cooldown)") ||
        document.querySelector(".slot-tile:not(.slot-add)"),
      title:    { fr: "Récolter tes premières ressources 🌿", en: "Gather your first resources 🌿" },
      text:     { fr: "Clique sur une <strong>case de forêt</strong> pour récolter. Chaque récolte te donne de l'XP et des ressources.", en: "Click on a <strong>forest tile</strong> to harvest. Each harvest gives you XP and resources." },
      advance:  "click_target",
      position: "right",
      stepLabel: { fr: "Tutoriel • Récolte", en: "Tutorial • Harvest" },
    },

    tutorial_inventory: {
      // Centered — no target. Avoids the menu opening on top of the bubble.
      target: () => null,
      title:    { fr: "Ton inventaire 🎒", en: "Your inventory 🎒" },
      text:     { fr: "Tes ressources récoltées et tes cartes s'accumulent dans ton <strong>Inventaire</strong>. Ouvre le menu ☰ (en haut à droite) puis clique sur <em>Inventaire</em> pour le consulter.", en: "Your gathered resources and cards build up in your <strong>Inventory</strong>. Open the ☰ menu (top right) and click <em>Inventory</em> to view it." },
      advance:  "manual",
      position: "centered",
      stepLabel: { fr: "Tutoriel • Inventaire", en: "Tutorial • Inventory" },
    },

    tutorial_notifications: {
      // Always centered — the notifications container may be empty/invisible
      target: () => null,
      title:    { fr: "Les notifications 🔔", en: "Notifications 🔔" },
      text:     { fr: "Des bulles apparaissent en <strong>haut à droite</strong> pour t'informer : première ressource découverte, passage de niveau, fonctionnalités débloquées, coffre journalier, quête accomplie…", en: "Bubbles appear in the <strong>top right</strong> to keep you informed: new resource found, level up, features unlocked, daily chest, quest completed…" },
      advance:  "manual",
      position: "centered",
      stepLabel: { fr: "Tutoriel • Notifications", en: "Tutorial • Notifications" },
    },

    tutorial_inventory_page: {
      // Shown when the player first lands on /inventory
      target: () => document.querySelector(".inv-tabs"),
      title:    { fr: "Bienvenue dans ton inventaire 🎒", en: "Welcome to your inventory 🎒" },
      text:     { fr: "Ici tu retrouves tout ce que tu possèdes : tes <strong>ressources</strong> récoltées, tes <strong>trésors</strong>, tes <strong>items</strong> craftés et tes <strong>cartes</strong> achetées ou reçues en récompense.", en: "Here you'll find everything you own: gathered <strong>resources</strong>, <strong>treasures</strong>, crafted <strong>items</strong>, and <strong>cards</strong> bought or received as rewards." },
      advance:  "manual",
      position: "bottom",
      stepLabel: { fr: "Tutoriel • Inventaire", en: "Tutorial • Inventory" },
    },

    tutorial_xp_bar: {
      target: () => document.getElementById("hud-level-zone") || document.getElementById("hud-level-zone-ring"),
      title:    { fr: "Expérience & Niveaux ⭐", en: "Experience & Levels ⭐" },
      text:     { fr: "Chaque action te rapporte de l'XP. En montant de niveau, tu débloques de nouveaux lieux, fonctionnalités et récompenses.", en: "Every action earns you XP. Leveling up unlocks new places, features and rewards." },
      advance:  "manual",
      position: "bottom",
      stepLabel: { fr: "Tutoriel • Progression", en: "Tutorial • Progression" },
    },

    tutorial_notebook: {
      target: () => document.getElementById("hud-notebook-btn"),
      title:    { fr: "Le carnet de notes 📘", en: "The notebook 📘" },
      text:     { fr: "Ce carnet liste tous tes lieux débloqués, tes compétences et ta progression. Clique dessus pour l'explorer !", en: "This notebook lists all your unlocked lands, skills and progress. Click it to explore!" },
      advance:  "click_target",
      position: "right",
      stepLabel: { fr: "Tutoriel • Carnet", en: "Tutorial • Notebook" },
    },

    tutorial_daily_chest: {
      target: () => document.getElementById("hudDaily"),
      title:    { fr: "Coffre journalier 🎁", en: "Daily chest 🎁" },
      text:     { fr: "Ouvre ce coffre chaque jour pour des récompenses gratuites ! Les jours consécutifs améliorent les récompenses.", en: "Open this chest every day for free rewards! Consecutive days improve the loot." },
      advance:  "click_target",
      position: "bottom",
      stepLabel: { fr: "Tutoriel • Coffre", en: "Tutorial • Chest" },
    },

    tutorial_travel: {
      target: () => document.getElementById("hud-travel-btn"),
      title:    { fr: "Voyager vers d'autres lieux 🗺️", en: "Travel to other places 🗺️" },
      text:     { fr: "Clique ici pour voir les lieux disponibles et voyager vers le village. Chaque lieu offre des ressources différentes.", en: "Click here to see available places and travel to the village. Each land offers different resources." },
      advance:  "click_target",
      position: "bottom",
      stepLabel: { fr: "Tutoriel • Voyage", en: "Tutorial • Travel" },
    },

    tutorial_quests: {
      target: () => document.getElementById("btn-quests"),
      title:    { fr: "Tes quêtes 📜", en: "Your quests 📜" },
      text:     { fr: "Les quêtes te guident pas à pas et te récompensent. Consulte-les régulièrement pour savoir quoi faire ensuite.", en: "Quests guide you step by step and reward your effort. Check them regularly to know what to do next." },
      advance:  "click_target",
      position: "bottom",
      stepLabel: { fr: "Tutoriel • Quêtes", en: "Tutorial • Quests" },
    },

  };

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  let _currentStepId   = null;
  let _currentTarget   = null;
  let _clickHandler    = null;
  let _onDone          = null;
  let _resizeObserver  = null;

  // ---------------------------------------------------------------------------
  // Persistence helpers (piggybacks on story flag system)
  // ---------------------------------------------------------------------------
  function _hasDone(stepId) {
    return typeof window.hasSeenStoryEvent === "function"
      ? window.hasSeenStoryEvent(stepId)
      : false;
  }

  function _markDone(stepId) {
    if (typeof window.markStoryEventSeen === "function") {
      window.markStoryEventSeen(stepId);
    }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Try to show a tutorial step.
   * If already done, calls onDone immediately and returns false.
   * @param {string}   stepId
   * @param {Function} [onDone]
   * @returns {boolean} true if step was shown
   */
  function tryShowStep(stepId, onDone) {
    if (_hasDone(stepId)) {
      if (typeof onDone === "function") onDone();
      return false;
    }

    const step = STEPS[stepId];
    if (!step) {
      console.warn("[tutorial] Unknown step:", stepId);
      if (typeof onDone === "function") onDone();
      return false;
    }

    _showStep(stepId, step, onDone);
    return true;
  }

  /**
   * Skip the currently visible tutorial step (user chose to skip).
   */
  function skipCurrentStep() {
    if (_currentStepId) _completeStep(_currentStepId);
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------
  function _showStep(stepId, step, onDone) {
    _currentStepId = stepId;
    _onDone = onDone || null;

    // Safety: remove any lingering overlay from a previous step (e.g. if the
    // fade timer hasn't fired yet but we're already showing the next step).
    document.querySelectorAll(".tutorial-overlay").forEach(el => el.remove());

    const target = step.target ? step.target() : null;
    _currentTarget = target;

    const hasTarget = !!target;
    const lang = _lang();

    // -- Build overlay --
    const overlay = document.createElement("div");
    overlay.id = "tutorialOverlay";
    overlay.className = "tutorial-overlay" + (hasTarget ? "" : " tutorial-overlay--no-target");

    // -- Spotlight (only if we have a target) --
    if (hasTarget) {
      const spotlight = document.createElement("div");
      spotlight.className = "tutorial-spotlight";
      spotlight.id = "tutorialSpotlight";
      _placeSpotlight(spotlight, target);
      overlay.appendChild(spotlight);
      target.classList.add("tutorial-target-pulse");
    }

    // -- Bubble --
    const pos = step.position || "bottom";
    const bubble = document.createElement("div");
    bubble.className = `tutorial-bubble tutorial-bubble--${pos}`;
    bubble.id = "tutorialBubble";

    const manualBtn = step.advance === "manual"
      ? `<button class="tutorial-bubble-btn" id="tutorialNextBtn">${lang === "en" ? "Got it ✓" : "Compris ✓"}</button>`
      : `<div class="tutorial-bubble-hint">👆 ${lang === "en" ? "Click the highlighted element" : "Clique sur l'élément mis en évidence"}</div>`;

    bubble.innerHTML = `
      <div class="tutorial-bubble-step">${_t(step.stepLabel)}</div>
      <div class="tutorial-bubble-title">${_t(step.title)}</div>
      <div class="tutorial-bubble-text">${_t(step.text)}</div>
      ${manualBtn}
      <button class="tutorial-bubble-skip" id="tutorialSkipBtn">
        ${lang === "en" ? "Skip tutorial" : "Passer le tutoriel"}
      </button>
    `;

    overlay.appendChild(bubble);
    document.body.appendChild(overlay);

    // Position bubble
    if (hasTarget) {
      _placeBubble(bubble, target, pos);
    } else {
      bubble.classList.add("tutorial-bubble--centered");
    }

    // Animate in
    requestAnimationFrame(() => requestAnimationFrame(() => {
      overlay.classList.add("tutorial-overlay--visible");
    }));

    // Wire: manual advance
    if (step.advance === "manual") {
      document.getElementById("tutorialNextBtn")?.addEventListener("click", () => {
        _completeStep(stepId);
      });
    }

    // Wire: click-target advance
    if (step.advance === "click_target" && target) {
      _clickHandler = () => _completeStep(stepId);
      target.addEventListener("click", _clickHandler, { once: true });
    }

    // Wire: skip button
    document.getElementById("tutorialSkipBtn")?.addEventListener("click", () => {
      _skipAll();
    });

    // Keep spotlight updated when window resizes
    if (hasTarget) {
      _resizeObserver = new ResizeObserver(() => {
        const sp = document.getElementById("tutorialSpotlight");
        const bb = document.getElementById("tutorialBubble");
        if (sp && target) _placeSpotlight(sp, target);
        if (bb && target) _placeBubble(bb, target, pos);
      });
      _resizeObserver.observe(document.body);
    }
  }

  // ---------------------------------------------------------------------------
  // Geometry helpers
  // ---------------------------------------------------------------------------
  function _placeSpotlight(el, target) {
    const r = target.getBoundingClientRect();
    const pad = 10;
    el.style.left   = `${r.left   - pad}px`;
    el.style.top    = `${r.top    - pad}px`;
    el.style.width  = `${r.width  + pad * 2}px`;
    el.style.height = `${r.height + pad * 2}px`;
  }

  function _placeBubble(bubble, target, pos) {
    const r      = target.getBoundingClientRect();
    const offset = 18;
    const W      = window.innerWidth;
    const H      = window.innerHeight;

    // Reset inline styles first
    bubble.style.left   = "";
    bubble.style.right  = "";
    bubble.style.top    = "";
    bubble.style.bottom = "";
    bubble.style.transform = "";

    const bw = 290; // approx bubble width

    if (pos === "right") {
      let left = r.right + offset;
      if (left + bw > W - 8) left = r.left - bw - offset; // flip if off-screen
      bubble.style.left = `${Math.max(8, left)}px`;
      bubble.style.top  = `${Math.max(8, r.top + r.height / 2)}px`;
      bubble.style.transform = "translateY(-50%)";
    } else if (pos === "left") {
      bubble.style.left = `${Math.max(8, r.left - bw - offset)}px`;
      bubble.style.top  = `${r.top + r.height / 2}px`;
      bubble.style.transform = "translateY(-50%)";
    } else if (pos === "bottom") {
      let top = r.bottom + offset;
      bubble.style.left = `${Math.min(W - bw - 8, Math.max(8, r.left + r.width / 2 - bw / 2))}px`;
      bubble.style.top  = `${Math.min(H - 200, top)}px`;
    } else { // top
      bubble.style.left   = `${Math.min(W - bw - 8, Math.max(8, r.left + r.width / 2 - bw / 2))}px`;
      bubble.style.bottom = `${H - r.top + offset}px`;
    }
  }

  // ---------------------------------------------------------------------------
  // Completion / teardown
  // ---------------------------------------------------------------------------
  const _FADE_MS = 340; // must be >= CSS transition duration (0.3s)

  function _completeStep(stepId) {
    _markDone(stepId);
    const cb = _onDone;
    _onDone = null;
    _currentStepId = null;
    _teardown();
    // Wait for the fade-out to finish before showing the next step,
    // otherwise the old overlay overlaps the new one.
    setTimeout(() => {
      if (typeof cb === "function") cb();
    }, _FADE_MS);
  }

  function _skipAll() {
    // Mark ALL steps as done so tutorial never shows again
    Object.keys(STEPS).forEach((id) => _markDone(id));
    _onDone = null;
    _currentStepId = null;
    _teardown();

    setTimeout(() => {
      if (typeof window.GameNotif !== "undefined") {
        window.GameNotif.show({
          type: "info",
          icon: "ℹ️",
          title: "Tutoriel ignoré",
          body: "Tu peux retrouver les infos dans le carnet 📘.",
          duration: 4000,
        });
      }
    }, _FADE_MS);
  }

  function _teardown() {
    // Remove overlay — strip the ID immediately so the next step's getElementById
    // won't find this old (still-fading) element and wire listeners to it.
    const overlay = document.getElementById("tutorialOverlay");
    if (overlay) {
      overlay.removeAttribute("id");  // detach from ID registry NOW
      overlay.classList.remove("tutorial-overlay--visible");
      setTimeout(() => overlay.remove(), 320); // let CSS fade play out
    }

    // Remove pulse class from target
    if (_currentTarget) {
      _currentTarget.classList.remove("tutorial-target-pulse");
    }

    // Remove click listener if present
    if (_clickHandler && _currentTarget) {
      _currentTarget.removeEventListener("click", _clickHandler);
    }
    _clickHandler = null;
    _currentTarget = null;

    // Stop resize observer
    if (_resizeObserver) {
      _resizeObserver.disconnect();
      _resizeObserver = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Pre-built sequences (called from game_app.js / game_menu.js)
  // ---------------------------------------------------------------------------

  /**
   * Called after intro story + name modal completes.
   * Shows the "how to collect" step.
   */
  function startIntroSequence() {
    setTimeout(() => {
      tryShowStep("tutorial_forest_collect");
    }, 600);
  }

  /**
   * Called after a successful first collect.
   * Chain: XP bar → notifications → inventory location hint.
   */
  function onFirstCollect() {
    tryShowStep("tutorial_xp_bar", () => {
      tryShowStep("tutorial_notifications", () => {
        tryShowStep("tutorial_inventory");
      });
    });
  }

  /**
   * Called when the player first visits /inventory.
   * Shows an explanation of what's in the inventory.
   */
  function onInventoryVisit() {
    tryShowStep("tutorial_inventory_page");
  }

  /**
   * Called when level 1 is reached.
   */
  function onLevel1Reached() {
    tryShowStep("tutorial_notebook");
  }

  /**
   * Called when level 3 is reached (village, travel, quests, daily unlock).
   */
  function onLevel3Reached() {
    tryShowStep("tutorial_daily_chest", () => {
      tryShowStep("tutorial_travel", () => {
        tryShowStep("tutorial_quests");
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Expose
  // ---------------------------------------------------------------------------
  window.TutorialApp = {
    tryShowStep,
    skipCurrentStep,
    startIntroSequence,
    onFirstCollect,
    onInventoryVisit,
    onLevel1Reached,
    onLevel3Reached,
  };

})(window);
