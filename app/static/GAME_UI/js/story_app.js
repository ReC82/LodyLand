/*
  File: static/GAME_UI/js/story_app.js
  Purpose: Handle narrative / tutorial story events (level-based).
  Notes:
  - Uses /api/levels and /api/state.
  - Depends on global http() and $() helpers.
*/

/* global http, $ */

const STORY_STATE = {
  lang: document.documentElement.lang === "en" ? "en" : "fr",
  levels: null,          // cached /api/levels result
  shownIds: new Set(),   // IDs persisted in DB + session
  currentEvent: null,
  currentPageIndex: 0,
};

/**
 * Fetch and cache levels (including story_events) from the API.
 */
async function storyLoadLevels() {
  if (STORY_STATE.levels) {
    return STORY_STATE.levels;
  }

  const res = await http("GET", "/api/levels");
  if (!res.ok) {
    console.error("[story] Failed to load levels", res);
    STORY_STATE.levels = [];
    return STORY_STATE.levels;
  }

  STORY_STATE.levels = res.data || [];
  return STORY_STATE.levels;
}

/**
 * Fetch full player state, and hydrate story_flags.
 */
async function storyFetchState() {
  const res = await http("GET", "/api/state");
  if (!res.ok) {
    console.error("[story] Failed to load state", res);
    return null;
  }
  const data = res.data || null;
  if (!data) return null;

  // NEW: hydrate shownIds from backend story_flags
  const flags = Array.isArray(data.story_flags) ? data.story_flags : [];
  flags.forEach((id) => {
    if (id) {
      STORY_STATE.shownIds.add(id);
    }
  });

  return data;
}

/**
 * Helper to get localized text for a page.
 */
function storyGetTextForPage(page) {
  const textMap = page.text || {};
  if (STORY_STATE.lang in textMap) {
    return textMap[STORY_STATE.lang] || "";
  }
  // Fallbacks
  if (textMap.fr) return textMap.fr;
  if (textMap.en) return textMap.en;
  return "";
}

/**
 * Render the current page of the current event into the modal.
 */
function storyRenderCurrentPage() {
  const ev = STORY_STATE.currentEvent;
  if (!ev) return;

  const pages = Array.isArray(ev.pages) ? ev.pages : [];
  const idx = STORY_STATE.currentPageIndex;

  const modal = $("storyModal");
  const textEl = $("storyModalText");
  const pageIndexEl = $("storyModalPageIndex");
  const pageCountEl = $("storyModalPageCount");
  const nextBtn = $("storyModalNext");
  const doneBtn = $("storyModalDone");

  if (!modal || !textEl || !pageIndexEl || !pageCountEl || !nextBtn || !doneBtn) {
    return;
  }

  if (!pages.length || idx < 0 || idx >= pages.length) {
    console.warn("[story] Invalid page index", idx);
    return;
  }

  const page = pages[idx];

  // Set text
  const txt = storyGetTextForPage(page);
  textEl.textContent = txt;

  // Page indicator
  pageIndexEl.textContent = String(idx + 1);
  pageCountEl.textContent = String(pages.length);

  // Buttons logic
  if (idx < pages.length - 1) {
    // Not last page
    nextBtn.style.display = "inline-block";
    doneBtn.style.display = "none";
  } else {
    // Last page
    nextBtn.style.display = "none";
    doneBtn.style.display = "inline-block";
  }

  // Apply modal variant if present (full / centered / toast)
  modal.classList.remove("story-modal-full", "story-modal-centered", "story-modal-toast");
  const variant = ev.modal_variant || "centered";
  if (variant === "full") {
    modal.classList.add("story-modal-full");
  } else if (variant === "toast") {
    modal.classList.add("story-modal-toast");
  } else {
    modal.classList.add("story-modal-centered");
  }

  // Finally open modal
  modal.classList.add("is-open");
}

/**
 * Open the story modal for a given event (starting at page 0).
 */
function storyOpenEvent(ev) {
  STORY_STATE.currentEvent = ev;
  STORY_STATE.currentPageIndex = 0;
  storyRenderCurrentPage();
}

/**
 * Initialize story modal buttons.
 */
function initStoryModal() {
  const modal = $("storyModal");
  const nextBtn = $("storyModalNext");
  const doneBtn = $("storyModalDone");
  const backdrop = $("storyModalBackdrop");

  if (!modal || !nextBtn || !doneBtn || !backdrop) {
    return;
  }

  // Next page
  nextBtn.addEventListener("click", () => {
    const ev = STORY_STATE.currentEvent;
    if (!ev) return;
    const pages = Array.isArray(ev.pages) ? ev.pages : [];
    const idx = STORY_STATE.currentPageIndex;

    if (idx < pages.length - 1) {
      STORY_STATE.currentPageIndex = idx + 1;
      storyRenderCurrentPage();
    }
  });

  // Finish story
  doneBtn.addEventListener("click", async () => {
    const ev = STORY_STATE.currentEvent;
    if (ev && ev.id) {
      // Mark as seen in memory immediately
      STORY_STATE.shownIds.add(ev.id);

      // NEW: persist to backend
      try {
        const res = await http("POST", "/api/story/seen", {
          story_id: ev.id,
        });
        if (!res.ok) {
          console.error("[story] Failed to mark story as seen", res);
        }
      } catch (err) {
        console.error("[story] Error while marking story as seen", err);
      }
    }

    modal.classList.remove("is-open");
    STORY_STATE.currentEvent = null;
    STORY_STATE.currentPageIndex = 0;
  });

  // Optional: ignore click on backdrop to force using buttons
  backdrop.addEventListener("click", (e) => {
    // Do nothing: player must use the buttons.
    e.stopPropagation();
  });
}

/**
 * Baby step: show only the "on_first_login" story for level 0.
 * Condition: player.level === 0 AND player.xp === 0 (approx first login).
 */
async function storyMaybeShowIntroOnFirstLogin() {
  const [levels, state] = await Promise.all([
    storyLoadLevels(),
    storyFetchState(),
  ]);

  if (!state || !state.player) {
    return;
  }

  const player = state.player;

  // Approximate "first login": level 0 and no XP yet
  if (Number(player.level ?? 0) !== 0) return;
  if (Number(player.xp ?? 0) > 0) return;

  const lvl0 = levels.find((l) => Number(l.level) === 0);
  if (!lvl0) return;

  const events = Array.isArray(lvl0.story_events) ? lvl0.story_events : [];
  const ev = events.find((e) => e.trigger === "on_first_login");
  if (!ev) return;

  // Respect show_once using persisted flags
  if (ev.show_once && ev.id && STORY_STATE.shownIds.has(ev.id)) {
    return;
  }

  storyOpenEvent(ev);
}

/**
 * Entry point: called on DOM ready.
 */
document.addEventListener("DOMContentLoaded", () => {
  initStoryModal();
  // Baby step: only intro for now
  storyMaybeShowIntroOnFirstLogin().catch((err) => {
    console.error("[story] intro error", err);
  });
});
