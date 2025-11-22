// static/GAME_UI/js/village/village_quests.js
// ============================================================
// VILLAGE QUESTS — Non-module JS (compatible with game_app.js)
// ------------------------------------------------------------
// - Uses global helpers http() and $() from common.js
// - Controls the village quests panel UI:
//     * Load quests from /api/state
//     * Render grouped quest cards (daily / weekly / other)
//     * Handle "running/completed" filter buttons
//     * Open / close panel
//     * Collapse / expand quest groups
// ============================================================

/* global http, $ */

// Current quests loaded from backend state
let QQ_currentQuests = [];

// "running" -> non-completed quests, "completed" -> completed only
let QQ_statusFilter = "running";

console.log("[quests] village_quests.js loaded");


// ============================================================
// TYPE / LABEL HELPERS
// ============================================================

/**
 * Convert quest_type into a french label.
 *
 * @param {Object} quest
 * @returns {string}
 */
function QQ_questTypeLabel(quest) {
  switch (quest.quest_type) {
    case "daily":
      return "Quotidienne";
    case "weekly":
      return "Hebdomadaire";
    case "bonus":
      return "Bonus";
    case "event":
      return "Événement";
    default:
      return quest.quest_type || "Quête";
  }
}


// ============================================================
// OBJECTIVES RENDERING
// ============================================================

/**
 * Render a single objective block (with progress bar).
 *
 * @param {Object} obj
 * @returns {string} HTML
 */
function QQ_renderObjective(obj) {
  const current = obj.current || 0;
  const target = obj.target || 0;
  const ratio = target > 0 ? Math.min(current / target, 1) : 0;

  let label = "";
  if (obj.kind === "collect_resource") {
    label = `Récolter ${target} × ${obj.resource_key || "?"}`;
  } else if (obj.kind === "craft_item") {
    label = `Crafter ${target} × ${obj.item_key || "?"}`;
  } else {
    label = `${obj.kind} (${current}/${target})`;
  }

  return `
    <div class="quest-objective">
      <div class="quest-objective-label">${label}</div>
      <div class="quest-progress-bar">
        <div class="quest-progress-fill" style="width: ${ratio * 100}%"></div>
      </div>
      <div class="quest-progress-text">${current} / ${target}</div>
    </div>
  `;
}


// ============================================================
// REWARDS RENDERING
// ============================================================

/**
 * Render rewards pill list (coins/diams for now).
 *
 * @param {Object} rewards
 * @returns {string} HTML
 */
function QQ_renderRewards(rewards) {
  if (!rewards) return "";

  const coins = rewards.coins || 0;
  const diams = rewards.diams || 0;
  const parts = [];

  if (coins > 0) {
    parts.push(`
      <div class="quest-reward-pill">
        <span>🪙</span>
        <span>+${coins} coins</span>
      </div>
    `);
  }
  if (diams > 0) {
    parts.push(`
      <div class="quest-reward-pill">
        <span>💎</span>
        <span>+${diams} diams</span>
      </div>
    `);
  }

  if (parts.length === 0) return "";
  return `<div class="quest-rewards">${parts.join("")}</div>`;
}


// ============================================================
// QUEST CARD RENDERING
// ============================================================

/**
 * Render a full quest card (header, description, objectives, rewards).
 *
 * @param {Object} q Quest object from backend
 * @returns {string} HTML
 */
function QQ_renderQuestCard(q) {
  const typeLabel = QQ_questTypeLabel(q);
  const badgeClass = `quest-badge ${q.quest_type}`;

  const title = q.title_fr || q.title_en || q.template_key;
  const desc = q.description_fr || q.description_en || "";

  const objectivesHtml = (q.objectives || [])
    .map(QQ_renderObjective)
    .join("");

  const rewardsHtml = QQ_renderRewards(q.rewards);

  return `
    <div class="quest-card">
      <div class="quest-header">
        <h3 class="quest-title">${title}</h3>
        <span class="${badgeClass}">${typeLabel}</span>
      </div>

      <p class="quest-desc">${desc}</p>

      ${objectivesHtml}
      ${rewardsHtml}
    </div>
  `;
}


// ============================================================
// PANEL RENDERING (FULL LIST + GROUPING + FILTER)
// ============================================================

/**
 * Render the whole quests panel into #quests-list.
 * Applies:
 *   - running/completed filter (QQ_statusFilter)
 *   - grouping by quest_type (daily / weekly / other)
 */
