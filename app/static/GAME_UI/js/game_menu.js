// ---------------------------------------------------------------------------
// Game menu (profil / lands / shop / quests / logout)
// ---------------------------------------------------------------------------

// Format ISO string -> DD/MM/YYYY à HH:MM
function formatIso(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);

  // Format FR
  const day = String(d.getDate()).padStart(2, "0");
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const year = d.getFullYear();

  const hours = String(d.getHours()).padStart(2, "0");
  const minutes = String(d.getMinutes()).padStart(2, "0");

  return `${day}/${month}/${year} à ${hours}:${minutes}`;
}



function setupGameMenu() {
  const btn = document.getElementById("hud-menu-btn");
  const menu = document.getElementById("game-menu");
  const closeBtn = document.getElementById("game-menu-close");

  if (!btn || !menu) return;

  // Toggle open/close on button click
  btn.addEventListener("click", (ev) => {
    // Prevent click from bubbling to document
    ev.stopPropagation();
    menu.classList.toggle("is-open");
  });

  // Close when clicking on the "X" button
  if (closeBtn) {
    closeBtn.addEventListener("click", (ev) => {
      // Prevent click from bubbling to document
      ev.stopPropagation();
      menu.classList.remove("is-open");
    });
  }

  // Close when clicking outside the menu element (if overlay does not cover full screen)
  document.addEventListener("click", (ev) => {
    if (!menu.classList.contains("is-open")) return;

    const target = ev.target;

    // Do not close if click on the toggle button or inside the menu overlay
    if (target === btn || menu.contains(target)) return;

    menu.classList.remove("is-open");
  });

  // Handle clicks inside the overlay:
  // - click on backdrop (outside .game-menu-card) => close
  // - click on .game-menu-item => run action
  menu.addEventListener("click", (ev) => {
    const card = ev.target.closest(".game-menu-card");

    // If there is NO game-menu-card under the click, it means we clicked on the backdrop
    if (!card) {
      // Click on dark background => close menu
      menu.classList.remove("is-open");
      return;
    }

    const item = ev.target.closest(".game-menu-item");
    if (!item) {
      // Click inside the card but not on an item => do nothing
      return;
    }

    const action = item.dataset.action;
    menu.classList.remove("is-open");

    switch (action) {
      case "lands":
        window.location.href = "/lands";
        break;

      case "inventory":
        window.location.href = "/inventory";
        break;

      case "profile":
        window.location.href = "/profile";
        break;

      case "shop":
        window.location.href = "/shop";
        break;

      case "support":
        if (typeof window.openSupportModal === "function") window.openSupportModal();
        break;

      case "logout":
        window.location.href = "/logout";
        break;

      default:
        console.log("[GameMenu] Action not implemented:", action);
        break;
    }

  });
}

// Daily Chest logic for GAME_UI
// Requires helpers from common.js: http(), $(), and currentPlayer/renderPlayer

