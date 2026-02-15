// app/static/GAME_UI/js/profile_app.js
console.log("[Profile] profile_app.js loaded!");

document.addEventListener("DOMContentLoaded", () => {
  console.log("[Profile] DOMContentLoaded fired");
  initLanguageSelector();
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
      
      // Wait 500ms before reload
      setTimeout(() => {
        console.log("[Profile] Reloading page...");
        window.location.reload();
      }, 500);
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

console.log("[Profile] profile_app.js fully loaded");