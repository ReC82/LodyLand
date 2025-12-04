// static/GAME_UI/js/village/village_quests.js
// ============================================================
// VILLAGE QUESTS PAGE BOOTSTRAP
// ------------------------------------------------------------
// - Utilise quests_app.js (QQ_loadQuestsFromState, QQ_renderQuestsPanel,
//   initQuestsUI, etc.)
// - Ne fait que l'initialisation spécifique à la page /village/quests
// ============================================================

/* global QQ_loadQuestsFromState, initQuestsUI */

document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("quests-list");
  if (!container) {
    console.warn("[village_quests] #quests-list not found, skip init.");
    return;
  }

  console.log("[village_quests] init on /village/quests");

  // 1) Charger les quêtes depuis /api/state
  if (typeof QQ_loadQuestsFromState === "function") {
    QQ_loadQuestsFromState();
  } else {
    console.warn("[village_quests] QQ_loadQuestsFromState not found");
  }

  // 2) Initialiser les listeners (boutons filtres, etc.)
  if (typeof initQuestsUI === "function") {
    initQuestsUI();
  } else {
    console.warn("[village_quests] initQuestsUI not found");
  }
});
