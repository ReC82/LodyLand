// static/GAME_UI/js/village/village_common.js
// ============================================================
// VILLAGE COMMON — Helpers partagés (HUD + level-up + story)
// ------------------------------------------------------------
// Utilise les globals de game_app.js :
//   - window.currentPlayer
//   - renderPlayer(...)
//   - showLevelUpModal(level, rewards)
//   - handleStoryAfterLevelUp(oldLevel, newLevel)
// ============================================================

(function (window) {
  "use strict";

  /**
   * Traite la partie "player / level-up / story" d'une réponse backend.
   *
   * Convention côté backend :
   *  - data.player        : état complet du joueur après l'action
   *  - data.level_up      : bool (true si passage de niveau)
   *  - data.level_rewards : liste des rewards de niveau (optionnel)
   */
  function handlePlayerAndLevelFromResponse(data) {
    if (!data || !data.player) {
      return;
    }

    // Niveau avant mise à jour
    const oldLevel =
      window.currentPlayer ? Number(window.currentPlayer.level || 0) : 0;

    // Normalisation du player pour le HUD (next_xp / nextXp)
    const newPlayer = {
      ...data.player,
      next_xp: data.player.next_xp ?? data.player.nextXp ?? null,
    };

    // Met à jour currentPlayer + HUD via renderPlayer (game_app.js)
    if (typeof window.renderPlayer === "function") {
      window.renderPlayer(newPlayer);
    } else {
      // fallback minimal
      window.currentPlayer = newPlayer;
    }

    const newLevel = Number(newPlayer.level || 0);

    // Gestion du level-up (modal + story queue)
    if (data.level_up && typeof window.showLevelUpModal === "function") {
      const rewards = data.level_rewards || [];

      // Affiche le modal de level up
      window.showLevelUpModal(newLevel, rewards);

      // Enfile les story_events liés aux niveaux gagnés
      if (
        typeof window.handleStoryAfterLevelUp === "function" &&
        newLevel > oldLevel
      ) {
        window.handleStoryAfterLevelUp(oldLevel, newLevel);
      }
    }
  }

  // Expose pour les scripts du village
  window.VillageCommon = {
    handlePlayerAndLevelFromResponse,
  };
})(window);
