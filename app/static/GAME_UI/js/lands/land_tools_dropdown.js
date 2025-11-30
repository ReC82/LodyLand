/*
  File: static/GAME_UI/js/lands/land_tools_dropdown.js
  Purpose: Link the land tools dropdown UI with existing LandTools logic.
  Notes:
  - Relies on the HTML structure:
    - #land-tool-toggle (main button)
    - #land-tool-menu (dropdown menu)
    - .land-tool-btn inside the menu (one per tool)
*/

(function () {
  document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("land-tool-toggle");
    const menu = document.getElementById("land-tool-menu");
    if (!toggleBtn || !menu) return;

    const items = Array.from(menu.querySelectorAll(".land-tool-btn"));

    // Helper: update main toggle button (icon + label) from a given tool button
    function updateToggleFrom(btn) {
      if (!btn) return;

      const iconUrl = btn.getAttribute("data-icon");
      const label =
        btn.getAttribute("data-label") ||
        btn.getAttribute("data-tool") ||
        "Tool";

      const iconImg = toggleBtn.querySelector(".land-tool-toggle-icon");
      const labelSpan = toggleBtn.querySelector(
        ".land-tool-toggle-label-main"
      );

      if (iconImg && iconUrl) {
        iconImg.src = iconUrl;
        iconImg.alt = label;
      }
      if (labelSpan) {
        labelSpan.textContent = label;
      }

      toggleBtn.setAttribute("aria-expanded", "false");
    }

    // Open/close menu on toggle click
    toggleBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      const isOpen = menu.classList.contains("open");
      if (isOpen) {
        menu.classList.remove("open");
        toggleBtn.setAttribute("aria-expanded", "false");
      } else {
        menu.classList.add("open");
        toggleBtn.setAttribute("aria-expanded", "true");
      }
    });

    // Close when clicking outside
    document.addEventListener("click", function () {
      if (menu.classList.contains("open")) {
        menu.classList.remove("open");
        toggleBtn.setAttribute("aria-expanded", "false");
      }
    });

    // When selecting a tool in the menu
    items.forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();

        // LandTools in land_common.js already listens to .land-tool-btn clicks
        // and will handle active class / current tool for /api/collect.

        // Here we only update the main toggle visuals and close the menu.
        updateToggleFrom(btn);
        menu.classList.remove("open");
      });
    });

    // Init: use the currently active tool (set by LandTools or fallback to first item)
    const activeBtn =
      menu.querySelector(".land-tool-btn.active") || items[0];

    if (activeBtn) {
      updateToggleFrom(activeBtn);
    }
  });
})();
