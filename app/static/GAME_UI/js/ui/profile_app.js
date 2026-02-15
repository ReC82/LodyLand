// app/static/GAME_UI/js/profile_app.js
/**
 * Profile page logic
 */

document.addEventListener("DOMContentLoaded", () => {
  initLanguageSelector();
});

/**
 * Initialize language selector functionality
 */
function initLanguageSelector() {
  const languageInputs = document.querySelectorAll('input[name="language"]');
  
  if (!languageInputs.length) return;
  
  languageInputs.forEach(input => {
    input.addEventListener('change', (e) => {
      const selectedLang = e.target.value;
      changeLanguage(selectedLang);
    });
  });
}

/**
 * Change user language preference
 * @param {string} lang - Language code (fr, en, etc.)
 */
async function changeLanguage(lang) {
  try {
    // Use I18n API to set language
    const success = await I18n.setLanguage(lang);
    
    if (success) {
      console.log(`[Profile] Language changed to: ${lang}`);
      // Page will reload automatically via I18n.setLanguage()
    } else {
      console.error('[Profile] Failed to change language');
      showLanguageError();
    }
  } catch (error) {
    console.error('[Profile] Error changing language:', error);
    showLanguageError();
  }
}

/**
 * Show error message when language change fails
 */
function showLanguageError() {
  // Use i18n for error message
  const errorMsg = typeof I18n !== 'undefined' 
    ? I18n.t("errors.language_change_failed")
    : "Erreur lors du changement de langue";
  
  alert(errorMsg);
  
  // Reset radio button to current language
  const currentLang = I18n.getCurrentLang();
  const currentInput = document.querySelector(`input[name="language"][value="${currentLang}"]`);
  if (currentInput) {
    currentInput.checked = true;
  }
}