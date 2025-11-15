// static/game/main.js - Version agrandie + responsive
class BootScene extends Phaser.Scene {
  constructor() { super('Boot'); }

  preload() {
    // Tiles de base (remplace par Craftpix plus tard)
    this.load.image('grass', '/static/img/resources/default.png');
    this.load.image('sand', '/static/img/resources/small_stone.png'); // sable

    // Ressources (tes assets existants)
    this.load.image('branch', '/static/img/resources/branch.png');
    this.load.image('palm_leaf', '/static/img/resources/palm_leaf.png');
    this.load.image('wood', '/static/img/resources/oak_wood_log.png');
    this.load.image('stone', '/static/img/resources/small_stone.png');
  }

  create() {
    this.scene.start('Game');
  }
}

class GameScene extends Phaser.Scene {
  constructor() { super('Game'); }

  create() {
    // === GRILLE AGRANDIE ===
    this.gridSize = 6;           // 6x6 = 36 tuiles
    this.tileSize = 120;         // Tuiles XXL
    this.offsetX = 60;           // Centré gauche
    this.offsetY = 60;           // Centré haut

    this.tiles = [];

    // === CRÉATION GRILLE ===
    for (let y = 0; y < this.gridSize; y++) {
      for (let x = 0; x < this.gridSize; x++) {
        const worldX = this.offsetX + x * this.tileSize;
        const worldY = this.offsetY + y * this.tileSize;

        // Tile de base (herbe ou sable aléatoire)
        const tileType = Math.random() > 0.7 ? 'sand' : 'grass';
        const tileSprite = this.add.image(worldX, worldY, tileType)
          .setInteractive({ useHandCursor: true })
          .setScale(1.1)  // ← un peu plus grand
          .setData('x', x)
          .setData('y', y)
          .setData('cooldown', false);

        // Icône ressource (plus grande)
        const resources = ['branch', 'palm_leaf', 'wood', 'stone'];
        const resKey = Phaser.Utils.Array.GetRandom(resources);
        const icon = this.add.image(worldX, worldY - 10, resKey)
          .setScale(0.8)  // ← icônes plus visibles
          .setDepth(1);   // ← au-dessus de la tile

        tileSprite.setData('resource', resKey);
        tileSprite.setData('icon', icon);

        // Clic → récolte
        tileSprite.on('pointerdown', () => this.harvestTile(tileSprite));

        this.tiles.push(tileSprite);
      }
    }

    // === ANIMATIONS DE FOND (vagues légères) ===
    this.cameras.main.setBackgroundColor('#87CEEB');
    this.add.rectangle(0, 0, 2000, 80, 0x4ECDC4).setOrigin(0).setDepth(-1); // mer

    // === CHARGEMENT ÉTAT JOUEUR ===
    this.refreshPlayerState();
    this.events.on('refreshPlayer', this.refreshPlayerState, this);
  }

  /** Récolte une tuile avec feedback visuel */
  harvestTile(tileSprite) {
    if (tileSprite.getData('cooldown')) return;

    const res = tileSprite.getData('resource');
    const icon = tileSprite.getData('icon');

    // === ANIMATION RÉCOLTE (gros bounce) ===
    this.tweens.add({
      targets: [tileSprite, icon],
      scale: 1.4,                // ← PLUS GROS
      duration: 150,
      yoyo: true,
      ease: 'Bounce.easeOut'
    });

    // === PARTIicules étoiles ===
    for (let i = 0; i < 5; i++) {
      const star = this.add.circle(0, 0, 4, 0xFFD700)
        .setPosition(tileSprite.x, tileSprite.y);
      this.tweens.add({
        targets: star,
        alpha: 0,
        y: '-=50',
        scale: 0,
        duration: 800,
        onComplete: () => star.destroy()
      });
    }

    // === API Flask ===
    fetch('/api/collect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resource: res })
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          // Cooldown visuel
          icon.setAlpha(0.4);
          tileSprite.setTint(0x888888);
          tileSprite.setData('cooldown', true);

          // Reset cooldown (selon ressource)
          const cooldown = data.cooldown || 5000;
          this.time.delayedCall(cooldown, () => {
            icon.setAlpha(1);
            tileSprite.clearTint();
            tileSprite.setData('cooldown', false);
          });

          // Refresh UI
          this.events.emit('refreshPlayer');
        }
      })
      .catch(err => console.error('Erreur récolte:', err));
  }

  /** Met à jour l'overlay UI */
  refreshPlayerState() {
    fetch('/api/state')
      .then(r => r.json())
      .then(state => {
        // Nom + XP
        document.getElementById('player-name').textContent = state.player?.name || '—';
        const xp = state.player?.xp || 0;
        const next = state.player?.next_xp || 100;
        const pct = Math.min((xp / next) * 100, 100);
        document.getElementById('xp-bar').style.width = `${pct}%`;
        document.getElementById('xp-text').textContent = `XP: ${xp} / ${next}`;

        // Inventaire
        const invBox = document.getElementById('inventory');
        invBox.innerHTML = '';
        (state.inventory || []).forEach(item => {
          const div = document.createElement('div');
          div.className = 'col text-center p-1';
          div.innerHTML = `
            <img src="/static/img/resources/${item.resource}.png" 
                 width="36" height="36" class="mb-1">
            <small class="fw-bold">${item.qty}</small>
          `;
          invBox.appendChild(div);
        });

        // Coffre journalier
        const dailyBtn = document.getElementById('daily-btn');
        const feedback = document.getElementById('daily-feedback');
        if (state.player?.last_daily === new Date().toISOString().split('T')[0]) {
          dailyBtn.disabled = true;
          dailyBtn.textContent = 'Déjà réclamé';
          feedback.textContent = 'Reviens demain !';
        } else {
          dailyBtn.disabled = false;
          dailyBtn.textContent = 'Coffre journalier';
          feedback.textContent = '';
          dailyBtn.onclick = () => this.claimDaily();
        }
      })
      .catch(err => console.error('Erreur état:', err));
  }

  claimDaily() {
    fetch('/api/daily', { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          // Animation récompense
          const coinsText = this.add.text(400, 300, `+${data.reward} coins!`, {
            fontSize: '48px',
            color: '#FFD700',
            fontStyle: 'bold'
          }).setOrigin(0.5);
          this.tweens.add({
            targets: coinsText,
            alpha: 0,
            scale: 1.5,
            duration: 2000,
            onComplete: () => coinsText.destroy()
          });
          this.events.emit('refreshPlayer');
        }
      });
  }
}

// === CONFIG RESPONSIVE ===
const config = {
  type: Phaser.AUTO,
  parent: 'game-container',
  width: Math.min(window.innerWidth * 0.75, 900),   // Max 900px
  height: Math.min(window.innerHeight * 0.85, 700), // Max 700px
  backgroundColor: '#87CEEB',
  scene: [BootScene, GameScene],
  scale: {
    mode: Phaser.Scale.RESIZE,  // ← RESPONSIVE AUTOMATIQUE
    autoCenter: Phaser.Scale.CENTER_BOTH
  }
};

new Phaser.Game(config);