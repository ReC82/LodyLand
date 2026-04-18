// app/static/GAME_UI/js/profile_app.js
console.log("[Profile] profile_app.js loaded!");

document.addEventListener("DOMContentLoaded", () => {
  console.log("[Profile] DOMContentLoaded fired");
  initLanguageSelector();
  initThemeSelector();
  initBetaReset();
});

/**
 * Initialize language selector functionality
 */
function initLanguageSelector() {
  const languageInputs = document.querySelectorAll('input[name="language"]');
  
  console.log("[Profile] Found language inputs:", languageInputs.length);
  
  if (!languageInputs.length) {
    console.warn("[Profile] No language inputs found!");
    return;
  }
  
  languageInputs.forEach(input => {
    input.addEventListener('change', (e) => {
      const selectedLang = e.target.value;
      console.log("[Profile] Language changed to:", selectedLang);
      changeLanguage(selectedLang);
    });
  });
  
  console.log("[Profile] Language selector initialized");
}

/**
 * Change user language preference
 * @param {string} lang - Language code (fr, en, etc.)
 */
async function changeLanguage(lang) {
  console.log("[Profile] changeLanguage called with:", lang);
  
  try {
    // Check if I18n is available
    if (typeof I18n === 'undefined') {
      console.error("[Profile] I18n not available!");
      alert("Error: Translation system not loaded");
      return;
    }
    
    console.log("[Profile] Calling I18n.setLanguage...");
    const success = await I18n.setLanguage(lang);
    
    console.log("[Profile] I18n.setLanguage result:", success);
    
    if (success) {
      console.log("[Profile] Language change successful, showing toast");
      showToast('Language saved: ' + lang, 'success');
      
    } else {
      console.error("[Profile] Language change failed");
      showLanguageError();
    }
  } catch (error) {
    console.error("[Profile] Error in changeLanguage:", error);
    showLanguageError();
  }
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
  console.log("[Profile] Showing toast:", message, type);
  
  const toast = document.createElement('div');
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 12px 20px;
    background: ${type === 'success' ? '#10b981' : '#3b82f6'};
    color: white;
    border-radius: 8px;
    z-index: 9999;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    font-weight: 500;
  `;
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.remove();
  }, 2000);
}

/**
 * Show error message when language change fails
 */
function showLanguageError() {
  console.error("[Profile] showLanguageError called");
  
  const errorMsg = typeof I18n !== 'undefined' 
    ? I18n.t("errors.language_change_failed")
    : "Error changing language";
  
  alert(errorMsg);
  
  // Reset radio button to current language
  if (typeof I18n !== 'undefined') {
    const currentLang = I18n.getCurrentLang();
    const currentInput = document.querySelector(`input[name="language"][value="${currentLang}"]`);
    if (currentInput) {
      currentInput.checked = true;
    }
  }
}

/**
 * Theme selector
 */
function initThemeSelector() {
  const picker = document.getElementById("theme-picker");
  if (!picker) return;

  picker.querySelectorAll(".theme-option").forEach(option => {
    option.addEventListener("click", async () => {
      const theme = option.dataset.theme;
      if (!theme) return;

      // Optimistic UI: apply class immediately
      const body = document.body;
      body.className = body.className.replace(/theme-\S+/, "").trim() + " theme-" + theme;

      // Update active state in picker
      picker.querySelectorAll(".theme-option").forEach(o => {
        o.classList.remove("active");
        o.querySelector(".theme-check").textContent = "";
      });
      option.classList.add("active");
      option.querySelector(".theme-check").textContent = "✓";

      // Save to server
      const msg = document.getElementById("theme-save-msg");
      try {
        const res = await fetch("/api/player/theme", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ theme }),
        });
        if (res.ok) {
          if (msg) { msg.style.color = "#4ade80"; msg.textContent = "Thème sauvegardé !"; }
        } else {
          if (msg) { msg.style.color = "#f87171"; msg.textContent = "Erreur lors de la sauvegarde."; }
        }
      } catch (e) {
        if (msg) { msg.style.color = "#f87171"; msg.textContent = "Erreur réseau."; }
      }
      if (msg) setTimeout(() => { msg.textContent = ""; }, 2500);
    });
  });
}

/**
 * Beta Reset
 */
function initBetaReset() {
  const btn = document.getElementById('btn-beta-reset');
  const modal = document.getElementById('modal-beta-reset');
  if (!btn || !modal) return;

  function openModal() {
    document.getElementById('beta-reset-confirm-input').value = '';
    document.getElementById('beta-reset-error').style.display = 'none';
    modal.style.display = 'flex';
    document.getElementById('beta-reset-confirm-input').focus();
  }

  function closeModal() {
    modal.style.display = 'none';
  }

  btn.addEventListener('click', openModal);
  document.getElementById('modal-beta-close').addEventListener('click', closeModal);
  document.getElementById('modal-beta-cancel').addEventListener('click', closeModal);

  // Close on backdrop click
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });

  // Close on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.style.display === 'flex') closeModal();
  });

  document.getElementById('btn-beta-reset-confirm').addEventListener('click', async () => {
    const input = document.getElementById('beta-reset-confirm-input').value.trim();
    const errorEl = document.getElementById('beta-reset-error');
    errorEl.style.display = 'none';

    try {
      const response = await fetch('/api/player/beta-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm_name: input })
      });

      if (response.ok) {
        closeModal();
        showToast('Reset effectué !', 'success');
        setTimeout(() => window.location.reload(), 1500);
      } else {
        errorEl.style.display = 'block';
      }
    } catch (err) {
      console.error('[BetaReset] Error:', err);
      errorEl.style.display = 'block';
    }
  });
}

console.log("[Profile] profile_app.js fully loaded");