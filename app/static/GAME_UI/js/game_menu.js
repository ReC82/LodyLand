// ---------------------------------------------------------------------------
// Game menu (profil / lands / shop / quests / logout)
// ---------------------------------------------------------------------------

function setupGameMenu() {
  const btn = document.getElementById("hud-menu-btn");
  const menu = document.getElementById("game-menu");

  if (!btn || !menu) return;

  // Toggle open/close on button click
  btn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    menu.classList.toggle("is-open");
  });

  // Close when clicking outside
  document.addEventListener("click", (ev) => {
    if (!menu.classList.contains("is-open")) return;
    const target = ev.target;
    if (target === btn || menu.contains(target)) return;
    menu.classList.remove("is-open");
  });

  // Handle actions
  menu.addEventListener("click", (ev) => {
    const item = ev.target.closest(".game-menu-item");
    if (!item) return;

    const action = item.dataset.action;
    menu.classList.remove("is-open");

    switch (action) {
      case "lands":
        // Pour l'instant on renvoie simplement vers la forêt.
        // Plus tard : page de sélection de land.
        window.location.href = "/land/forest";
        break;
      case "logout":
        window.location.href = "/logout";
        break;
      case "profile":
      case "shop":
      case "quests":
      default:
        // TODO: pages dédiées à venir
        console.log("[GameMenu] Action not implemented:", action);
        break;
    }
  });
}
