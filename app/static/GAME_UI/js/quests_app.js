// quests_app.js — Quest grid UI
// Requires http() and $() from common.js

/* global http, $ */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let QQ_quests = { daily: [], weekly: [], continuous: [] };
let QQ_activeTab = "daily";
let QQ_detailQuestId = null;
let QQ_locked = false;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function QQ_title(q) {
  return q.title_fr || q.title_en || q.template_key || "—";
}

function QQ_desc(q) {
  return q.description_fr || q.description_en || "";
}

function QQ_isReady(q) {
  return q.status === "ready";
}

function QQ_progressRatio(q) {
  if (!q.objectives || !q.objectives.length) return 1;
  const obj = q.objectives[0];
  const cur = obj.current || 0;
  const tgt = obj.target || 1;
  return Math.min(cur / tgt, 1);
}

function QQ_progressText(q) {
  if (!q.objectives || !q.objectives.length) return "";
  const obj = q.objectives[0];
  return `${obj.current || 0} / ${obj.target || 0}`;
}

/** Difficulty tier for a quest ("easy" | "medium" | "hard") */
function QQ_difficulty(q) {
  return q.difficulty || "easy";
}

/** Icon URL for the first objective */
function QQ_questIcon(q) {
  const obj = (q.objectives || [])[0];
  if (!obj) return null;
  if (obj.resource_key) return `/static/assets/img/items/resources/${obj.resource_key}.png`;
  if (obj.item_key)     return `/static/assets/img/items/resources/${obj.item_key}.png`;
  return null;
}

function QQ_formatExpiry(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d)) return null;
  const now = new Date();
  const diff = d - now;
  if (diff < 0) return "Expirée";
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  if (h >= 24) return `${Math.floor(h / 24)}j ${h % 24}h`;
  return `${h}h ${m}m`;
}

