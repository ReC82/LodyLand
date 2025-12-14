/* File: static/GAME_UI/js/temple/temple_game.js
   Purpose: Temple Phaser client (STEP 7: lateral reveal + persistent broken tiles + fall anim + DEV reset)
   Notes:
   - Placeholder visuals (rectangles), sprites later.
   - Client NEVER knows trap positions.
   - Lateral move REVEALS tile via server (POST /temple/step).
   - If next tile is broken, player "jumps" over broken tiles to the next available tile in that direction.
   - Player can always move back/forward laterally on his current row (server reveals each tile),
     but can never end a move on a broken tile.
   - Trap: tile collapses and disappears; player shrinks in place (top-down fall); respawn on nearest safe.
   - Broken tiles are loaded from server state (persist across refresh/devices).
   - DEV shortcut: press K to reset today's run (POST /temple/dev/reset)
*/

(function () {
  "use strict";

  const mount = document.getElementById("phaser-temple");
  if (!mount) {
    console.warn("[Temple] Mount point #phaser-temple not found.");
    return;
  }

  if (typeof Phaser === "undefined") {
    console.error("[Temple] Phaser is not loaded. Check phaser.min.js include.");
    return;
  }

  // -----------------------------
  // API helpers
  // -----------------------------
  const apiGet = async (url) => {
    const res = await fetch(url, { credentials: "same-origin" });
    return res.json();
  };

  const apiPost = async (url, payload) => {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    return res.json();
  };

  class TempleScene extends Phaser.Scene {
    constructor() {
      super("TempleScene");
    }

    create() {
      /* ============================================================
         SCENE & LAYOUT
         ============================================================ */

      const w = this.scale.width;
      const h = this.scale.height;

      this.add.rectangle(w / 2, h / 2, w, h, 0x0b1020).setOrigin(0.5);

      this.add.text(16, 12, "TEMPLE — STEP 7 (Lateral reveal + jump broken tiles)", {
        fontFamily: "Arial",
        fontSize: "16px",
        color: "#ffffff",
      });

      // --- Layout tuning ---
      const STATUE_ZONE_H = 120;
      const TILE_SCALE = 0.82;

      // Depth system (important for visibility)
      const DEPTH_TILES = 10;
      const DEPTH_HIGHLIGHT = 20;
      const DEPTH_PLAYER = 30;
      const DEPTH_UI = 100;

      // Statue placeholder
      const statueX = w / 2;
      const statueY = 48 + STATUE_ZONE_H / 2;

      this.add
        .rectangle(statueX, statueY, 180, 90, 0x0f172a)
        .setOrigin(0.5)
        .setStrokeStyle(2, 0x2a3a66, 1)
        .setDepth(DEPTH_UI);

      const statueLabel = this.add
        .text(statueX, statueY, "STATUE (placeholder)", {
          fontFamily: "Arial",
          fontSize: "14px",
          color: "#9ca3af",
        })
        .setOrigin(0.5)
        .setDepth(DEPTH_UI);

      /* ============================================================
         GRID CONFIG
         ============================================================ */

      let ROWS = 8;
      let COLS = 10;

      const padX = 24;
      const padTop = 48 + STATUE_ZONE_H;
      const padBottom = 28;
      const gap = 10;

      const availW = w - padX * 2;
      const availH = h - padTop - padBottom;

      const computeTileSize = (rows, cols) => {
        const tileW = Math.floor((availW - gap * (cols - 1)) / cols);
        const tileH = Math.floor((availH - gap * (rows - 1)) / rows);
        const raw = Math.min(tileW, tileH);
        return Math.max(18, Math.floor(raw * TILE_SCALE));
      };

      let tileSize = computeTileSize(ROWS, COLS);

      const computeGridGeometry = (rows, cols, tSize) => {
        const gridW = tSize * cols + gap * (cols - 1);
        const gridH = tSize * rows + gap * (rows - 1);
        const startX = Math.floor((w - gridW) / 2);
        const startY = padTop + Math.floor((availH - gridH) / 2);
        return { gridW, gridH, startX, startY };
      };

      let { startX, startY } = computeGridGeometry(ROWS, COLS, tileSize);

      // row = 0..ROWS-1 inside grid
      // row = ROWS outside start position (bottom)
      const tileCenter = (row, col) => {
        const x = startX + col * (tileSize + gap) + tileSize / 2;

        if (row < ROWS) {
          const y = startY + row * (tileSize + gap) + tileSize / 2;
          return { x, y };
        }

        const bottomY =
          startY +
          (ROWS - 1) * (tileSize + gap) +
          tileSize / 2 +
          tileSize +
          gap;

        return { x, y: bottomY };
      };

      /* ============================================================
         GRID OBJECTS + BROKEN TILES (server-synced)
         ============================================================ */

      const tileFillByKey = new Map();
      const tileBorderByKey = new Map();
      const gridObjects = [];

      // Authoritative from server (/temple/state)
      // Set key format: "r{gridRow}-c{col}"
      const brokenTiles = new Set();

      const tileKey = (r, c) => `r${r}-c${c}`;

      const hideTile = (gridRow, col) => {
        const k = tileKey(gridRow, col);
        const fill = tileFillByKey.get(k);
        const border = tileBorderByKey.get(k);
        if (fill) fill.setVisible(false);
        if (border) border.setVisible(false);
      };

      const drawGrid = () => {
        for (const obj of gridObjects) obj.destroy();
        gridObjects.length = 0;
        tileFillByKey.clear();
        tileBorderByKey.clear();

        for (let r = 0; r < ROWS; r++) {
          for (let c = 0; c < COLS; c++) {
            const key = tileKey(r, c);
            const { x, y } = tileCenter(r, c);

            const baseColor = 0x111a33;
            const rowTint = r * 0x030303;
            const color = baseColor + rowTint;

            const fill = this.add
              .rectangle(x, y, tileSize, tileSize, color)
              .setOrigin(0.5)
              .setDepth(DEPTH_TILES);

            const border = this.add
              .rectangle(x, y, tileSize, tileSize)
              .setOrigin(0.5)
              .setStrokeStyle(2, 0x2a3a66, 1)
              .setDepth(DEPTH_TILES + 1);

            tileFillByKey.set(key, fill);
            tileBorderByKey.set(key, border);

            gridObjects.push(fill, border);

            if (brokenTiles.has(key)) {
              fill.setVisible(false);
              border.setVisible(false);
            }
          }
        }
      };

      /* ============================================================
         PLAYER STATE
         ============================================================ */

      let lives = 3;
      let progressRow = 0;

      // playerRow: ROWS means "outside start"
      let playerRow = ROWS;
      let playerCol = 0;

      const highlight = this.add
        .rectangle(0, 0, tileSize + 6, tileSize + 6)
        .setOrigin(0.5)
        .setStrokeStyle(3, 0xfbbf24, 1)
        .setDepth(DEPTH_HIGHLIGHT);

      const player = this.add
        .rectangle(0, 0, Math.floor(tileSize * 0.5), Math.floor(tileSize * 0.5), 0x22c55e)
        .setOrigin(0.5)
        .setDepth(DEPTH_PLAYER);

      const statusText = this.add
        .text(16, h - 40, "", {
          fontFamily: "Arial",
          fontSize: "14px",
          color: "#9ca3af",
        })
        .setDepth(DEPTH_UI);

      const hud = this.add
        .text(16, h - 18, "", {
          fontFamily: "Arial",
          fontSize: "14px",
          color: "#9ca3af",
        })
        .setDepth(DEPTH_UI);

      const setStatus = (msg) => statusText.setText(msg || "");

      const updateHud = () => {
        const progressLabel = `${progressRow}/${ROWS}`;
        const rowLabel = playerRow === ROWS ? "Start" : `Row ${ROWS - playerRow}/${ROWS}`;
        hud.setText(
          `Lives: ${lives} | Progress: ${progressLabel} | ${rowLabel} | Col ${playerCol + 1}/${COLS}`
        );
      };

      const movePlayerTo = (row, col, opts = {}) => {
        const pos = tileCenter(row, col);

        highlight.setPosition(pos.x, pos.y);

        const duration = typeof opts.duration === "number" ? opts.duration : 120;

        this.tweens.add({
          targets: player,
          x: pos.x,
          y: pos.y,
          duration,
          ease: "Sine.easeOut",
        });
      };

      /* ============================================================
         SAFE PLACEMENT (avoid broken tiles on refresh)
         ============================================================ */

      const computeGridRowFromProgress = (pr) => {
        if (pr <= 0) return ROWS;
        const gridRow = ROWS - pr; // 1->ROWS-1, 8->0
        return Math.max(0, Math.min(ROWS - 1, gridRow));
      };

      const findNearestSafeCol = (gridRow, preferredCol) => {
        if (gridRow === ROWS) return preferredCol;

        if (!brokenTiles.has(tileKey(gridRow, preferredCol))) return preferredCol;

        for (let d = 1; d < COLS; d++) {
          const left = preferredCol - d;
          const right = preferredCol + d;
          if (left >= 0 && !brokenTiles.has(tileKey(gridRow, left))) return left;
          if (right < COLS && !brokenTiles.has(tileKey(gridRow, right))) return right;
        }
        return null;
      };

      const syncPlayerFromProgress = (opts = {}) => {
        const targetRow = computeGridRowFromProgress(progressRow);

        if (targetRow === ROWS) {
          playerRow = ROWS;
          movePlayerTo(playerRow, playerCol, { duration: opts.duration ?? 0 });
          updateHud();
          return;
        }

        const safeCol = findNearestSafeCol(targetRow, playerCol);
        if (safeCol === null) {
          // Entire row is broken => fallback outside start
          playerRow = ROWS;
          movePlayerTo(playerRow, playerCol, { duration: 0 });
          updateHud();
          return;
        }

        playerRow = targetRow;
        playerCol = safeCol;

        movePlayerTo(playerRow, playerCol, { duration: opts.duration ?? 0 });
        updateHud();
      };

      /* ============================================================
         BROKEN TILE HELPERS
         ============================================================ */

      const rowFromBottomOfCurrentRow = () => {
        if (playerRow === ROWS) return 0; // start area
        return ROWS - playerRow; // gridRow 7 => 1, gridRow 0 => 8
      };

      const canStandOn = (gridRow, col) => {
        if (gridRow < 0 || gridRow >= ROWS) return false;
        if (col < 0 || col >= COLS) return false;
        return !brokenTiles.has(tileKey(gridRow, col));
      };

      // If immediate target tile is broken, jump over consecutive broken tiles in the same direction.
      // Returns: destination col (safe), or null if none.
      const computeJumpDestinationCol = (gridRow, fromCol, dir) => {
        let c = fromCol + dir;
        if (c < 0 || c >= COLS) return null;

        while (c >= 0 && c < COLS) {
          if (canStandOn(gridRow, c)) return c;
          c += dir;
        }
        return null;
      };

      /* ============================================================
         ANIMATIONS
         ============================================================ */

      const playSafeFeedback = () => {
        this.tweens.add({
          targets: highlight,
          alpha: 0.4,
          yoyo: true,
          repeat: 1,
          duration: 90,
        });
      };

      const flashBlocked = () => {
        this.tweens.add({
          targets: highlight,
          alpha: 0.15,
          yoyo: true,
          repeat: 2,
          duration: 80,
        });
      };

      const collapseTileAndHide = async (gridRow, col) => {
        const key = tileKey(gridRow, col);
        const fill = tileFillByKey.get(key);
        const border = tileBorderByKey.get(key);

        if (!fill || !border) return;

        await new Promise((resolve) => {
          this.tweens.add({
            targets: [fill, border],
            scaleX: 0.0,
            scaleY: 0.0,
            alpha: 0.0,
            duration: 220,
            ease: "Back.easeIn",
            onComplete: () => resolve(),
          });
        });

        fill.setVisible(false);
        border.setVisible(false);
      };

      const playerTopDownFall = async () => {
        await new Promise((resolve) => {
          this.tweens.add({
            targets: player,
            x: player.x + 4,
            yoyo: true,
            repeat: 2,
            duration: 40,
            onComplete: () => resolve(),
          });
        });

        await new Promise((resolve) => {
          this.tweens.add({
            targets: player,
            scaleX: 0.0,
            scaleY: 0.0,
            alpha: 0.0,
            duration: 320,
            ease: "Sine.easeIn",
            onComplete: () => resolve(),
          });
        });
      };

      const respawnPlayerVisual = () => {
        player.setAlpha(1);
        player.setScale(1, 1);
      };

      const playTrapSequenceAt = async (gridRow, col) => {
        const { x, y } = tileCenter(gridRow, col);
        highlight.setPosition(x, y);
        player.setPosition(x, y);
        player.setDepth(DEPTH_PLAYER);

        await collapseTileAndHide(gridRow, col);
        await playerTopDownFall();

        respawnPlayerVisual();
        await new Promise((resolve) => setTimeout(resolve, 120));

        // respawn to last safe position according to progressRow, but never on broken
        syncPlayerFromProgress({ duration: 0 });
      };

      /* ============================================================
         SERVER STATE LOAD (includes broken tiles)
         ============================================================ */

      const applyBrokenTilesFromState = (arr) => {
        brokenTiles.clear();
        if (!Array.isArray(arr)) return;

        for (const it of arr) {
          const rfb = it && typeof it.row_from_bottom === "number" ? it.row_from_bottom : null;
          const c = it && typeof it.col === "number" ? it.col : null;
          if (rfb === null || c === null) continue;
          if (rfb < 1 || rfb > ROWS) continue;
          if (c < 0 || c >= COLS) continue;

          const gridRow = ROWS - rfb; // convert to 0..ROWS-1
          brokenTiles.add(tileKey(gridRow, c));
        }
      };

      const loadState = async () => {
        try {
          const st = await apiGet("/temple/state");
          if (!st || !st.ok) {
            setStatus("Unable to load temple state.");
            return;
          }

          if (typeof st.rows === "number" && typeof st.cols === "number") {
            ROWS = st.rows;
            COLS = st.cols;

            tileSize = computeTileSize(ROWS, COLS);
            ({ startX, startY } = computeGridGeometry(ROWS, COLS, tileSize));

            highlight.setSize(tileSize + 6, tileSize + 6);
            player.setSize(Math.floor(tileSize * 0.5), Math.floor(tileSize * 0.5));
          }

          lives = typeof st.lives === "number" ? st.lives : lives;
          progressRow = typeof st.progress_row === "number" ? st.progress_row : progressRow;

          applyBrokenTilesFromState(st.broken_tiles);

          drawGrid();

          setStatus("");
          syncPlayerFromProgress({ duration: 0 });

          if (progressRow >= ROWS) {
            setStatus("Temple cleared for today.");
            statueLabel.setText("STATUE (reached)");
          }
        } catch (e) {
          setStatus("Error loading temple state.");
        }
      };

      /* ============================================================
         MOVE / STEP LOGIC
         ============================================================ */

      let requestInFlight = false;

      const stepRevealAndMove = async (destCol) => {
        if (requestInFlight) return;

        if (lives <= 0) {
          setStatus("No lives left today.");
          return;
        }

        // Start zone: no reveal
        if (playerRow === ROWS) {
          playerCol = destCol;
          movePlayerTo(playerRow, playerCol);
          updateHud();
          return;
        }

        // Never end on broken: if dest is broken, we should have jumped already.
        if (!canStandOn(playerRow, destCol)) {
          setStatus("No available tile in that direction.");
          flashBlocked();
          return;
        }

        requestInFlight = true;
        setStatus("Stepping…");

        try {
          const rfb = rowFromBottomOfCurrentRow();
          const ans = await apiPost("/temple/step", { row_from_bottom: rfb, col: destCol });

          if (!ans || !ans.ok) {
            setStatus("Step failed.");
            requestInFlight = false;
            return;
          }

          lives = typeof ans.lives === "number" ? ans.lives : lives;
          progressRow = typeof ans.progress_row === "number" ? ans.progress_row : progressRow;

          if (Array.isArray(ans.broken_tiles)) {
            applyBrokenTilesFromState(ans.broken_tiles);
            drawGrid();
          }

          if (ans.result === "already_broken") {
            // This can happen if our local brokenTiles was stale.
            // We must still allow moving backwards/forwards: recompute a jump target and try once.
            setStatus("Tile broken. Searching next available…");
            const dir = destCol > playerCol ? 1 : -1;

            const retryDest = computeJumpDestinationCol(playerRow, playerCol, dir);
            if (retryDest === null) {
              setStatus("No available tile in that direction.");
              flashBlocked();
              requestInFlight = false;
              updateHud();
              return;
            }

            requestInFlight = false;
            // Immediately try again (single retry)
            await stepRevealAndMove(retryDest);
            return;
          }

          if (ans.result === "trap") {
            setStatus(`Trap! Lives left: ${lives}`);

            // Mark as broken locally immediately (visual)
            brokenTiles.add(tileKey(playerRow, destCol));
            hideTile(playerRow, destCol);

            // Snap player onto the tile, then play fall
            playerCol = destCol;
            movePlayerTo(playerRow, playerCol, { duration: 0 });

            await playTrapSequenceAt(playerRow, destCol);

            if (lives <= 0) setStatus("No lives left today. Come back tomorrow.");
            updateHud();
            requestInFlight = false;
            return;
          }

          // safe
          playerCol = destCol;
          movePlayerTo(playerRow, playerCol);
          playSafeFeedback();
          setStatus("");
          updateHud();
          requestInFlight = false;
        } catch (e) {
          setStatus("Error during step.");
          requestInFlight = false;
        }
      };

      // Public entry: attempt lateral move in dir (-1 left, +1 right)
      const tryLateralMove = async (dir) => {
        if (requestInFlight) return;
        if (dir !== -1 && dir !== 1) return;

        // Start zone: just move inside 0..COLS-1
        if (playerRow === ROWS) {
          const next = Math.max(0, Math.min(COLS - 1, playerCol + dir));
          if (next === playerCol) return;
          await stepRevealAndMove(next);
          return;
        }

        const dest = computeJumpDestinationCol(playerRow, playerCol, dir);
        if (dest === null) {
          setStatus("No available tile in that direction.");
          flashBlocked();
          return;
        }

        await stepRevealAndMove(dest);
      };

      // Advance remains the progression mechanic
      const tryAdvance = async () => {
        if (requestInFlight) return;

        if (lives <= 0) {
          setStatus("No lives left today.");
          return;
        }
        if (progressRow >= ROWS) {
          setStatus("Already finished today.");
          return;
        }

        requestInFlight = true;
        setStatus("Advancing…");

        try {
          const ans = await apiPost("/temple/advance", { col: playerCol });
          if (!ans || !ans.ok) {
            setStatus("Advance failed.");
            requestInFlight = false;
            return;
          }

          lives = typeof ans.lives === "number" ? ans.lives : lives;
          progressRow = typeof ans.progress_row === "number" ? ans.progress_row : progressRow;

          if (Array.isArray(ans.broken_tiles)) {
            applyBrokenTilesFromState(ans.broken_tiles);
            drawGrid();
          }

          if (ans.result === "already_broken") {
            setStatus("This tile is already broken. Move sideways first.");
            flashBlocked();
            requestInFlight = false;
            updateHud();
            return;
          }

          if (ans.result === "trap") {
            setStatus(`Trap! Lives left: ${lives}`);

            const attemptRowFromBottom =
              typeof ans.attempt_row === "number" ? ans.attempt_row : progressRow + 1;

            const attemptedGridRow = ROWS - attemptRowFromBottom;
            if (attemptedGridRow >= 0 && attemptedGridRow < ROWS) {
              brokenTiles.add(tileKey(attemptedGridRow, playerCol));
              hideTile(attemptedGridRow, playerCol);
              drawGrid();
              await playTrapSequenceAt(attemptedGridRow, playerCol);
            }

            if (lives <= 0) setStatus("No lives left today. Come back tomorrow.");
            updateHud();
            requestInFlight = false;
            return;
          }

          if (ans.result === "safe") {
            playSafeFeedback();
            setStatus("");

            syncPlayerFromProgress({ duration: 120 });

            if (ans.finished || progressRow >= ROWS) {
              statueLabel.setText("STATUE (reached)");
              setStatus("Temple cleared for today.");
            }

            requestInFlight = false;
            return;
          }

          if (ans.result === "no_lives") setStatus("No lives left today.");
          else if (ans.result === "already_finished") setStatus("Already finished today.");
          else setStatus(`Result: ${ans.result}`);

          syncPlayerFromProgress({ duration: 0 });
          requestInFlight = false;
        } catch (e) {
          setStatus("Error during advance.");
          requestInFlight = false;
        }
      };

      /* ============================================================
         DEV RESET — Press K
         ============================================================ */

      this.input.keyboard.on("keydown-K", async () => {
        if (requestInFlight) return;

        requestInFlight = true;
        setStatus("DEV reset…");

        try {
          const res = await fetch("/temple/dev/reset", {
            method: "POST",
            credentials: "same-origin",
          });

          const json = await res.json();
          if (!json || !json.ok) {
            setStatus("DEV reset failed.");
            requestInFlight = false;
            return;
          }

          await loadState();
          setStatus("DEV reset applied (K).");
        } catch (e) {
          setStatus("DEV reset error.");
        } finally {
          requestInFlight = false;
        }
      });

      /* ============================================================
         INPUT LOOP
         ============================================================ */

      const cursors = this.input.keyboard.createCursorKeys();
      let lastMoveAt = 0;
      const MOVE_COOLDOWN_MS = 140;

      const canMove = () => {
        const now = Date.now();
        if (now - lastMoveAt < MOVE_COOLDOWN_MS) return false;
        lastMoveAt = now;
        return true;
      };

      this.add
        .text(w / 2, 32 + STATUE_ZONE_H, "← → step (server reveal) | ↑ advance | DEV: K reset", {
          fontFamily: "Arial",
          fontSize: "14px",
          color: "#9ca3af",
        })
        .setOrigin(0.5)
        .setDepth(DEPTH_UI);

      this.events.on("update", () => {
        if (!canMove()) return;
        if (requestInFlight) return;

        if (cursors.left.isDown) {
          tryLateralMove(-1);
          return;
        }

        if (cursors.right.isDown) {
          tryLateralMove(1);
          return;
        }

        if (cursors.up.isDown) {
          tryAdvance();
          return;
        }
      });

      /* ============================================================
         FIRST LOAD
         ============================================================ */

      setStatus("Loading temple state…");
      updateHud();
      loadState();
    }
  }

  const config = {
    type: Phaser.AUTO,
    parent: "phaser-temple",
    width: mount.clientWidth || 800,
    height: mount.clientHeight || 500,
    backgroundColor: "#0b1020",
    scene: [TempleScene],
    scale: {
      mode: Phaser.Scale.RESIZE,
      autoCenter: Phaser.Scale.CENTER_BOTH,
    },
  };

  if (window.__TEMPLE_PHASER_GAME__) {
    try {
      window.__TEMPLE_PHASER_GAME__.destroy(true);
    } catch (e) {
      // no-op
    }
  }

  window.__TEMPLE_PHASER_GAME__ = new Phaser.Game(config);
})();
