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
      case "logout":
        window.location.href = "/logout";
        break;
      case "profile":
      case "shop":
        window.location.href = "/shop";
        break;
      case "inventory":
        window.location.href = "/inventory";
      break;
      default:
        // TODO: dedicated pages to come
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

  if (!icon || !tooltip) {
    return;
  }

  icon.classList.add("is-busy");
  tooltip.textContent = "Ouverture du coffre...";

  try {
    const r = await http("POST", "/api/daily");

    if (r.ok) {
      const d = r.data || {};

      const reward = d.reward ?? d.coins_awarded ?? 0;
      const streak = d.streak || {};
      const cur = streak.current ?? "?";
      const best = streak.best ?? "?";

    // 👉 affiche le modal animé
    showDailyModal(reward, streak);

      tooltip.innerHTML =
        `Coffre ouvert 🎁<br>` +
        `+${reward} coins<br>` +
        `<small>Streak: ${cur} (meilleur: ${best})</small>`;

      // Mise à jour HUD player si le backend renvoie un player
      if (d.player) {
        const p = d.player;
        currentPlayer = {
          ...p,
          next_xp: p.next_xp ?? p.nextXp ?? null,
        };
        renderPlayer(currentPlayer);
      } else {
        // fallback : /api/me
        const meRes = await http("GET", "/api/me");
        if (meRes.ok) {
          const p = meRes.data;
          currentPlayer = {
            ...p,
            next_xp: p.next_xp ?? p.nextXp ?? null,
          };
          renderPlayer(currentPlayer);
        }
      }

      // Mise à jour du badge / tooltip
      await refreshDailyStatus();
    } else {
      const err = r.data || {};
      const msg = err.error || "daily_failed";

      if (r.status === 409 && err.next_at) {
        const formatted = formatIso(err.next_at);
        tooltip.innerHTML =
          "Déjà ouvert aujourd'hui.<br>" +
          `<small>Prochain coffre: <br>${formatted}</small>`;
      } else {
        tooltip.textContent =
          `Impossible d'ouvrir le coffre (${r.status}) : ${msg}`;
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
    // Daily not ready on error
    setDailyChestReady(false);
    return;
  }

  const d = r.data || {};

  // ✅ Ici on active / désactive animation + badge "!"
  setDailyChestReady(!!d.eligible);

  // Contenu de l'infobulle
  let html = "";

  if (d.eligible) {
    html += `<div><b>Coffre disponible</b> 🎁</div>`;
    html += `<div>Récompense : quelques coins</div>`;
  } else {
    html += `<div><b>Déjà ouvert aujourd'hui</b></div>`;
  }

  html += `<hr style="opacity:0.2;">`;
  html += `<div>Streak actuel : <b>${d.streak?.current ?? 0}</b></div>`;
  html += `<div>Meilleur streak : <b>${d.streak?.best ?? 0}</b></div>`;

    if (!d.eligible && d.next_reset) {
      const formatted = formatIso(d.next_reset);
      html += `<div style="margin-top:4px;">Prochain coffre :<br><b>${formatted}</b></div>`;
    }

  tooltip.innerHTML = html;
}


// ------------------------------
// Daily modal helpers
// ------------------------------

function showDailyModal(reward, streak) {
  const modal = $("dailyModal");
  if (!modal) return;

  const rewardEl = $("dailyModalReward");
  const streakCurEl = $("dailyModalStreakCurrent");
  const streakBestEl = $("dailyModalStreakBest");

  if (rewardEl) rewardEl.textContent = reward ?? 0;
  if (streakCurEl) streakCurEl.textContent = streak?.current ?? 0;
  if (streakBestEl) streakBestEl.textContent = streak?.best ?? 0;

  modal.classList.add("is-open");
}

function setupDailyModal() {
  const modal = $("dailyModal");
  if (!modal) return;

  const closeBtn = $("dailyModalClose");
  const backdrop = modal.querySelector(".daily-modal-backdrop");

  const close = () => {
    modal.classList.remove("is-open");
  };

  if (closeBtn) {
    closeBtn.addEventListener("click", close);
  }
  if (backdrop) {
    backdrop.addEventListener("click", close);
  }

  // fermer avec ESC
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("is-open")) {
      close();
    }
  });
}
