/* File: static/GAME_UI/js/temple/temple_movement.js
   Purpose: Gameplay rules (lateral step reveal, jumping broken tiles, advance, move down/back)
*/
(function () {
  "use strict";

  window.Temple = window.Temple || {};

  const grid = () => window.Temple.grid;

  const canStandOn = (s, gridRow, col) => {
    if (gridRow < 0 || gridRow >= s.rows) return false;
    if (col < 0 || col >= s.cols) return false;
    return !s.brokenTiles.has(grid().tileKey(gridRow, col));
  };

  const computeJumpDestinationCol = (s, gridRow, fromCol, dir) => {
    let c = fromCol + dir;
    if (c < 0 || c >= s.cols) return null;

    while (c >= 0 && c < s.cols) {
      if (canStandOn(s, gridRow, c)) return c;
      c += dir;
    }
    return null;
  };

  const findNearestSafeCol = (s, gridRow, preferredCol) => {
    if (gridRow === s.rows) return preferredCol; // start zone
    if (canStandOn(s, gridRow, preferredCol)) return preferredCol;

    for (let d = 1; d < s.cols; d++) {
      const L = preferredCol - d;
      const R = preferredCol + d;
      if (L >= 0 && canStandOn(s, gridRow, L)) return L;
      if (R < s.cols && canStandOn(s, gridRow, R)) return R;
    }
    return null;
  };

  const movePlayerTo = (scene, s, row, col, opts) => {
    const pos = grid().tileCenter(s, row, col);
    if (s.gfx.highlight) s.gfx.highlight.setPosition(pos.x, pos.y);

    const duration = opts && typeof opts.duration === "number" ? opts.duration : 120;
    scene.tweens.add({
      targets: s.gfx.player,
      x: pos.x,
      y: pos.y,
      duration,
      ease: "Sine.easeOut",
    });
  };

  const drawGridApplyBroken = (scene, s) => {
    // callback provided by temple_game.js (grid rebuild)
    if (typeof s._drawGrid === "function") s._drawGrid(scene, s);
  };

  // row_from_bottom for the CURRENT VISUAL ROW of the player
  const rowFromBottomForPlayerRow = (s) => {
    if (s.playerRow === s.rows) return 0; // start zone / outside grid
    return s.rows - s.playerRow;          // gridRow 7 => 1, gridRow 0 => 8
  };

  const syncPlayerFromProgress = (scene, s, opts) => {
    const targetRow = grid().gridRowFromProgress(s, s.progressRow);

    // start zone
    if (targetRow === s.rows) {
      s.playerRow = s.rows;
      movePlayerTo(scene, s, s.playerRow, s.playerCol, { duration: (opts && opts.duration) ?? 0 });
      window.Temple.ui.updateHud(s);
      return;
    }

    // ensure not standing on broken
    const safeCol = findNearestSafeCol(s, targetRow, s.playerCol);
    if (safeCol === null) {
      // row fully broken => fallback
      s.playerRow = s.rows;
      movePlayerTo(scene, s, s.playerRow, s.playerCol, { duration: 0 });
      window.Temple.ui.updateHud(s);
      return;
    }

    s.playerRow = targetRow;
    s.playerCol = safeCol;

    movePlayerTo(scene, s, s.playerRow, s.playerCol, { duration: (opts && opts.duration) ?? 0 });
    window.Temple.ui.updateHud(s);
  };

  const applyServerState = (s, st) => {
    if (typeof st.rows === "number") s.rows = st.rows;
    if (typeof st.cols === "number") s.cols = st.cols;
    if (typeof st.lives === "number") s.lives = st.lives;
    if (typeof st.progress_row === "number") s.progressRow = st.progress_row;

    s.serverBrokenTiles = Array.isArray(st.broken_tiles) ? st.broken_tiles : [];
    window.Temple.state.applyBrokenTilesFromServer(s);
  };

  const stepRevealAndMove = async (scene, s, destCol) => {
    if (s.requestInFlight) return;

    if (s.lives <= 0) {
      window.Temple.ui.setStatus(s, "No lives left today.");
      return;
    }

    // start zone: no reveal, allow free back/forth
    if (s.playerRow === s.rows) {
      s.playerCol = destCol;
      movePlayerTo(scene, s, s.playerRow, s.playerCol);
      window.Temple.ui.updateHud(s);
      return;
    }

    // must never land on broken
    if (!canStandOn(s, s.playerRow, destCol)) {
      window.Temple.ui.setStatus(s, "No available tile in that direction.");
      window.Temple.anim.flashBlocked(scene, s);
      return;
    }

    s.requestInFlight = true;
    window.Temple.ui.setStatus(s, "Stepping…");

    try {
      // IMPORTANT: server should accept stepping on <= progressRow.
      // We send the row we are actually on (playerRow).
      const rfb = rowFromBottomForPlayerRow(s);

      const ans = await window.Temple.api.step(rfb, destCol);
      if (!ans || !ans.ok) {
        window.Temple.ui.setStatus(s, "Step failed.");
        s.requestInFlight = false;
        return;
      }

      // If server still refuses "back rows", it will reply wrong_row.
      // We'll resync, but the real fix is server patch (below).
      if (ans.result === "not_in_grid" || ans.result === "wrong_row") {
        s.requestInFlight = false;
        window.Temple.ui.setStatus(s, "Resync…");
        await window.Temple.movement.loadState(scene, s);
        return;
      }

      applyServerState(s, ans);
      drawGridApplyBroken(scene, s);

      if (ans.result === "already_broken") {
        const dir = destCol > s.playerCol ? 1 : -1;
        const retryDest = computeJumpDestinationCol(s, s.playerRow, s.playerCol, dir);

        s.requestInFlight = false;

        if (retryDest === null) {
          window.Temple.ui.setStatus(s, "No available tile in that direction.");
          window.Temple.anim.flashBlocked(scene, s);
          window.Temple.ui.updateHud(s);
          return;
        }

        await stepRevealAndMove(scene, s, retryDest);
        return;
      }

      if (ans.result === "trap") {
        window.Temple.ui.setStatus(s, `Trap! Lives left: ${s.lives}`);

        const k = grid().tileKey(s.playerRow, destCol);
        s.brokenTiles.add(k);

        if (typeof s._hideTile === "function") s._hideTile(scene, s, s.playerRow, destCol);

        // snap + fall
        s.playerCol = destCol;
        movePlayerTo(scene, s, s.playerRow, s.playerCol, { duration: 0 });

        await window.Temple.anim.playTrapSequenceAt(scene, s, s.playerRow, destCol);

        // respawn based on progress (authoritative)
        syncPlayerFromProgress(scene, s, { duration: 0 });

        if (s.lives <= 0) window.Temple.ui.setStatus(s, "No lives left today. Come back tomorrow.");
        window.Temple.ui.updateHud(s);

        s.requestInFlight = false;
        return;
      }

      // safe
      s.playerCol = destCol;
      movePlayerTo(scene, s, s.playerRow, s.playerCol);
      window.Temple.anim.playSafeFeedback(scene, s);
      window.Temple.ui.setStatus(s, "");
      window.Temple.ui.updateHud(s);

      s.requestInFlight = false;
    } catch (e) {
      window.Temple.ui.setStatus(s, "Error during step.");
      s.requestInFlight = false;
    }
  };

  const tryLateralMove = async (scene, s, dir) => {
    if (s.requestInFlight) return;
    if (dir !== -1 && dir !== 1) return;

    // start zone: clamp and move freely
    if (s.playerRow === s.rows) {
      const next = Math.max(0, Math.min(s.cols - 1, s.playerCol + dir));
      if (next === s.playerCol) return;
      await stepRevealAndMove(scene, s, next);
      return;
    }

    const dest = computeJumpDestinationCol(s, s.playerRow, s.playerCol, dir);
    if (dest === null) {
      window.Temple.ui.setStatus(s, "No available tile in that direction.");
      window.Temple.anim.flashBlocked(scene, s);
      return;
    }

    await stepRevealAndMove(scene, s, dest);
  };

  // NEW: move down/back one row (client-only navigation)
  // - does NOT change progressRow (server authority)
  // - lets player go back to previously cleared rows and to Start
  const tryMoveDown = async (scene, s) => {
    if (s.requestInFlight) return;

    // Already at Start
    if (s.playerRow === s.rows) {
      window.Temple.anim.flashBlocked(scene, s);
      return;
    }

    // next visual row down
    const nextRow = s.playerRow + 1;

    // from bottom grid row -> Start zone
    if (nextRow > s.rows) return;

    // allow going to Start (outside grid)
    if (nextRow === s.rows) {
      s.playerRow = s.rows;
      movePlayerTo(scene, s, s.playerRow, s.playerCol, { duration: 120 });
      window.Temple.ui.setStatus(s, "");
      window.Temple.ui.updateHud(s);
      return;
    }

    // If you want to restrict to "already reached" area only:
    // the lowest reachable grid row is gridRowFromProgress(progressRow)
    // We are moving DOWN, which is always <= reached, so no restriction needed.

    const safeCol = findNearestSafeCol(s, nextRow, s.playerCol);
    if (safeCol === null) {
      window.Temple.ui.setStatus(s, "Row fully broken.");
      window.Temple.anim.flashBlocked(scene, s);
      return;
    }

    s.playerRow = nextRow;
    s.playerCol = safeCol;

    movePlayerTo(scene, s, s.playerRow, s.playerCol, { duration: 120 });
    window.Temple.ui.setStatus(s, "");
    window.Temple.ui.updateHud(s);
  };

  const tryAdvance = async (scene, s) => {
    if (s.requestInFlight) return;

    if (s.lives <= 0) {
      window.Temple.ui.setStatus(s, "No lives left today.");
      return;
    }
    if (s.progressRow >= s.rows) {
      window.Temple.ui.setStatus(s, "Already finished today.");
      return;
    }

    s.requestInFlight = true;
    window.Temple.ui.setStatus(s, "Advancing…");

    try {
      const ans = await window.Temple.api.advance(s.playerCol);
      if (!ans || !ans.ok) {
        window.Temple.ui.setStatus(s, "Advance failed.");
        s.requestInFlight = false;
        return;
      }

      applyServerState(s, ans);
      drawGridApplyBroken(scene, s);

      if (ans.result === "already_broken") {
        window.Temple.ui.setStatus(s, "This tile is already broken. Move sideways first.");
        window.Temple.anim.flashBlocked(scene, s);
        window.Temple.ui.updateHud(s);
        s.requestInFlight = false;
        return;
      }

      if (ans.result === "trap") {
        window.Temple.ui.setStatus(s, `Trap! Lives left: ${s.lives}`);

        const attemptRow = typeof ans.attempt_row === "number" ? ans.attempt_row : (s.progressRow + 1);
        const attemptedGridRow = s.rows - attemptRow;

        if (attemptedGridRow >= 0 && attemptedGridRow < s.rows) {
          const k = grid().tileKey(attemptedGridRow, s.playerCol);
          s.brokenTiles.add(k);
          if (typeof s._hideTile === "function") s._hideTile(scene, s, attemptedGridRow, s.playerCol);
          await window.Temple.anim.playTrapSequenceAt(scene, s, attemptedGridRow, s.playerCol);
        }

        syncPlayerFromProgress(scene, s, { duration: 0 });

        if (s.lives <= 0) window.Temple.ui.setStatus(s, "No lives left today. Come back tomorrow.");
        window.Temple.ui.updateHud(s);
        s.requestInFlight = false;
        return;
      }

      if (ans.result === "safe") {
        window.Temple.anim.playSafeFeedback(scene, s);
        window.Temple.ui.setStatus(s, "");

        // move to new row based on progressRow (server-authoritative)
        syncPlayerFromProgress(scene, s, { duration: 120 });

        if (ans.finished || s.progressRow >= s.rows) {
          if (s.gfx.statueLabel) s.gfx.statueLabel.setText("STATUE (reached)");
          window.Temple.ui.setStatus(s, "Temple cleared for today.");
        }

        s.requestInFlight = false;
        return;
      }

      if (ans.result === "no_lives") window.Temple.ui.setStatus(s, "No lives left today.");
      else if (ans.result === "already_finished") window.Temple.ui.setStatus(s, "Already finished today.");
      else window.Temple.ui.setStatus(s, `Result: ${ans.result}`);

      syncPlayerFromProgress(scene, s, { duration: 0 });
      window.Temple.ui.updateHud(s);

      s.requestInFlight = false;
    } catch (e) {
      window.Temple.ui.setStatus(s, "Error during advance.");
      s.requestInFlight = false;
    }
  };

  const loadState = async (scene, s) => {
    const st = await window.Temple.api.getState();
    if (!st || !st.ok) {
      window.Temple.ui.setStatus(s, "Unable to load temple state.");
      return false;
    }

    applyServerState(s, st);

    if (typeof s._onServerStateLoaded === "function") s._onServerStateLoaded(scene, s);

    drawGridApplyBroken(scene, s);

    window.Temple.ui.setStatus(s, "");
    syncPlayerFromProgress(scene, s, { duration: 0 });

    if (s.progressRow >= s.rows) {
      window.Temple.ui.setStatus(s, "Temple cleared for today.");
      if (s.gfx.statueLabel) s.gfx.statueLabel.setText("STATUE (reached)");
    }

    window.Temple.ui.updateHud(s);
    return true;
  };

  window.Temple.movement = {
    canStandOn,
    computeJumpDestinationCol,
    syncPlayerFromProgress,
    stepRevealAndMove,
    tryLateralMove,
    tryMoveDown,   // NEW
    tryAdvance,
    loadState,
  };
})();
