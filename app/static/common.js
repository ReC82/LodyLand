/* File: static/common.js
   Purpose: Global helpers shared by GAME_UI scripts
*/

function $(id) {
  return document.getElementById(id);
}

async function http(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  });

  // 204 / empty responses safety
  const ct = res.headers.get("content-type") || "";
  const isJson = ct.includes("application/json");

  let data = null;
  if (res.status !== 204) {
    data = isJson ? await res.json().catch(() => null) : await res.text().catch(() => "");
  }

  return { ok: res.ok, status: res.status, data };
}

// ============================================================
// Currency Helpers - Client-side currency icon generation
// ============================================================

/**
 * Currency icon helpers for client-side rendering
 * Usage: CurrencyHelpers.coinIcon('small') or CH.coinIcon('small')
 */
window.CurrencyHelpers = {
  /**
   * Get the base path for UI images
   * @returns {string}
   */
  getUIPath() {
    return window.UI_IMG_PATH || '/static/assets/img/ui/';
  },

  /**
   * Get coin icon HTML
   * @param {string} size - 'small', 'medium', or 'large'
   * @param {string} additionalClasses - Optional additional CSS classes
   * @returns {string} HTML string
   */
  coinIcon(size = 'small', additionalClasses = '') {
    const basePath = this.getUIPath();
    const classes = `currency-icon currency-icon-${size} ${additionalClasses}`.trim();
    return `<img src="${basePath}coins.png" alt="Coins" class="${classes}" />`;
  },

  /**
   * Get diam icon HTML
   * @param {string} size - 'small', 'medium', or 'large'
   * @param {string} additionalClasses - Optional additional CSS classes
   * @returns {string} HTML string
   */
  diamIcon(size = 'small', additionalClasses = '') {
    const basePath = this.getUIPath();
    const classes = `currency-icon currency-icon-${size} ${additionalClasses}`.trim();
    return `<img src="${basePath}diams.png" alt="Diamants" class="${classes}" />`;
  },

  /**
   * Get coin display with amount
   * @param {number|string} amount - The amount to display
   * @param {string} size - Icon size
   * @returns {string} HTML string
   */
  coinsDisplay(amount, size = 'small') {
    return `
      <span class="currency-display currency-display-coins">
        ${this.coinIcon(size)}
        <span class="currency-amount">${amount}</span>
      </span>
    `.trim();
  },

  /**
   * Get diam display with amount
   * @param {number|string} amount - The amount to display
   * @param {string} size - Icon size
   * @returns {string} HTML string
   */
  diamsDisplay(amount, size = 'small') {
    return `
      <span class="currency-display currency-display-diams">
        ${this.diamIcon(size)}
        <span class="currency-amount">${amount}</span>
      </span>
    `.trim();
  },

  /**
   * Get both currencies side by side
   * @param {number|string} coins - Coins amount
   * @param {number|string} diams - Diams amount
   * @param {string} size - Icon size
   * @returns {string} HTML string
   */
  currenciesDisplay(coins, diams, size = 'small') {
    return `
      <span class="currencies-display">
        ${this.coinsDisplay(coins, size)}
        ${this.diamsDisplay(diams, size)}
      </span>
    `.trim();
  },

  /**
   * Format a price with coin icon
   * Useful for displaying prices in markets/shops
   * @param {number|string} price - The price
   * @param {string} size - Icon size
   * @returns {string} HTML string
   */
  formatPrice(price, size = 'small') {
    return `${price} ${this.coinIcon(size)}`;
  },

  /**
   * Format a premium price with diam icon
   * @param {number|string} price - The price
   * @param {string} size - Icon size
   * @returns {string} HTML string
   */
  formatPremiumPrice(price, size = 'small') {
    return `${price} ${this.diamIcon(size)}`;
  }
};

// Shorthand alias for convenience
window.CH = window.CurrencyHelpers;

// Explicit global exposure
window.$ = $;
window.http = http;

console.log('[common.js] Loaded with Currency Helpers');
