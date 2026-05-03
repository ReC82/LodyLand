// static/GAME_UI/js/notifications_app.js
// Rich notification toast system for LodyLand.
// Usage: window.showGameNotification({ type, icon, title, body, chips, duration })

(function (window) {
  "use strict";

  // ---------------------------------------------------------------------------
  // Labels for feature unlocks
  // ---------------------------------------------------------------------------
  const FEATURE_LABELS = {
    notebook:        "📘 Carnet de notes",
    hud_currencies:  "💰 Monnaies dans le HUD",
    daily_chest:     "🎁 Coffre journalier",
    resource_market: "🏪 Marché aux ressources",
    global_shop:     "🛒 Boutique de cartes",
    quest_system:    "📜 Système de quêtes",
    travel_system:   "🗺️ Voyage entre les lieux",
    craft_system:    "⚙️ Artisanat",
    card_system:     "🎴 Cartes",
    temple_system:   "🏛️ Temple",
    minigame_system: "🎮 Mini-jeux",
    skills_system:   "⚡ Compétences",
  };

  // ---------------------------------------------------------------------------
  // Container
  // ---------------------------------------------------------------------------
  function _getContainer() {
    let c = document.getElementById("game-notifications");
    if (!c) {
      c = document.createElement("div");
      c.id = "game-notifications";
      document.body.appendChild(c);
    }
    return c;
  }

  // ---------------------------------------------------------------------------
  // Core: showGameNotification
  // opts: { type, icon, title, body, chips, duration }
  //   type: "level_up" | "unlock" | "first_resource" | "daily" | "quest" | "info"
  //   icon: URL string (img) or emoji
  //   title: string
  //   body: string (optional)
  //   chips: [{ icon, label }] — small reward pills (optional)
  //   duration: ms (default 5500)
  // ---------------------------------------------------------------------------
  function showGameNotification(opts) {
    if (!opts || !opts.title) return;

    const ts = _persistNotif(opts);
    // Update badge & refresh panel if open
    _updateBadge();
    if (_isPanelOpen()) _renderPanel();

    const type     = opts.type     || "info";
    const duration = opts.duration ?? 5500;
    const container = _getContainer();

    // Icon HTML
    let iconHtml = "";
    if (opts.icon) {
      if (opts.icon.startsWith("/") || opts.icon.startsWith("http")) {
        iconHtml = `<img class="game-notif-icon" src="${opts.icon}" alt="">`;
      } else {
        iconHtml = `<span class="game-notif-icon-emoji">${opts.icon}</span>`;
      }
    }

    // Chips HTML (small pills for rewards)
    let chipsHtml = "";
    if (Array.isArray(opts.chips) && opts.chips.length) {
      const chipItems = opts.chips.map((c) => {
        const img = c.icon
          ? `<img src="${c.icon}" alt="">`
          : "";
        return `<span class="game-notif-chip">${img}${_esc(c.label)}</span>`;
      }).join("");
      chipsHtml = `<div class="game-notif-chips">${chipItems}</div>`;
    }

    const notif = document.createElement("div");
    notif.className = `game-notif game-notif--${type}`;

    notif.innerHTML = `
      <div class="game-notif-inner${opts.url ? " game-notif-inner--clickable" : ""}">
        ${iconHtml}
        <div class="game-notif-content">
          <div class="game-notif-title">${_esc(opts.title)}</div>
          ${opts.body ? `<div class="game-notif-body">${_esc(opts.body)}</div>` : ""}
          ${chipsHtml}
        </div>
        <button class="game-notif-close" aria-label="Fermer" title="Fermer">✕</button>
      </div>
      <div class="game-notif-bar-wrap">
        <div class="game-notif-bar"></div>
      </div>
    `;

    container.appendChild(notif);

    // Close button
    notif.querySelector(".game-notif-close")?.addEventListener("click", (e) => {
      e.stopPropagation();
      _dismiss(notif);
    });

    // Click on body → remove all notifs for this url + navigate
    if (opts.url) {
      notif.querySelector(".game-notif-inner")?.addEventListener("click", () => {
        _dismiss(notif);
        _removeFromHistoryByUrl(opts.url);
        _updateBadge();
        window.location.href = opts.url;
      });
    }

    // Animate in (double rAF to allow CSS to register initial state first)
    requestAnimationFrame(() => requestAnimationFrame(() => {
      notif.classList.add("game-notif--visible");

      // Animate progress bar from 100% → 0%
      const bar = notif.querySelector(".game-notif-bar");
      if (bar) {
        bar.style.transition = `width ${duration}ms linear`;
        bar.style.width = "0%";
      }
    }));

    // Auto-dismiss
    const timer = setTimeout(() => _dismiss(notif), duration);
    notif._timer = timer;

    return notif;
  }

  function _dismiss(notif) {
    clearTimeout(notif._timer);
    notif.classList.remove("game-notif--visible");
    notif.classList.add("game-notif--leaving");
    setTimeout(() => notif.remove(), 300);
  }

  // ---------------------------------------------------------------------------
  // High-level helpers called from game logic
  // ---------------------------------------------------------------------------

  /**
   * Level-up notification.
   * @param {number} level — new level
   * @param {Array}  rewards — level rewards array
   * @param {Array}  unlocks — system_unlocks array from LEVEL_DEFS
   */
  // i18n helper — uses I18n.t if loaded, falls back to key
  function _t(key, fallback) {
    if (typeof window.I18n !== "undefined") {
      const v = window.I18n.t(key);
      return (v && v !== key) ? v : (fallback || key);
    }
    return fallback || key;
  }

  // Translate a label that may be an i18n key (e.g. "items.branch.label")
  function _label(raw) {
    if (!raw) return raw;
    if (/^[\w.]+$/.test(raw) && raw.includes(".")) {
      const v = _t(raw, null);
      if (v && v !== raw) return v;
    }
    return raw;
  }

  function notifyLevelUp(level, rewards, unlocks) {
    const chips = [];

    (rewards || []).forEach((r) => {
      if (r.type === "shards" || r.type === "coins") {
        chips.push({ icon: "/static/assets/img/ui/coins.png", label: `+${r.amount} ${_t("notif.shards", "Éclats")}` });
      } else if (r.type === "essence" || r.type === "diams") {
        chips.push({ icon: "/static/assets/img/ui/diams.png", label: `+${r.amount} ${_t("notif.essence", "Essence")}` });
      } else if (r.type === "card") {
        chips.push({ icon: r.icon || null, label: _label(r.label) || r.card_key || _t("notif.card", "Carte") });
      } else if (r.type === "currency") {
        const isPrimary = r.currency === "primary";
        chips.push({
          icon: isPrimary ? "/static/assets/img/ui/coins.png" : "/static/assets/img/ui/diams.png",
          label: `+${r.amount} ${isPrimary ? _t("notif.shards", "Éclats") : _t("notif.essence", "Essence")}`,
        });
      }
    });

    showGameNotification({
      type: "level_up",
      icon: "⭐",
      title: _t("notif.level_up.title", "Niveau {level} atteint !").replace("{level}", level),
      body: chips.length ? _t("notif.level_up.rewards", "Récompenses reçues :") : _t("notif.level_up.keep_going", "Continue comme ça !"),
      chips,
      duration: 7000,
    });

    if (Array.isArray(unlocks) && unlocks.length) {
      const unlockLabels = unlocks.map((u) => FEATURE_LABELS[u.key] || u.key).filter(Boolean);
      if (unlockLabels.length) {
        setTimeout(() => {
          showGameNotification({
            type: "unlock",
            icon: "🔓",
            title: _t("notif.unlock.title", "Nouveau déblocage !"),
            body: unlockLabels.join(" · "),
            duration: 8000,
          });
        }, 600);
      }
    }
  }

  function notifyFirstResource(resourceKey, label, icon, qty) {
    showGameNotification({
      type: "first_resource",
      icon: icon || "/static/assets/img/ui/xp.png",
      title: _t("notif.first_resource.title", "Nouvelle ressource découverte !"),
      body: `${_label(label) || resourceKey} (×${qty})`,
      duration: 5000,
    });
  }

  function notifyDailyChest(rewards, streak) {
    const chips = [];
    (rewards || []).forEach((r) => {
      if (r.type === "shards" || r.type === "coins") {
        chips.push({ icon: "/static/assets/img/ui/coins.png", label: `+${r.amount}` });
      } else if (r.type === "essence" || r.type === "diams") {
        chips.push({ icon: "/static/assets/img/ui/diams.png", label: `+${r.amount}` });
      } else if (r.type === "xp") {
        chips.push({ icon: "/static/assets/img/ui/xp.png", label: `+${r.amount} XP` });
      } else if (r.type === "card") {
        chips.push({ icon: null, label: _label(r.label) || _t("notif.card", "Carte") });
      }
    });

    showGameNotification({
      type: "daily",
      icon: "🎁",
      title: _t("notif.daily.title", "Coffre journalier ouvert !"),
      body: streak > 1
        ? _t("notif.daily.streak", "Série : {streak} jours consécutifs 🔥").replace("{streak}", streak)
        : _t("notif.daily.first", "À demain pour continuer !"),
      chips,
      duration: 6000,
    });
  }

  function notifyQuestComplete(questTitle) {
    showGameNotification({
      type: "quest",
      icon: "📜",
      title: _t("notif.quest.title", "Quête accomplie !"),
      body: questTitle,
      duration: 5000,
    });
  }

  // ---------------------------------------------------------------------------
  // Notification history (localStorage, capped at 150 entries)
  // ---------------------------------------------------------------------------
  const HISTORY_KEY    = "llNotifHistory";
  const LAST_SEEN_KEY  = "llNotifLastSeen";   // ISO timestamp: last panel open
  const HISTORY_MAX    = 150;
  const PANEL_MAX_ROWS = 20;

  function _removeFromHistory(ts) {
    try {
      const history = _getHistory().filter(n => n.ts !== ts);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    } catch (_) {}
  }

  function _removeFromHistoryByUrl(url) {
    if (!url) return;
    try {
      const history = _getHistory().filter(n => n.url !== url);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    } catch (_) {}
  }

  function _persistNotif(opts) {
    const ts = new Date().toISOString();
    try {
      const entry = {
        type:  opts.type  || "info",
        icon:  opts.icon  || null,
        title: opts.title || "",
        body:  opts.body  || "",
        url:   opts.url   || null,
        ts,
      };
      let history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      // If the most recent entry has the same url, replace it (no duplicate land notifs)
      if (entry.url && history.length > 0 && history[0].url === entry.url) {
        history[0] = entry;
      } else {
        history.unshift(entry);
        if (history.length > HISTORY_MAX) history.length = HISTORY_MAX;
      }
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    } catch (_) {
      // localStorage may be unavailable (private mode, quota)
    }
    return ts;
  }

  // ---------------------------------------------------------------------------
  // HUD notification panel
  // ---------------------------------------------------------------------------

  const TYPE_EMOJI = {
    level_up:       "⭐",
    unlock:         "🔓",
    first_resource: "🌿",
    daily:          "🎁",
    quest:          "📜",
    info:           "ℹ️",
  };

  function _relTime(iso) {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    const h = Math.floor(diff / 3600000);
    const d = Math.floor(diff / 86400000);
    if (m < 1)  return "À l'instant";
    if (m < 60) return `${m} min`;
    if (h < 24) return `${h}h`;
    return `${d}j`;
  }

  function _getLastSeen() {
    try { return localStorage.getItem(LAST_SEEN_KEY) || ""; } catch (_) { return ""; }
  }
  function _setLastSeen() {
    try { localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString()); } catch (_) {}
  }

  function _getUnreadCount() {
    const lastSeen = _getLastSeen();
    if (!lastSeen) return Math.min(_getHistory().length, 9);
    return _getHistory().filter(n => n.ts > lastSeen).length;
  }

  function _getHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); } catch (_) { return []; }
  }

  function _updateBadge() {
    const badge = document.getElementById("hud-notif-badge");
    if (!badge) return;
    const count = _getUnreadCount();
    if (count > 0) {
      badge.textContent = count > 9 ? "9+" : String(count);
      badge.style.display = "block";
    } else {
      badge.style.display = "none";
    }
  }

  function _renderPanel() {
    const list    = document.getElementById("hud-notif-list");
    const empty   = document.getElementById("hud-notif-empty");
    if (!list) return;

    const history  = _getHistory().slice(0, PANEL_MAX_ROWS);
    const lastSeen = _getLastSeen();

    if (!history.length) {
      list.innerHTML = "";
      if (empty) empty.style.display = "";
      return;
    }
    if (empty) empty.style.display = "none";

    list.innerHTML = history.map(n => {
      const icon    = TYPE_EMOJI[n.type] || "ℹ️";
      const time    = _relTime(n.ts);
      const unread  = lastSeen && n.ts > lastSeen;
      const clickable = n.url ? " hud-notif-row--clickable" : "";
      const dataUrl   = n.url ? ` data-url="${_escAttr(n.url)}"` : "";
      return `
        <div class="hud-notif-row${unread ? " is-unread" : ""}${clickable}" data-type="${_escAttr(n.type)}" data-ts="${_escAttr(n.ts)}"${dataUrl}>
          <div class="hud-notif-row-icon">${icon}</div>
          <div class="hud-notif-row-content">
            <div class="hud-notif-row-title">${_esc(n.title)}</div>
            ${n.body ? `<div class="hud-notif-row-body">${_esc(n.body)}</div>` : ""}
          </div>
          <div class="hud-notif-row-time">${time}</div>
        </div>`;
    }).join("");

    // Navigate on click for rows that have a url — removes all notifs for that url
    list.querySelectorAll(".hud-notif-row--clickable").forEach(row => {
      row.addEventListener("click", () => {
        _removeFromHistoryByUrl(row.dataset.url);
        _closePanel();
        window.location.href = row.dataset.url;
      });
    });
  }

  function _openPanel() {
    const panel = document.getElementById("hud-notif-panel");
    const btn   = document.getElementById("hud-notif-btn");
    if (!panel) return;
    _renderPanel();
    panel.hidden = false;
    if (btn) btn.setAttribute("aria-expanded", "true");
    // Mark all as read
    _setLastSeen();
    _updateBadge();
  }

  function _closePanel() {
    const panel = document.getElementById("hud-notif-panel");
    const btn   = document.getElementById("hud-notif-btn");
    if (panel) panel.hidden = true;
    if (btn)   btn.setAttribute("aria-expanded", "false");
  }

  function _isPanelOpen() {
    const p = document.getElementById("hud-notif-panel");
    return p && !p.hidden;
  }

  // Wire up DOM once ready
  document.addEventListener("DOMContentLoaded", () => {
    const btn   = document.getElementById("hud-notif-btn");
    const clear = document.getElementById("hud-notif-clear");

    if (btn) {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        _isPanelOpen() ? _closePanel() : _openPanel();
      });
    }

    if (clear) {
      clear.addEventListener("click", (e) => {
        e.stopPropagation();
        try { localStorage.removeItem(HISTORY_KEY); } catch (_) {}
        _setLastSeen();
        _updateBadge();
        _renderPanel();
      });
    }

    // Click outside closes panel
    document.addEventListener("click", (e) => {
      const wrap = document.getElementById("hud-notif-wrap");
      if (wrap && !wrap.contains(e.target)) _closePanel();
    });

    // Initial badge
    _updateBadge();
  });

  // ---------------------------------------------------------------------------
  // Utils
  // ---------------------------------------------------------------------------
  function _esc(str) {
    if (!str) return "";
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function _escAttr(str) {
    if (!str) return "";
    return String(str).replace(/['"<>&]/g, c => ({"'":"&#39;",'"':"&quot;","<":"&lt;",">":"&gt;","&":"&amp;"}[c]));
  }

  // ---------------------------------------------------------------------------
  // Expose
  // ---------------------------------------------------------------------------
  window.GameNotif = {
    show: showGameNotification,
    levelUp: notifyLevelUp,
    firstResource: notifyFirstResource,
    dailyChest: notifyDailyChest,
    questComplete: notifyQuestComplete,
    FEATURE_LABELS,
    HISTORY_KEY,
    getHistory: _getHistory,
    clearHistory: () => {
      try { localStorage.removeItem(HISTORY_KEY); } catch (_) {}
      _setLastSeen();
      _updateBadge();
      if (_isPanelOpen()) _renderPanel();
    },
  };

})(window);