async function claimDaily() {
  const icon = $("dailyIcon");
  const tooltip = $("dailyTooltip");

  if (!icon || !tooltip) return;

  icon.classList.add("is-busy");
  tooltip.textContent = "Ouverture du coffre...";

  try {
    const r = await http("POST", "/api/daily");

    if (r.ok) {
      const d = r.data || {};
      const rewards      = d.rewards      || [];
      const dayInCycle   = d.day_in_cycle || 1;
      const weekMult     = d.week_multiplier || 1;
      const streak       = d.streak || {};

      // Persist rewards so we can show them on re-open
      try {
        localStorage.setItem("daily_last_rewards", JSON.stringify({ rewards, dayInCycle, weekMult }));
      } catch (_) {}

      // Show animated modal
      showDailyModal(rewards, dayInCycle, weekMult, streak);

      // Rich notification for daily chest
      if (typeof window.GameNotif !== "undefined") {
        window.GameNotif.dailyChest(rewards, streak.current ?? 1);
      }

      // Build a short tooltip summary
      const shardsReward = rewards.filter(r => r.type === "shards").reduce((a, r) => a + r.amount, 0);
      tooltip.innerHTML =
        `Coffre ouvert 🎁<br>` +
        (shardsReward ? `+${shardsReward} éclats<br>` : "") +
        `<small>Série: ${streak.current ?? 0} (meilleur: ${streak.best ?? 0})</small>`;

      // Update HUD player
      if (d.player) {
        const p = d.player;
        currentPlayer = { ...p, next_xp: p.next_xp ?? p.nextXp ?? null };
        renderPlayer(currentPlayer);
      } else {
        const meRes = await http("GET", "/api/me");
        if (meRes.ok) {
          const p = meRes.data;
          currentPlayer = { ...p, next_xp: p.next_xp ?? p.nextXp ?? null };
          renderPlayer(currentPlayer);
        }
      }

      await refreshDailyStatus();
    } else {
      const err = r.data || {};
      if (r.status === 409 && err.already_claimed) {
        // Load last rewards from localStorage to display them
        let lastRewards = [];
        try {
          const saved = localStorage.getItem("daily_last_rewards");
          if (saved) lastRewards = JSON.parse(saved).rewards || [];
        } catch (_) {}

        showDailyModal(lastRewards, err.day_in_cycle || 1, 1, err.streak || {}, true);

        if (err.next_at) {
          const formatted = formatIso(err.next_at);
          tooltip.innerHTML =
            "Déjà ouvert aujourd'hui.<br>" +
            `<small>Prochain coffre:<br>${formatted}</small>`;
        }
      } else {
        tooltip.textContent = `Impossible d'ouvrir le coffre (${r.status}) : ${err.error || "daily_failed"}`;
      }
    }
  } catch (e) {
    console.error("daily error", e);
    tooltip.textContent = "Erreur réseau lors de l'ouverture du coffre.";
  } finally {
    icon.classList.remove("is-busy");
  }
}

function setDailyChestReady(isReady) {
  const icon = document.getElementById("dailyIcon");
  const alertBadge = document.getElementById("dailyAlert");
  if (!icon || !alertBadge) return;

  if (isReady) {
    // Add animation + badge
    icon.classList.add("hud-daily-ready");
    alertBadge.style.display = "block";
  } else {
    // Stop animation + cacher le badge
    icon.classList.remove("hud-daily-ready");
    alertBadge.style.display = "none";
  }
}


async function refreshDailyStatus() {
  const tooltip = $("dailyTooltip");
  if (!tooltip) return;

  const r = await http("GET", "/api/daily/status");

  if (!r.ok) {
    tooltip.textContent = "Impossible de récupérer le statut du coffre.";
    setDailyChestReady(false);
    return;
  }

  const d = r.data || {};
  setDailyChestReady(!!d.eligible);

  let html = "";
  if (d.eligible) {
    html += `<div><b>Coffre disponible</b> 🎁</div>`;
    const day = d.day_in_cycle || 1;
    html += `<div>Jour <b>${day}</b>/7 du cycle</div>`;
  } else {
    html += `<div><b>Déjà ouvert aujourd'hui</b></div>`;
  }

  html += `<hr style="opacity:0.2;">`;
  html += `<div>Série : <b>${d.streak?.current ?? 0}</b></div>`;
  html += `<div>Meilleure : <b>${d.streak?.best ?? 0}</b></div>`;

  if (!d.eligible && d.next_reset) {
    html += `<div style="margin-top:4px;">Prochain coffre :<br><b>${formatIso(d.next_reset)}</b></div>`;
  }

  tooltip.innerHTML = html;
}


// ------------------------------
// Daily modal helpers
// ------------------------------

const DAILY_REWARD_TYPE_LABELS = {
  shards:   "Éclats",
  essence:  "Essences",
  xp:       "XP",
  resource: "",
};

const DAILY_DAY_EMOJIS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","⭐"];

// alreadyClaimed: today's day counts as "done" (past), not "today"
function _buildDailyTimeline(dayInCycle, alreadyClaimed = false) {
  const container = $("dailyTimeline");
  if (!container) return;

  container.innerHTML = "";
  const frag = document.createDocumentFragment();

  for (let d = 1; d <= 7; d++) {
    if (d > 1) {
      const conn = document.createElement("div");
      conn.className = "daily-timeline-connector";
      frag.appendChild(conn);
    }

    const dayEl = document.createElement("div");
    dayEl.className = "daily-day";

    const isDone = alreadyClaimed ? d <= dayInCycle : d < dayInCycle;
    const isToday = !alreadyClaimed && d === dayInCycle;

    if (isDone)    dayEl.classList.add("is-past");
    if (isToday)   dayEl.classList.add("is-today");
    if (!isDone && !isToday) dayEl.classList.add("is-future");
    if (d === 7)   dayEl.classList.add("is-day7");

    const iconEl = document.createElement("div");
    iconEl.className = "daily-day-icon";
    iconEl.textContent = isDone ? "✔" : DAILY_DAY_EMOJIS[d - 1];

    const labelEl = document.createElement("div");
    labelEl.className = "daily-day-label";
    labelEl.textContent = d === 7 ? "Bonus" : `J${d}`;

    dayEl.appendChild(iconEl);
    dayEl.appendChild(labelEl);
    frag.appendChild(dayEl);
  }

  container.appendChild(frag);
}

