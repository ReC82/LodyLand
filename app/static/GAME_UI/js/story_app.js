// static/GAME_UI/js/story_app.js
// UI du Story Modal (multi-pages) + intégration avec la file de stories

const STORY_AVATARS = {
  self: "/static/assets/img/ui/players/defaults/player_default_avatar.png",

  npc_villager_guide: "/static/assets/img/ui/pnj/village_guide.png",
  npc_village_chief: "/static/assets/img/ui/pnj/village_chief.png",
  npc_villager_fisher: "/static/assets/img/ui/pnj/village_fisher.png",

  // fallback
  default: "/static/assets/img/ui/players/defaults/player_default_avatar.png"
};

(function (window) {
  "use strict";

  let currentEvent = null;      // story_event en cours
  let currentPageIndex = 0;     // index dans ev.pages
  let onDoneCallback = null;    // callback fourni par playNextStoryFromQueue

  // ---------------------------------------------
  // Helpers internes
  // ---------------------------------------------

  function getPages(ev) {
    return Array.isArray(ev && ev.pages) ? ev.pages : [];
  }

  function getTextForPage(page) {
    const lang = document.documentElement.lang || "fr";
    if (!page || !page.text) return "";
    return page.text[lang] || page.text.en || "";
  }

    function formatSpeakerLabel(rawSpeaker) {
    if (!rawSpeaker) return "";

    if (rawSpeaker === "self") {
      return "Moi";
    }

    if (rawSpeaker.startsWith("npc_")) {
      // npc_village_chief -> "Village chief"
      const base = rawSpeaker.replace(/^npc_/, "").replace(/_/g, " ");
      // On met simplement la première lettre en majuscule
      return base.charAt(0).toUpperCase() + base.slice(1);
    }

    return rawSpeaker;
  }

  function computeTitle(ev, page) {
    const speaker = (page && page.speaker) || ev.speaker || "";
    const mood = (page && page.mood) || ev.mood || "";

    if (!speaker) return "Histoire";
    return mood ? `${speaker} – ${mood}` : speaker;
  }

  function renderCurrentPage() {
    const modal = document.getElementById("storyModal");
    if (!modal || !currentEvent) return;

    const pages = getPages(currentEvent);
    const total = Math.max(pages.length, 1);
    const idx = Math.min(Math.max(currentPageIndex, 0), total - 1);
    const page = pages[idx] || {};

    const titleEl   = document.getElementById("storyModalTitle");
    const textEl    = document.getElementById("storyModalText");
    const idxEl     = document.getElementById("storyModalPageIndex");
    const countEl   = document.getElementById("storyModalPageCount");
    const btnNext   = document.getElementById("storyModalNext");
    const btnDone   = document.getElementById("storyModalDone");
    const avatarEl  = document.getElementById("storyModalAvatar");
    const speakerEl = document.getElementById("storyModalSpeaker");

    // Speaker / avatar
    const rawSpeaker   = (page && page.speaker) || currentEvent.speaker || "";
    const speakerLabel = formatSpeakerLabel(rawSpeaker);
    const avatarPath   =
      STORY_AVATARS[rawSpeaker] || STORY_AVATARS.default;

    if (titleEl) {
      // Tu peux garder le titre "global" ou quelque chose de neutre
      titleEl.textContent = computeTitle(currentEvent, page);
    }

    if (speakerEl) {
      speakerEl.textContent = speakerLabel;
    }

    if (avatarEl) {
      avatarEl.src = avatarPath;
      avatarEl.alt = speakerLabel || "avatar";
    }

    // Texte
    if (textEl) {
      textEl.textContent = (getTextForPage(page) || "").trim();
    }

    // Pagination
    if (idxEl) idxEl.textContent = String(idx + 1);
    if (countEl) countEl.textContent = String(total);

    // Boutons Next / Done
    if (btnNext && btnDone) {
      if (idx < total - 1) {
        btnNext.style.display = "";
        btnDone.style.display = "none";
      } else {
        btnNext.style.display = "none";
        btnDone.style.display = "";
      }
    }
  }


  function closeModal() {
    const modal = document.getElementById("storyModal");
    if (modal) {
      modal.classList.remove("is-open");
    }

    const ev = currentEvent;

    // Marquer l'event comme "vu"
    if (ev && ev.id && typeof window.markStoryEventSeen === "function") {
      window.markStoryEventSeen(ev.id);
    }

    currentEvent = null;
    currentPageIndex = 0;

    // Prévenir playNextStoryFromQueue qu'on a fini
    if (typeof onDoneCallback === "function") {
      const cb = onDoneCallback;
      onDoneCallback = null;
      cb();
    }
  }

  // ---------------------------------------------
  // API appelée par game_app.js
  // ---------------------------------------------
  function openStoryModalForEvent(ev, doneCallback) {
    currentEvent = ev;
    currentPageIndex = 0;
    onDoneCallback = doneCallback || null;

    const modal = document.getElementById("storyModal");
    if (!modal) {
      console.warn("[story_app] storyModal introuvable, fallback alert().");
      // Fallback si pour une raison quelconque le modal n'existe pas
      if (ev && typeof window.renderStoryEventAsText === "function") {
        alert(window.renderStoryEventAsText(ev));
      }
      if (ev && ev.id && typeof window.markStoryEventSeen === "function") {
        window.markStoryEventSeen(ev.id);
      }
      if (typeof doneCallback === "function") {
        doneCallback();
      }
      return;
    }

    modal.classList.add("is-open");
    renderCurrentPage();
  }

  // ---------------------------------------------
  // Wiring DOM (Next / Done / Backdrop)
  // ---------------------------------------------
  function initStoryModal() {
    const modal = document.getElementById("storyModal");
    if (!modal) return;

    const backdrop = document.getElementById("storyModalBackdrop");
    const btnNext = document.getElementById("storyModalNext");
    const btnDone = document.getElementById("storyModalDone");

    if (btnNext) {
      btnNext.addEventListener("click", () => {
        const pages = getPages(currentEvent || {});
        if (!pages.length) {
          closeModal();
          return;
        }

        if (currentPageIndex < pages.length - 1) {
          currentPageIndex += 1;
          renderCurrentPage();
        } else {
          // Sécurité, mais normalement on ne passe plus ici
          closeModal();
        }
      });
    }

    if (btnDone) {
      btnDone.addEventListener("click", () => {
        closeModal();
      });
    }

    if (backdrop) {
      backdrop.addEventListener("click", () => {
        closeModal();
      });
    }
  }

  // Expose au window pour game_app.js
  window.openStoryModalForEvent = openStoryModalForEvent;

  // Init quand le DOM est prêt
  document.addEventListener("DOMContentLoaded", initStoryModal);
})(window);
