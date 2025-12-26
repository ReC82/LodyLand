/* File: static/GAME_UI/js/temple/temple_game.js
   Purpose: Bootstrap Phaser + Scene + wiring global
   Notes:
   - Preload: temple_tile + temple_tile_broken + temple_statue + tile_bg
   - Grid uses IMAGE tiles (not rectangles)
   - Statue uses IMAGE (aspect ratio preserved inside a square box)
   - Broken tiles use texture swap (broken tile image) and keep same display size
   - Background uses a repeating tileSprite (responsive-friendly)
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

  class TempleScene extends Phaser.Scene {
    constructor() {
      super("TempleScene");
    }

    preload() {
      // Background tile (same folder as others)
      this.load.image("temple_bg_tile", "/static/assets/img/ui/temple/tile_bg.png");

      // Tiles
      this.load.image("temple_tile", "/static/assets/img/ui/temple/tile.png");
      this.load.image("temple_tile_broken", "/static/assets/img/ui/temple/tile_broken.png");

      // Statue
      this.load.image("temple_statue", "/static/assets/img/ui/temple/statue.png");
    }

    create() {
      const w = this.scale.width;
      const h = this.scale.height;

      const s = window.Temple.state.make();
      this.__templeState = s;

      // Layout constants
      const STATUE_ZONE_H = 120;
      const TILE_SCALE = 0.82;

      const DEPTH_BG = 0;
      const DEPTH_TILES = 10;
      const DEPTH_HIGHLIGHT = 20;
      const DEPTH_PLAYER = 30;
      const DEPTH_UI = 100;

      // Background (repeating tile)
      s.gfx.bg = this.add
        .tileSprite(0, 0, w, h, "temple_bg_tile")
        .setOrigin(0, 0)
        .setDepth(DEPTH_BG);

      this.add
        .text(16, 12, "TEMPLE — STEP 7 (split files)", {
          fontFamily: "Arial",
          fontSize: "16px",
          color: "#ffffff",
        })
        .setDepth(DEPTH_UI);

      // Statue image (keep ratio, fit inside square box)
      const statueX = w / 2;
      const statueY = 48 + STATUE_ZONE_H / 2;

      s.gfx.statue = this.add
        .image(statueX, statueY, "temple_statue")
        .setOrigin(0.5)
        .setDepth(DEPTH_UI);

      // Fit into a square box WITHOUT distortion
      const STATUE_BOX = 96; // adjust if needed (80-120)
      const tex = this.textures.get("temple_statue");
      const src = tex && tex.getSourceImage ? tex.getSourceImage() : null;

      if (src && src.width && src.height) {
        const scale = Math.min(STATUE_BOX / src.width, STATUE_BOX / src.height);
        s.gfx.statue.setScale(scale);
      } else {
        // Fallback (rare): still a square, may distort if we don't know ratio
        s.gfx.statue.setDisplaySize(STATUE_BOX, STATUE_BOX);
      }

      // Optional label (debug)
      s.gfx.statueLabel = this.add
        .text(statueX, statueY + STATUE_BOX / 2 + 14, "STATUE", {
          fontFamily: "Arial",
          fontSize: "14px",
          color: "#9ca3af",
        })
        .setOrigin(0.5)
        .setDepth(DEPTH_UI);

      // HUD
      s.gfx.statusText = this.add
        .text(16, h - 40, "", { fontFamily: "Arial", fontSize: "14px", color: "#9ca3af" })
        .setDepth(DEPTH_UI);

      s.gfx.hudText = this.add
        .text(16, h - 18, "", { fontFamily: "Arial", fontSize: "14px", color: "#9ca3af" })
        .setDepth(DEPTH_UI);

      this.add
        .text(w / 2, 32 + STATUE_ZONE_H, "← → step (server reveal) | ↑ advance | DEV: K reset", {
          fontFamily: "Arial",
          fontSize: "14px",
          color: "#9ca3af",
        })
        .setOrigin(0.5)
        .setDepth(DEPTH_UI);

      // Geometry init (will be recomputed when state arrives if rows/cols differ)
      const padX = 24;
      const padTop = 48 + STATUE_ZONE_H;
      const padBottom = 28;
      const gap = 10;

      const availW = w - padX * 2;
      const availH = h - padTop - padBottom;

      const initialTileSize = window.Temple.grid.computeTileSize(
        availW,
        availH,
        s.rows,
        s.cols,
        gap,
        TILE_SCALE
      );

      s.geom.padX = padX;
      s.geom.padTop = padTop;
      s.geom.padBottom = padBottom;
      s.geom.gap = gap;
      s.geom.availW = availW;
      s.geom.availH = availH;
      s.geom.tileSize = initialTileSize;

      // compute startY based on grid height
      const gridH = s.geom.tileSize * s.rows + gap * (s.rows - 1);
      s.geom.startY = padTop + Math.floor((availH - gridH) / 2);

      // compute startX
      const gg = window.Temple.grid.computeGridGeometry(
        w,
        padTop,
        padBottom,
        padX,
        gap,
        s.rows,
        s.cols,
        s.geom.tileSize
      );
      s.geom.startX = gg.startX;

      // Highlight + Player
      s.gfx.highlight = this.add
        .rectangle(0, 0, s.geom.tileSize + 6, s.geom.tileSize + 6)
        .setOrigin(0.5)
        .setStrokeStyle(3, 0xfbbf24, 1)
        .setDepth(DEPTH_HIGHLIGHT);

      s.gfx.player = this.add
        .rectangle(0, 0, Math.floor(s.geom.tileSize * 0.5), Math.floor(s.geom.tileSize * 0.5), 0x22c55e)
        .setOrigin(0.5)
        .setDepth(DEPTH_PLAYER);

      // Ensure gfx containers exist
      s.gfx.gridObjects = s.gfx.gridObjects || [];
      s.gfx.tilesByKey = s.gfx.tilesByKey || new Map();

      // Callbacks used by movement module
      // Here: "broken" => swap texture (same size), not hide
      s._hideTile = (_scene, _s, gridRow, col) => {
        const k = window.Temple.grid.tileKey(gridRow, col);
        const tile = _s.gfx.tilesByKey.get(k);
        if (!tile) return;

        tile.setTexture("temple_tile_broken");
        tile.setDisplaySize(_s.geom.tileSize, _s.geom.tileSize);
      };

      s._drawGrid = (_scene, _s) => {
        // destroy old
        for (const obj of _s.gfx.gridObjects) obj.destroy();
        _s.gfx.gridObjects.length = 0;
        _s.gfx.tilesByKey.clear();

        const tSize = _s.geom.tileSize;

        for (let r = 0; r < _s.rows; r++) {
          for (let c = 0; c < _s.cols; c++) {
            const key = window.Temple.grid.tileKey(r, c);
            const { x, y } = window.Temple.grid.tileCenter(_s, r, c);

            const tile = _scene.add
              .image(x, y, "temple_tile")
              .setOrigin(0.5)
              .setDepth(DEPTH_TILES);

            // Fit to computed tileSize
            tile.setDisplaySize(tSize, tSize);

            _s.gfx.tilesByKey.set(key, tile);
            _s.gfx.gridObjects.push(tile);

            // Broken tiles: swap texture (same size)
            if (_s.brokenTiles.has(key)) {
              tile.setTexture("temple_tile_broken");
              tile.setDisplaySize(tSize, tSize);
            }
          }
        }
      };

      s._onServerStateLoaded = (_scene, _s) => {
        // recompute tileSize & geometry if rows/cols updated by server
        const newTileSize = window.Temple.grid.computeTileSize(
          _s.geom.availW,
          _s.geom.availH,
          _s.rows,
          _s.cols,
          _s.geom.gap,
          TILE_SCALE
        );

        _s.geom.tileSize = newTileSize;

        const gridH2 = newTileSize * _s.rows + _s.geom.gap * (_s.rows - 1);
        _s.geom.startY = _s.geom.padTop + Math.floor((_s.geom.availH - gridH2) / 2);

        const gg2 = window.Temple.grid.computeGridGeometry(
          w,
          _s.geom.padTop,
          _s.geom.padBottom,
          _s.geom.padX,
          _s.geom.gap,
          _s.rows,
          _s.cols,
          newTileSize
        );
        _s.geom.startX = gg2.startX;

        // resize highlight/player
        _s.gfx.highlight.setSize(newTileSize + 6, newTileSize + 6);
        _s.gfx.player.setSize(Math.floor(newTileSize * 0.5), Math.floor(newTileSize * 0.5));
      };

      // Keep background sized correctly on RESIZE (does not change any existing gameplay logic)
      this.scale.on("resize", (gameSize) => {
        const nw = gameSize.width;
        const nh = gameSize.height;

        if (s.gfx.bg) {
          s.gfx.bg.setSize(nw, nh);
        }

        // Keep HUD anchored to bottom like before (only positions, no logic changes)
        if (s.gfx.statusText) s.gfx.statusText.setPosition(16, nh - 40);
        if (s.gfx.hudText) s.gfx.hudText.setPosition(16, nh - 18);
      });

      // DEV reset
      this.input.keyboard.on("keydown-K", async () => {
        if (s.requestInFlight) return;
        s.requestInFlight = true;
        window.Temple.ui.setStatus(s, "DEV reset…");
        try {
          const json = await window.Temple.api.devReset();
          if (!json || !json.ok) {
            window.Temple.ui.setStatus(s, "DEV reset failed.");
            s.requestInFlight = false;
            return;
          }
          await window.Temple.movement.loadState(this, s);
          window.Temple.ui.setStatus(s, "DEV reset applied (K).");
        } catch (e) {
          window.Temple.ui.setStatus(s, "DEV reset error.");
        } finally {
          s.requestInFlight = false;
        }
      });

      // Input loop (cooldown)
      const cursors = this.input.keyboard.createCursorKeys();
      let lastMoveAt = 0;
      const MOVE_COOLDOWN_MS = 140;

      const canMove = () => {
        const now = Date.now();
        if (now - lastMoveAt < MOVE_COOLDOWN_MS) return false;
        lastMoveAt = now;
        return true;
      };

      this.events.on("update", () => {
        if (!canMove()) return;
        if (s.requestInFlight) return;

        if (cursors.left.isDown) {
          window.Temple.movement.tryLateralMove(this, s, -1);
          return;
        }

        if (cursors.right.isDown) {
          window.Temple.movement.tryLateralMove(this, s, 1);
          return;
        }

        if (cursors.up.isDown) {
          window.Temple.movement.tryAdvance(this, s);
          return;
        }

        if (cursors.down && cursors.down.isDown && window.Temple.movement.tryMoveDown) {
          window.Temple.movement.tryMoveDown(this, s);
          return;
        }
      });

      // First load
      window.Temple.ui.setStatus(s, "Loading temple state…");
      window.Temple.ui.updateHud(s);
      window.Temple.movement.loadState(this, s);
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
