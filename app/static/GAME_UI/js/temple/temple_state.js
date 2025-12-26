/* File: static/GAME_UI/js/temple/temple_state.js
   Purpose: Local state holder (authoritative mirrors from server)
*/
(function () {
  "use strict";

  window.Temple = window.Temple || {};

  const make = () => ({
    rows: 8,
    cols: 10,

    lives: 3,
    progressRow: 0, // server: 0..ROWS, represents current row_from_bottom (and cleared rows)

    // player "visual" position
    playerRow: 8, // 0..ROWS-1 in grid, or ROWS for start zone
    playerCol: 0,

    // broken tiles local cache (server-synced): keys "r{gridRow}-c{col}"
    brokenTiles: new Set(),

    requestInFlight: false,

    // Phaser handles populated by scene
    gfx: {
      tileFillByKey: new Map(),
      tileBorderByKey: new Map(),
      gridObjects: [],
      highlight: null,
      player: null,
      statueLabel: null,
      statusText: null,
      hudText: null,
    },

    // computed geometry (set by grid module)
    geom: {
      startX: 0,
      startY: 0,
      tileSize: 28,
      gap: 10,
      padTop: 0,
      padBottom: 0,
      padX: 0,
      availW: 0,
      availH: 0,
    },
  });

  window.Temple.state = {
    make,

    // Converts server broken_tiles [{row_from_bottom, col}] to Set("r{gridRow}-c{col}")
    applyBrokenTilesFromServer: (st) => {
      const s = st;
      s.brokenTiles.clear();

      const arr = Array.isArray(st.serverBrokenTiles) ? st.serverBrokenTiles : [];
      const ROWS = s.rows;

      for (const it of arr) {
        const rfb = it && typeof it.row_from_bottom === "number" ? it.row_from_bottom : null;
        const c = it && typeof it.col === "number" ? it.col : null;
        if (rfb === null || c === null) continue;
        if (rfb < 1 || rfb > ROWS) continue;
        if (c < 0 || c >= s.cols) continue;

        const gridRow = ROWS - rfb; // 0..ROWS-1
        s.brokenTiles.add(`r${gridRow}-c${c}`);
      }
    },
  };
})();