// ---------------------------------------------------------------------------
// Quest card (compact)
// ---------------------------------------------------------------------------
function QQ_renderCard(q) {
  const title   = QQ_title(q);
  const ratio   = QQ_progressRatio(q);
  const pctText = QQ_progressText(q);
  const icon    = QQ_questIcon(q);
  const ready   = QQ_isReady(q);
  const rewards = q.rewards || {};
  const shards  = rewards.shards  || rewards.coins  || 0;
  const essence = rewards.essence || rewards.diams  || 0;
  const diff    = QQ_difficulty(q);

  const diffLabels = { easy: "Facile", medium: "Moyen", hard: "Difficile" };

  const iconHtml = icon
    ? `<img class="qcard-icon" src="${icon}" alt="" onerror="this.style.display='none'">`
    : `<div class="qcard-icon-placeholder">📦</div>`;

  const xp = (q.rewards || {}).xp || 0;

  const rewardBadge = shards
    ? `<div class="qcard-reward"><img src="/static/assets/img/ui/shards.png" alt="shards"> ${shards}</div>`
    : (essence
      ? `<div class="qcard-reward essence"><img src="/static/assets/img/ui/essence.png" alt="essence"> ${essence}</div>`
      : (xp
        ? `<div class="qcard-reward xp">⭐ ${xp}</div>`
        : ""));

  const readyBadge = ready
    ? `<div class="qcard-ready-badge">✔ Prêt</div>`
    : `<div class="qcard-diff-badge diff-${diff}">${diffLabels[diff] || diff}</div>`;

  return `
    <div class="qcard${ready ? " is-ready" : ""}" data-quest-id="${q.id}" role="button" tabindex="0">
      ${rewardBadge}
      ${readyBadge}
      <div class="qcard-body">
        ${iconHtml}
        <div class="qcard-title">${title}</div>
      </div>
      <div class="qcard-footer">
        <div class="qcard-bar-wrap">
          <div class="qcard-bar-fill" style="width:${Math.round(ratio * 100)}%"></div>
        </div>
        <div class="qcard-progress">${pctText}</div>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Render a grid section
// ---------------------------------------------------------------------------
function QQ_renderGrid(type) {
  const grid = document.getElementById(`grid-${type}`);
  if (!grid) return;

  const list = QQ_quests[type] || [];

  if (!list.length) {
    grid.innerHTML = `<p class="quests-empty">Aucune quête ${type === "daily" ? "quotidienne" : type === "weekly" ? "hebdomadaire" : "continue"} en cours.</p>`;
    return;
  }

  grid.innerHTML = list.map(QQ_renderCard).join("");
}

function QQ_updateBadges() {
  ["daily", "weekly", "continuous"].forEach(type => {
    const el = document.getElementById(`badge-${type}`);
    if (!el) return;
    const ready = (QQ_quests[type] || []).filter(QQ_isReady).length;
    if (ready > 0) {
      el.textContent = ready;
      el.style.display = "inline-flex";
    } else {
      el.style.display = "none";
    }
  });
}

// ---------------------------------------------------------------------------
// Detail modal
// ---------------------------------------------------------------------------
function QQ_openDetail(questId) {
  const q = Object.values(QQ_quests).flat().find(q => q.id === questId);
  if (!q) return;

  QQ_detailQuestId = questId;

  const modal = document.getElementById("quest-detail-modal");
  const content = document.getElementById("quest-modal-content");
  if (!modal || !content) return;

  const rewards = q.rewards || {};
  const shards  = rewards.shards  || rewards.coins  || 0;
  const essence = rewards.essence || rewards.diams  || 0;
  const ready   = QQ_isReady(q);

  const typeLabels = { daily: "Quotidienne ☀️", weekly: "Hebdomadaire 📅", continuous: "Continue 🔄" };
  const typeLabel  = typeLabels[q.quest_type] || q.quest_type;

  const expiryStr  = QQ_formatExpiry(q.expires_at);
  const expiryHtml = (expiryStr && q.quest_type !== "continuous")
    ? `<div class="qdetail-expiry">⏱ Expire dans : <b>${expiryStr}</b></div>`
    : "";

  const objectivesHtml = (q.objectives || []).map(obj => {
    const cur   = obj.current || 0;
    const tgt   = obj.target || 1;
    const ratio = Math.min(cur / tgt, 1);
    const icon  = obj.resource_key
      ? `<img class="qdetail-obj-icon" src="/static/assets/img/items/resources/${obj.resource_key}.png" alt="" onerror="this.style.display='none'">`
      : (obj.item_key
        ? `<img class="qdetail-obj-icon" src="/static/assets/img/items/resources/${obj.item_key}.png" alt="" onerror="this.style.display='none'">`
        : "");
    const kindLabel = obj.kind === "collect_resource" ? "Récolter"
      : obj.kind === "craft_item" ? "Crafter"
      : obj.kind === "unlock_land" ? "Débloquer"
      : obj.kind;
    const resourceName = obj.resource_key || obj.item_key || "?";

    return `
      <div class="qdetail-obj">
        ${icon}
        <div class="qdetail-obj-info">
          <div class="qdetail-obj-label">${kindLabel} <b>${tgt}×</b> ${resourceName}</div>
          <div class="qdetail-obj-bar-wrap">
            <div class="qdetail-obj-bar-fill" style="width:${Math.round(ratio * 100)}%"></div>
          </div>
          <div class="qdetail-obj-progress">${cur} / ${tgt}</div>
        </div>
      </div>`;
  }).join("");

  const xp = rewards.xp || 0;

  const rewardsHtml = `
    <div class="qdetail-rewards">
      ${shards  ? `<span class="qdetail-reward-pill"><img src="/static/assets/img/ui/shards.png" alt=""> +${shards}</span>` : ""}
      ${essence ? `<span class="qdetail-reward-pill essence"><img src="/static/assets/img/ui/essence.png" alt=""> +${essence}</span>` : ""}
      ${xp      ? `<span class="qdetail-reward-pill xp">⭐ +${xp} XP</span>` : ""}
    </div>`;

  const claimBtn = ready
    ? `<button class="qdetail-claim-btn" id="qdetail-claim" data-quest-id="${q.id}">✔ Valider la quête</button>`
    : "";

  content.innerHTML = `
    <div class="qdetail-type-badge ${q.quest_type}">${typeLabel}</div>
    <h3 class="qdetail-title">${QQ_title(q)}</h3>
    <p class="qdetail-desc">${QQ_desc(q)}</p>
    <div class="qdetail-section-label">Objectifs</div>
    <div class="qdetail-objectives">${objectivesHtml}</div>
    <div class="qdetail-section-label">Récompenses</div>
    ${rewardsHtml}
    ${expiryHtml}
    ${claimBtn}
  `;

  modal.classList.add("is-open");
}

function QQ_closeDetail() {
  const modal = document.getElementById("quest-detail-modal");
  if (modal) modal.classList.remove("is-open");
  QQ_detailQuestId = null;
}

// ---------------------------------------------------------------------------
// Completion popup
// ---------------------------------------------------------------------------
function QQ_showCompletionPopup(quest) {
  const popup   = document.getElementById("quest-complete-popup");
  const nameEl  = document.getElementById("qcp-name");
  const rwEl    = document.getElementById("qcp-rewards");
  if (!popup || !nameEl || !rwEl) return;

  const rewards = quest.rewards || {};
  const shards  = rewards.shards  || rewards.coins  || 0;
  const essence = rewards.essence || rewards.diams  || 0;
  const xp      = rewards.xp || 0;

  nameEl.textContent = QQ_title(quest);

  rwEl.innerHTML = `
    ${shards  ? `<div class="qcp-reward-item"><img src="/static/assets/img/ui/shards.png" alt=""> <span>+${shards}</span></div>` : ""}
    ${essence ? `<div class="qcp-reward-item"><img src="/static/assets/img/ui/essence.png" alt=""> <span>+${essence}</span></div>` : ""}
    ${xp      ? `<div class="qcp-reward-item qcp-xp"><span class="qcp-xp-icon">⭐</span> <span>+${xp} XP</span></div>` : ""}
  `;

  popup.classList.add("is-open");
}

function QQ_hideCompletionPopup() {
  const popup = document.getElementById("quest-complete-popup");
  if (popup) popup.classList.remove("is-open");
}

// ---------------------------------------------------------------------------
// Claim quest
// ---------------------------------------------------------------------------
async function QQ_claimQuest(questId) {
  const btn = document.getElementById("qdetail-claim");
  if (btn) { btn.disabled = true; btn.textContent = "…"; }

  const r = await http("POST", "/api/quests/claim", { quest_id: questId });

  if (!r.ok) {
    const err = (r.data && r.data.error) || "unknown";
    if (btn) { btn.disabled = false; btn.textContent = "✔ Valider la quête"; }
    alert(
      err === "quest_not_ready" ? "Les objectifs ne sont pas encore remplis." :
      err === "quest_expired"   ? "Cette quête est expirée." :
      "Impossible de valider cette quête."
    );
    return;
  }

  const data  = r.data || {};
  const quest = data.quest || null;

  // Update player HUD
  if (data.player) {
    QQ_updateHud(data.player);
    if (typeof renderPlayer === "function") renderPlayer(data.player);
  }

  // Close detail modal first
  QQ_closeDetail();

  // Remove or update the quest in state, add new_quest if any
  if (quest) {
    // Remove completed quest from all lists
    ["daily", "weekly", "continuous"].forEach(type => {
      QQ_quests[type] = QQ_quests[type].filter(q => q.id !== quest.id);
    });

    // If a new continuous quest was assigned, add it (dedup by id)
    if (data.new_quest) {
      QQ_quests.continuous = [
        ...QQ_quests.continuous.filter(q => q.id !== data.new_quest.id),
        data.new_quest,
      ];
    }
  }

  QQ_renderGrid(QQ_activeTab);
  QQ_updateBadges();

  // Show completion popup
  if (quest) QQ_showCompletionPopup(quest);

  // Trigger level-up modal if applicable
  if (data.level_up && typeof showLevelUpModal === "function") {
    setTimeout(() => showLevelUpModal(data.new_level, data.level_rewards || []), 800);
  }
}

// ---------------------------------------------------------------------------
// Load quests
// ---------------------------------------------------------------------------
async function QQ_load() {
  ["daily", "weekly", "continuous"].forEach(type => {
    const g = document.getElementById(`grid-${type}`);
    if (g) g.innerHTML = `<p class="quests-loading">Chargement…</p>`;
  });

  const r = await http("GET", "/api/quests");

  if (!r.ok) {
    const grid = document.getElementById("grid-daily");
    if (grid) grid.innerHTML = `<p class="quests-error">Impossible de charger les quêtes.</p>`;
    return;
  }

  const data = r.data || {};

  // Level-locked: quests not yet available
  if (data.locked) {
    QQ_locked = true;
    const msg = `<p class="quests-locked">🔒 Les quêtes sont disponibles à partir du niveau ${data.min_level}.</p>`;
    ["daily", "weekly", "continuous"].forEach(type => {
      const g = document.getElementById(`grid-${type}`);
      if (g) g.innerHTML = msg;
    });
    return;
  }

  QQ_locked = false;
  QQ_quests.daily      = data.daily      || [];
  QQ_quests.weekly     = data.weekly     || [];
  QQ_quests.continuous = data.continuous || [];

  ["daily", "weekly", "continuous"].forEach(QQ_renderGrid);
  QQ_updateBadges();
}

// ---------------------------------------------------------------------------
// HUD update
// ---------------------------------------------------------------------------
function QQ_updateHud(player) {
  const map = {
    "hud-shards": player.shards, "hud-shards-value": player.shards,
    "hud-essence": player.essence, "hud-essence-value": player.essence,
  };
  Object.entries(map).forEach(([id, val]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  });

  // Update full XP/level HUD if available
  if (typeof updatePlayerHUD === "function") {
    updatePlayerHUD({
      level:   player.level,
      xp:      player.xp,
      xp_next: player.next_xp ?? player.xp_next ?? null,
      shards:  player.shards,
      essence: player.essence,
    });
  }
}

// ---------------------------------------------------------------------------
// Panel open / close
// ---------------------------------------------------------------------------
let QQ_initialized = false;

window.QQ_openPanel = function () {
  const panel = document.getElementById("quests-panel");
  if (!panel) return;
  panel.classList.remove("hidden");
  // Charge les quêtes à chaque ouverture (données fraîches)
  QQ_load();
};

window.QQ_closePanel = function () {
  const panel = document.getElementById("quests-panel");
  if (panel) panel.classList.add("hidden");
  QQ_closeDetail();
  QQ_hideCompletionPopup();
};

// ---------------------------------------------------------------------------
// Init — event listeners (appelé une seule fois au démarrage)
// ---------------------------------------------------------------------------
window.initQuestsUI = function () {
  if (QQ_initialized) return;
  QQ_initialized = true;

  // Tabs
  document.querySelectorAll(".qtab").forEach(btn => {
    btn.addEventListener("click", () => {
      QQ_activeTab = btn.dataset.tab;
      document.querySelectorAll(".qtab").forEach(b => b.classList.toggle("is-active", b === btn));
      document.querySelectorAll(".quests-tab-panel").forEach(p => p.classList.toggle("is-active", p.id === `panel-${QQ_activeTab}`));
    });
  });

  // Card click → detail modal
  document.addEventListener("click", e => {
    const card = e.target.closest(".qcard");
    if (card) {
      QQ_openDetail(parseInt(card.dataset.questId, 10));
      return;
    }

    // Claim button inside detail modal
    const claimBtn = e.target.closest("#qdetail-claim");
    if (claimBtn) {
      QQ_claimQuest(parseInt(claimBtn.dataset.questId, 10));
      return;
    }

    // Close detail modal
    if (e.target.id === "quest-modal-backdrop" || e.target.id === "quest-modal-close") {
      QQ_closeDetail();
      return;
    }

    // Close completion popup
    if (e.target.id === "qcp-ok") {
      QQ_hideCompletionPopup();
    }

    // Close quest panel via backdrop
    if (e.target.id === "quests-panel-backdrop") {
      window.QQ_closePanel();
    }
  });

  // ESC closes modals
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      QQ_closeDetail();
      QQ_hideCompletionPopup();
      window.QQ_closePanel();
    }
  });
};
