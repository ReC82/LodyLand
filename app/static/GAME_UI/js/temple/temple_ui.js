/* File: static/GAME_UI/js/temple/temple_ui.js
   Purpose: HUD + status + labels
*/
(function () {
  "use strict";

  window.Temple = window.Temple || {};

  const setStatus = (s, msg) => {
    if (s.gfx.statusText) s.gfx.statusText.setText(msg || "");
  };

  const updateHud = (s) => {
    const progressLabel = `${s.progressRow}/${s.rows}`;
    const rowLabel = s.playerRow === s.rows ? "Start" : `Row ${s.rows - s.playerRow}/${s.rows}`;
    if (s.gfx.hudText) {
      s.gfx.hudText.setText(
        `Lives: ${s.lives} | Progress: ${progressLabel} | ${rowLabel} | Col ${s.playerCol + 1}/${s.cols}`
      );
    }
  };

  window.Temple.ui = {
    setStatus,
    updateHud,
  };
})();
