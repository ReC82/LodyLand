// static/GAME_UI/js/quests_app.js
// NON-MODULE VERSION – Compatible with existing game_app.js
// Uses http() and $() helpers from common.js

/* global http, $ */

let QQ_currentQuests = [];
let QQ_statusFilter = "running";
let QQ_typeFilter = "all";   // "all", "daily", "weekly", etc.
console.log("[quests] quests_app.js loaded");
/**
 * Convert quest_type into a label.
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

/**
 * Render objective HTML.
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

/**
 * Render rewards
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


/**
 * Render the whole quests list
 */
function QQ_renderQuestsPanel() {
  const container = $("quests-list");
  if (!container) {
    console.warn("[quests] container #quests-list NOT FOUND");
    return;
  }

  // 1) Filtre statut : "En cours" / "Terminées"
  const filtered = QQ_currentQuests.filter((q) => {
    const isCompleted = q.status === "completed";
    const isExpired = q.status === "expired";
    const isFailed = q.status === "failed";

    if (QQ_statusFilter === "completed") {
      // Dans l'onglet "Terminées" on montre:
      // - completed
      // - expired
      // - failed
      return isCompleted || isExpired || isFailed;
    }

    // Dans l'onglet "En cours", on ne garde que les actives
    return q.status === "active";
  });

  // 2) Filtre par TYPE (onglets)
  const filteredByType = filtered.filter((q) => {
    if (QQ_typeFilter === "all") return true;

    if (QQ_typeFilter === "daily") return q.quest_type === "daily";
    if (QQ_typeFilter === "storyline") return q.quest_type === "storyline";
    if (QQ_typeFilter === "weekly") return q.quest_type === "weekly";
    if (QQ_typeFilter === "monthly") return q.quest_type === "monthly";

    if (QQ_typeFilter === "other") {
      // "other" = tout ce qui n'est PAS daily / storyline / weekly / monthly
      return (
        q.quest_type !== "daily" &&
        q.quest_type !== "storyline" &&
        q.quest_type !== "weekly" &&
        q.quest_type !== "monthly"
      );
    }

    return true;
  });

  if (!filteredByType.length) {
    container.innerHTML = `
      <p class="quest-desc text-muted small">
        Aucune quête pour ce filtre pour l'instant.
      </p>
    `;
    return;
  }

  // 3) Si on est sur un onglet spécifique (daily / storyline / other…)
  //    -> on affiche juste une liste de cartes, sans sous-groupes.
  if (QQ_typeFilter !== "all") {
    const cardsHtml = filteredByType.map(QQ_renderQuestCard).join("");
    container.innerHTML = cardsHtml;
    return;
  }

  // 4) Mode "Toutes" : on regroupe par type (comme avant, mais avec storyline séparé)
  const groupsDef = [
    { key: "daily",     label: "Quêtes quotidiennes" },
    { key: "weekly",    label: "Quêtes hebdomadaires" },
    { key: "storyline", label: "Quêtes storyline" },
    { key: "other",     label: "Autres quêtes" },
  ];

  const groups = {
    daily: [],
    weekly: [],
    storyline: [],
    other: [],
  };

  filteredByType.forEach((q) => {
    if (q.quest_type === "daily") {
      groups.daily.push(q);
    } else if (q.quest_type === "weekly") {
      groups.weekly.push(q);
    } else if (q.quest_type === "storyline") {
      groups.storyline.push(q);
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



/**
 * Load quests from /api/state
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


/**
 * Show / hide panel
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

window.closeQuestsPanel = function () {
  const panel = $("quests-panel");
  if (panel) {
    panel.classList.add("hidden");
  }
};

window.initQuestsUI = function () {
  const btn = $("btn-quests");
  const close = $("btn-quests-close");

  if (btn) {
    btn.addEventListener("click", () => {
      console.log("[quests] Quests button clicked");
      window.openQuestsPanel();
    });
  }

  if (close) {
    close.addEventListener("click", () => {
      console.log("[quests] Quests close button clicked");
      window.closeQuestsPanel();
    });
  }

  // 1) Filtres statut : En cours / Terminées
  const filterButtons = document.querySelectorAll(".qfilter-btn");
  filterButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.getAttribute("data-filter") || "running";
      QQ_statusFilter = mode === "completed" ? "completed" : "running";

      // Style actif
      filterButtons.forEach((b) => {
        if (b === btn) {
          b.classList.add("qfilter-active");
        } else {
          b.classList.remove("qfilter-active");
        }
      });

      QQ_renderQuestsPanel();
    });
  });

  // 2) Onglets de TYPE : Toutes / Quotidiennes / Storyline / Autres
  const typeButtons = document.querySelectorAll(".qtype-btn");
  typeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const qtype = btn.getAttribute("data-qtype") || "all";
      QQ_typeFilter = qtype;

      // Style actif
      typeButtons.forEach((b) => {
        if (b === btn) {
          b.classList.add("qtype-active");
        } else {
          b.classList.remove("qtype-active");
        }
      });

      QQ_renderQuestsPanel();
    });
  });
};


window.QQ_toggleGroup = function (groupKey) {
  const group = document.querySelector(`.quests-group[data-group="${groupKey}"]`);
  if (!group) return;
  group.classList.toggle("collapsed");
};