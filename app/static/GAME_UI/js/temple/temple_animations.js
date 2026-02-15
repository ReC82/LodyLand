/* File: static/GAME_UI/js/temple/temple_animations.js
   Purpose: Collapse + fall + feedback animations
*/
(function () {
  "use strict";

  window.Temple = window.Temple || {};

  const playSafeFeedback = (scene, s) => {
    if (!s.gfx.highlight) return;
    scene.tweens.add({
      targets: s.gfx.highlight,
      alpha: 0.4,
      yoyo: true,
      repeat: 1,
      duration: 90,
    });
  };

  const flashBlocked = (scene, s) => {
    if (!s.gfx.highlight) return;
    scene.tweens.add({
      targets: s.gfx.highlight,
      alpha: 0.15,
      yoyo: true,
      repeat: 2,
      duration: 80,
    });
  };

  const collapseTileAndHide = async (scene, s, gridRow, col) => {
    const k = window.Temple.grid.tileKey(gridRow, col);
    const fill = s.gfx.tileFillByKey.get(k);
    const border = s.gfx.tileBorderByKey.get(k);
    if (!fill || !border) return;

    await new Promise((resolve) => {
      scene.tweens.add({
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

  const playerTopDownFall = async (scene, s) => {
    const player = s.gfx.player;
    if (!player) return;

    await new Promise((resolve) => {
      scene.tweens.add({
        targets: player,
        x: player.x + 4,
        yoyo: true,
        repeat: 2,
        duration: 40,
        onComplete: () => resolve(),
      });
    });

    await new Promise((resolve) => {
      scene.tweens.add({
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

  const respawnPlayerVisual = (s) => {
    if (!s.gfx.player) return;
    s.gfx.player.setAlpha(1);
    s.gfx.player.setScale(1, 1);
  };

  const playTrapSequenceAt = async (scene, s, gridRow, col) => {
    const pos = window.Temple.grid.tileCenter(s, gridRow, col);
    if (s.gfx.highlight) s.gfx.highlight.setPosition(pos.x, pos.y);
    if (s.gfx.player) {
      s.gfx.player.setPosition(pos.x, pos.y);
      s.gfx.player.setDepth(30);
    }

    await collapseTileAndHide(scene, s, gridRow, col);
    await playerTopDownFall(scene, s);

    respawnPlayerVisual(s);
    await new Promise((resolve) => setTimeout(resolve, 120));
  };

  window.Temple.anim = {
    playSafeFeedback,
    flashBlocked,
    collapseTileAndHide,
    playerTopDownFall,
    respawnPlayerVisual,
    playTrapSequenceAt,
  };
})();
