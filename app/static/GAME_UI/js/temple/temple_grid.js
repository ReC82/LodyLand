/* File: static/GAME_UI/js/temple/temple_grid.js
   Purpose: Grid geometry, positions and tile keys
*/
(function () {
  "use strict";

  window.Temple = window.Temple || {};

  const tileKey = (r, c) => `r${r}-c${c}`;

  const computeTileSize = (availW, availH, rows, cols, gap, tileScale) => {
    const tileW = Math.floor((availW - gap * (cols - 1)) / cols);
    const tileH = Math.floor((availH - gap * (rows - 1)) / rows);
    const raw = Math.min(tileW, tileH);
    return Math.max(18, Math.floor(raw * tileScale));
  };

  const computeGridGeometry = (w, padTop, padBottom, padX, gap, rows, cols, tileSize) => {
    const availW = w - padX * 2;
    const gridW = tileSize * cols + gap * (cols - 1);
    const startX = Math.floor((w - gridW) / 2);

    // vertical is handled by caller (based on scene height)
    return { startX, availW, gridW, padTop, padBottom, padX, gap };
  };

  const tileCenter = (s, row, col) => {
    const { startX, startY, tileSize, gap } = s.geom;
    const x = startX + col * (tileSize + gap) + tileSize / 2;

    if (row < s.rows) {
      const y = startY + row * (tileSize + gap) + tileSize / 2;
      return { x, y };
    }

    // start zone: one tile-height below last grid row
    const bottomY =
      startY +
      (s.rows - 1) * (tileSize + gap) +
      tileSize / 2 +
      tileSize +
      gap;

    return { x, y: bottomY };
  };

  const gridRowFromProgress = (s, progressRow) => {
    if (progressRow <= 0) return s.rows; // start zone
    const gridRow = s.rows - progressRow;
    return Math.max(0, Math.min(s.rows - 1, gridRow));
  };

  const rowFromBottomFromGridRow = (s, gridRow) => {
    if (gridRow === s.rows) return 0;
    return s.rows - gridRow;
  };

  window.Temple.grid = {
    tileKey,
    computeTileSize,
    computeGridGeometry,
    tileCenter,
    gridRowFromProgress,
    rowFromBottomFromGridRow,
  };
})();
