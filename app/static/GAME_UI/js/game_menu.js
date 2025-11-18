// ---------------------------------------------------------------------------
// Game menu (profil / lands / shop / quests / logout)
// ---------------------------------------------------------------------------

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
      case "quests":
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
        tooltip.innerHTML =
          "Déjà ouvert aujourd'hui.<br>" +
          `<small>Prochain coffre: ${err.next_at}</small>`;
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


async function refreshDailyStatus() {
  const alert = $("dailyAlert");
  const tooltip = $("dailyTooltip");

  if (!alert || !tooltip) return;

  const r = await http("GET", "/api/daily/status");

  if (!r.ok) {
    tooltip.textContent = "Impossible de récupérer le statut du coffre.";
    alert.style.display = "none";
    return;
  }

  const d = r.data || {};

  // Badge "!"
  alert.style.display = d.eligible ? "flex" : "none";

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
    html += `<div style="margin-top:4px;">Prochain coffre :<br><b>${d.next_reset}</b></div>`;
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
