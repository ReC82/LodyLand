// static/GAME_UI/js/village/village_quests.js
// Page dédiée aux quêtes du village (/village/quests).
// quests_app.js est déjà chargé par game_base.html.
// game_app.js appelle initQuestsUI() au DOMContentLoaded, donc les listeners
// sont déjà en place — on lance juste le chargement des données.

document.addEventListener("DOMContentLoaded", () => {
  const grid = document.getElementById("grid-daily");
  if (!grid) {
    console.warn("[village_quests] #grid-daily not found, skip init.");
    return;
  }

  console.log("[village_quests] page init — chargement des quêtes");

  // initQuestsUI() a déjà été appelé par game_app.js (flag QQ_initialized l'empêche de tourner 2x).
  // On charge les données fraîches pour les afficher dans la grille de la page.
  if (typeof QQ_load === "function") {
    QQ_load();
  } else {
    console.warn("[village_quests] QQ_load not found");
  }
});
