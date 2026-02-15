// app/static/GAME_UI/js/i18n.js
/**
 * Client-side i18n module for LodyLand
 * 
 * Usage:
 *   await I18n.init();
 *   I18n.t("ui.welcome");
 *   I18n.currencyLabel("primary", 10);
 *   I18n.formatCurrency(100, "primary");
 */

const I18n = (() => {
  // Private state
  let currentLang = "en";
  let translations = {};
  let currencies = {};
  let availableLangs = ["en", "fr"];
  
  /**
   * Initialize the i18n system
   * Loads translations from the API
   */
  async function init() {
    try {
      const response = await fetch("/api/i18n/translations");
      
      if (!response.ok) {
        console.error("[i18n] Failed to load translations:", response.status);
        return false;
      }
      
      const data = await response.json();
      
      currentLang = data.lang || "en";
      translations = data.translations || {};
      currencies = data.currencies || {};
      availableLangs = data.available_langs || ["en", "fr"];
      
      console.log(`[i18n] Loaded translations for language: ${currentLang}`);
      
      // Store in localStorage for offline fallback
      try {
        localStorage.setItem("i18n_lang", currentLang);
        localStorage.setItem("i18n_data", JSON.stringify(data));
      } catch (e) {
        // localStorage may be disabled
      }
      
      return true;
      
    } catch (error) {
      console.error("[i18n] Error loading translations:", error);
      
      // Try to load from localStorage
      try {
        const cachedData = localStorage.getItem("i18n_data");
        if (cachedData) {
          const data = JSON.parse(cachedData);
          currentLang = data.lang || "en";
          translations = data.translations || {};
          currencies = data.currencies || {};
          console.log("[i18n] Loaded from cache");
          return true;
        }
      } catch (e) {
        // Ignore
      }
      
      return false;
    }
  }
  
  /**
   * Translate a key
   * 
   * @param {string} key - Translation key (e.g. "ui.welcome")
   * @param {object} vars - Variables to interpolate
   * @returns {string} Translated string
   * 
   * @example
   * t("ui.welcome")
   * t("errors.not_enough", { resource: "wood" })
   */
  function t(key, vars = {}) {
    // Navigate nested object
    const parts = key.split(".");
    let value = translations;
    
    for (const part of parts) {
      if (value && typeof value === "object") {
        value = value[part];
      } else {
        break;
      }
    }
    
    // Not found -> return key as fallback
    if (typeof value !== "string") {
      console.warn(`[i18n] Translation not found: ${key}`);
      return key;
    }
    
    // Interpolate variables
    let result = value;
    for (const [varName, varValue] of Object.entries(vars)) {
      result = result.replace(new RegExp(`{${varName}}`, "g"), varValue);
    }
    
    return result;
  }
  
  /**
   * Translate with plural support
   * 
   * @param {string} key - Base translation key
   * @param {number} count - Number for plural decision
   * @param {object} vars - Additional variables
   * @returns {string} Translated string
   * 
   * @example
   * tPlural("numbers.items", 1)   -> "1 item"
   * tPlural("numbers.items", 5)   -> "5 items"
   */
  function tPlural(key, count, vars = {}) {
    const pluralKey = count === 1 ? `${key}.one` : `${key}.other`;
    return t(pluralKey, { count, ...vars });
  }
  
  /**
   * Get currency label
   * 
   * @param {string} currencyType - "primary" or "premium"
   * @param {number} count - Amount (for singular/plural)
   * @param {boolean} short - Use short form
   * @returns {string} Currency label
   * 
   * @example
   * currencyLabel("primary", 1)      -> "Shard"
   * currencyLabel("primary", 10)     -> "Shards"
   * currencyLabel("premium", 5, true) -> "E"
   */
  function currencyLabel(currencyType, count = 1, short = false) {
    const currencyDef = currencies[currencyType];
    if (!currencyDef || !currencyDef.labels) {
      return currencyType;
    }
    
    const labels = currencyDef.labels;
    
    if (short) {
      return labels.short || currencyType[0].toUpperCase();
    }
    
    if (count === 1) {
      return labels.singular || currencyType;
    } else {
      return labels.plural || currencyType + "s";
    }
  }
  
  /**
   * Format a currency amount
   * 
   * @param {number} amount - Quantity
   * @param {string} currencyType - "primary" or "premium"
   * @param {boolean} withLabel - Include currency name
   * @param {boolean} short - Use short label
   * @returns {string} Formatted string
   * 
   * @example
   * formatCurrency(100, "primary")           -> "100 Shards"
   * formatCurrency(1, "premium")             -> "1 Essence"
   * formatCurrency(50, "primary", true, true) -> "50S"
   * formatCurrency(200, "primary", false)    -> "200"
   */
  function formatCurrency(amount, currencyType, withLabel = true, short = false) {
    if (!withLabel) {
      return amount.toString();
    }
    
    const label = currencyLabel(currencyType, amount, short);
    
    if (short) {
      return `${amount}${label}`;
    } else {
      return `${amount} ${label}`;
    }
  }
  
  /**
   * Get currency icon path
   * 
   * @param {string} currencyType - "primary" or "premium"
   * @returns {string} Icon path
   */
  function currencyIcon(currencyType) {
    const currencyDef = currencies[currencyType];
    return currencyDef?.icon || "/static/assets/img/ui/default.png";
  }
  
  /**
   * Get currency technical key (for API)
   * 
   * @param {string} currencyType - "primary" or "premium"
   * @returns {string} Key (e.g. "shards", "essence")
   */
  function currencyKey(currencyType) {
    const currencyDef = currencies[currencyType];
    return currencyDef?.key || currencyType;
  }
  
  /**
   * Change the current language
   * 
   * @param {string} lang - Language code (fr, en, ...)
   * @returns {Promise<boolean>} Success
   */
  async function setLanguage(lang) {
    if (!availableLangs.includes(lang)) {
      console.error(`[i18n] Invalid language: ${lang}`);
      return false;
    }
    
    try {
      console.log(`[i18n] Setting language to: ${lang}`);
      
      const response = await fetch("/api/i18n/set-language", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang }),
      });
      
      if (!response.ok) {
        console.error(`[i18n] Server returned error: ${response.status}`);
        return false;
      }
      
      const data = await response.json();
      
      if (!data.ok) {
        console.error(`[i18n] Server rejected language change:`, data);
        return false;
      }
      
      console.log(`[i18n] Language saved successfully: ${data.lang}`);
      
      // Important: Reload AFTER successful save
      window.location.reload();
      
      return true;
      
    } catch (error) {
      console.error("[i18n] Error setting language:", error);
      return false;
    }
  }
  
  /**
   * Get current language
   * 
   * @returns {string} Current language code
   */
  function getCurrentLang() {
    return currentLang;
  }
  
  /**
   * Get available languages
   * 
   * @returns {string[]} Array of language codes
   */
  function getAvailableLangs() {
    return availableLangs;
  }
  
  // Public API
  return {
    init,
    t,
    tPlural,
    currencyLabel,
    formatCurrency,
    currencyIcon,
    currencyKey,
    setLanguage,
    getCurrentLang,
    getAvailableLangs,
  };
})();

// Auto-initialize on page load
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => I18n.init());
} else {
  I18n.init();
}

// Expose globally
window.I18n = I18n;