function QQ_renderQuestsPanel() {
  const container = $("quests-list");
  if (!container) {
    console.warn("[quests] container #quests-list NOT FOUND");
    return;
  }

  // 1) Apply running / completed filter
  const filtered = QQ_currentQuests.filter((q) => {
    const isCompleted = q.status === "completed";
    if (QQ_statusFilter === "completed") {
      return isCompleted;
    }
    // "running" = everything that is NOT completed
    return !isCompleted;
  });

  if (!filtered.length) {
    container.innerHTML = `
      <p class="quest-desc">
        Aucune quête pour ce filtre pour l'instant.
      </p>
    `;
    return;
  }

  // 2) Group quests by type
  const groupsDef = [
    { key: "daily", label: "Quêtes quotidiennes" },
    { key: "weekly", label: "Quêtes hebdomadaires" },
    { key: "other", label: "Autres quêtes" },
  ];

  const groups = {
    daily: [],
    weekly: [],
    other: [],
  };

  filtered.forEach((q) => {
    if (q.quest_type === "daily") {
      groups.daily.push(q);
    } else if (q.quest_type === "weekly") {
      groups.weekly.push(q);
    } else {
      groups.other.push(q);
    }
  });

  const htmlParts = [];

  groupsDef.forEach((g) => {
    const list = groups[g.key];
    if (!list.length) return;

    const cardsHtml = list.map(QQ_renderQuestCard).join("");

    htmlParts.push(`
      <div class="quests-group" data-group="${g.key}">
        <div class="quests-group-header" onclick="QQ_toggleGroup('${g.key}')">
          <span class="quests-group-title">${g.label}</span>
          <span class="quests-group-chevron">⌄</span>
        </div>
        <div class="quests-group-body">
          ${cardsHtml}
        </div>
      </div>
    `);
  });

  container.innerHTML = htmlParts.join("");
}


// ============================================================
// DATA LOADING FROM BACKEND
// ============================================================

/**
 * Load quests from /api/state, then render the panel.
 * Uses http("GET", "/api/state") helper (common.js).
 */
function QQ_loadQuestsFromState() {
  return http("GET", "/api/state").then((r) => {
    if (!r.ok) {
      console.error("Failed to load quests:", r);
      return;
    }

    console.log("[quests] state from /api/state =", r.data);

    const state = r.data || {};
    QQ_currentQuests = state.quests || [];
    console.log("[quests] currentQuests =", QQ_currentQuests);

    QQ_renderQuestsPanel();
  });
}


// ============================================================
// PUBLIC API: OPEN/CLOSE PANEL
// ============================================================

/**
 * Open quests panel and load current quests.
 * Exposed on window for usage from other scripts.
 */
window.openQuestsPanel = function () {
  console.log("[quests] openQuestsPanel()");
  const panel = $("quests-panel");
  if (panel) {
    panel.classList.remove("hidden");
    QQ_loadQuestsFromState();
  } else {
    console.warn("[quests] quests-panel not found");
  }
};

/**
 * Close quests panel.
 * Exposed on window for usage from other scripts.
 */
window.closeQuestsPanel = function () {
  const panel = $("quests-panel");
  if (panel) {
    panel.classList.add("hidden");
  }
};


// ============================================================
// INITIALIZATION: BUTTONS / FILTERS
// ============================================================

/**
 * Initialize quests UI:
 * - Bind open / close button
 * - Bind filter buttons (running / completed)
 *
 * Should be called once from main game JS when HUD is ready.
 */
window.initQuestsUI = function () {
  const btn = $("btn-quests");
  const close = $("btn-quests-close");

  // Open button in HUD
  if (btn) {
    btn.addEventListener("click", () => {
      console.log("[quests] Quests button clicked");
      window.openQuestsPanel();
    });
  }

  // Close button in panel
  if (close) {
    close.addEventListener("click", () => {
      console.log("[quests] Quests close button clicked");
      window.closeQuestsPanel();
    });
  }

  // ----------------------------------------------------------
  // Filter buttons: running / completed
  // Buttons should have class .qfilter-btn and data-filter attr
  // ----------------------------------------------------------
  const filterButtons = document.querySelectorAll(".qfilter-btn");

  filterButtons.forEach((btnEl) => {
    btnEl.addEventListener("click", () => {
      const mode = btnEl.getAttribute("data-filter") || "running";
      QQ_statusFilter = mode === "completed" ? "completed" : "running";

      // Update active visual state on all filter buttons
      filterButtons.forEach((b) => {
        if (b === btnEl) {
          b.classList.add("qfilter-active");
        } else {
          b.classList.remove("qfilter-active");
        }
      });

      // Re-render the panel using the new filter
      QQ_renderQuestsPanel();
    });
  });
};


// ============================================================
// GROUP COLLAPSE / EXPAND
// ============================================================

/**
 * Collapse / expand a specific quest group.
 * Triggered by clicking on the group's header.
 *
 * @param {string} groupKey "daily" | "weekly" | "other"
 */
window.QQ_toggleGroup = function (groupKey) {
  const group = document.querySelector(
    `.quests-group[data-group="${groupKey}"]`
  );
  if (!group) return;

  group.classList.toggle("collapsed");
};