function _buildDailyRewards(rewards, alreadyClaimed = false) {
  const container = $("dailyRewardsList");
  if (!container) return;

  container.innerHTML = "";

  if (alreadyClaimed) {
    container.classList.add("is-past-chest");
  } else {
    container.classList.remove("is-past-chest");
  }

  // If no rewards at all, hide the list silently
  if (!rewards || rewards.length === 0) return;

  const frag = document.createDocumentFragment();

  // Label hint when showing past chest
  if (alreadyClaimed) {
    const hint = document.createElement("div");
    hint.className = "daily-rewards-hint";
    hint.textContent = "Dernier coffre";
    frag.appendChild(hint);
  }

  for (const reward of rewards) {
    const item = document.createElement("div");
    item.className = "daily-reward-item";
    item.dataset.type = reward.type;

    // Icon
    if (reward.icon) {
      const img = document.createElement("img");
      img.className = "daily-reward-icon";
      img.src = reward.icon;
      img.alt = reward.label || reward.type;
      img.onerror = function() {
        // fallback emoji if image missing
        const span = document.createElement("span");
        span.className = "daily-reward-icon is-emoji";
        span.textContent = reward.type === "shards" ? "✨"
          : reward.type === "essence" ? "💜"
          : reward.type === "xp"      ? "⚡"
          : "📦";
        this.replaceWith(span);
      };
      item.appendChild(img);
    }

    // Amount + label
    const textWrap = document.createElement("div");

    const amountEl = document.createElement("div");
    amountEl.className = "daily-reward-amount";
    amountEl.textContent = `+${reward.amount}`;

    const labelEl = document.createElement("div");
    labelEl.className = "daily-reward-label";
    labelEl.textContent = DAILY_REWARD_TYPE_LABELS[reward.type] || reward.label || reward.key || reward.type;

    textWrap.appendChild(amountEl);
    textWrap.appendChild(labelEl);
    item.appendChild(textWrap);

    frag.appendChild(item);
  }

  container.appendChild(frag);
}

function showDailyModal(rewards, dayInCycle, weekMultiplier, streak, alreadyClaimed = false) {
  const modal = $("dailyModal");
  if (!modal) return;

  // Update title depending on claimed state
  const titleEl = modal.querySelector(".daily-modal-title");
  if (titleEl) {
    titleEl.textContent = alreadyClaimed
      ? "Déjà ouvert aujourd'hui"
      : (titleEl.dataset.titleOpen || titleEl.textContent);
    // Store original title on first open so we can restore it later
    if (!alreadyClaimed && !titleEl.dataset.titleOpen) {
      titleEl.dataset.titleOpen = titleEl.textContent;
    }
  }

  _buildDailyTimeline(dayInCycle || 1, alreadyClaimed);
  _buildDailyRewards(rewards || [], alreadyClaimed);

  const streakCurEl  = $("dailyModalStreakCurrent");
  const streakBestEl = $("dailyModalStreakBest");
  if (streakCurEl)  streakCurEl.textContent  = streak?.current ?? 0;
  if (streakBestEl) streakBestEl.textContent = streak?.best    ?? 0;

  modal.classList.add("is-open");
}

function setupDailyModal() {
  const modal = $("dailyModal");
  if (!modal) return;

  const closeBtn = $("dailyModalClose");
  const backdrop = modal.querySelector(".daily-modal-backdrop");

  const close = () => modal.classList.remove("is-open");

  if (closeBtn) closeBtn.addEventListener("click", close);
  if (backdrop) backdrop.addEventListener("click", close);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("is-open")) close();
  });
}
