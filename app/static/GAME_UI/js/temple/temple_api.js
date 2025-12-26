/* File: static/GAME_UI/js/temple/temple_api.js
   Purpose: All HTTP calls to /temple/*
*/
(function () {
  "use strict";

  window.Temple = window.Temple || {};

  const apiGet = async (url) => {
    const res = await fetch(url, { credentials: "same-origin" });
    return res.json();
  };

  const apiPost = async (url, payload) => {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload || {}),
    });
    return res.json();
  };

  window.Temple.api = {
    getState: () => apiGet("/temple/state"),
    advance: (col) => apiPost("/temple/advance", { col }),
    step: (row_from_bottom, col) => apiPost("/temple/step", { row_from_bottom, col }),
    devReset: async () => {
      const res = await fetch("/temple/dev/reset", { method: "POST", credentials: "same-origin" });
      return res.json();
    },
  };
})();
