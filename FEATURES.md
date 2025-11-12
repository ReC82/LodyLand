# 🌴 LodyLand — Core Features Overview

> Version: MVP+ (Phase gameplay backend)  
> Author: Lloyd Malfliet  
> Last updated: 2025-11-12  

---

## 🎯 Vision Générale
Le joueur débarque sur une île vierge.  
Il commence sans outils et doit **collecter des ressources naturelles**, **crafter des outils**, **débloquer de nouvelles zones et bâtiments**, et **faire progresser son personnage** à travers des niveaux, des quêtes et des cartes spéciales.

Le jeu repose sur trois grands piliers :

1. **Collection & Crafting**
2. **Économie & Progression**
3. **Cartes & Boosts**

---

## 🪓 1. Collecte de Ressources

### Ressources de base (sans outil)
- **Branchages (`twig`)**
- **Feuilles de palmier (`palm_leaf`)**
- **Cailloux (`stone`)**

Ces ressources sont collectables dès le départ, avec un cooldown court (5–8 s).  
Elles permettent de crafter les premiers outils (ex. corde, hache).

### Ressources avancées
- **Bois de palmier (`wood`)**
  - Nécessite la carte **“Hache de palmier” (`card_palm_axe`)**
  - Cooldown plus long, yield et XP supérieurs.
- D’autres viendront plus tard (métal, poisson, argile, etc.)

### Données associées à chaque ressource
- `base_yield_qty` — quantité de ressource obtenue par collecte  
- `base_yield_xp` — XP gagnée  
- `base_cooldown` — durée avant nouvelle collecte  
- `requires_card_key` — carte nécessaire pour débloquer la ressource  
- `min_level` — niveau minimum requis  

---

## 💰 2. Économie & Monnaies

### Monnaies principales
- **Coins** — monnaie standard (vente de ressources, quêtes, coffres)  
- **Diams** — monnaie rare (récompenses spéciales, boutique premium)

### Système de vente
- Endpoint `/api/sell`  
- Le joueur peut vendre ses ressources contre des coins selon un prix fixe (modifiable).  
- Les boosts de type `sell_price` peuvent augmenter la valeur de vente.

### Système d’achat (Shop)
- Premier shop débloqué à un certain niveau (ex. niveau 3)
- Permet d’acheter :
  - des **cartes** (boosts, accès, bâtiments)
  - des **items** spéciaux (si craft impossible)
- Les prix peuvent être en coins, diams, ou ressources.

---

## 🗺️ 3. Tuiles et Déblocage

### Fonctionnement général
- Le joueur commence avec **une tuile** (point de collecte).  
- Il peut **débloquer** de nouvelles tuiles (`/api/tiles/unlock`) pour accéder à d’autres ressources.  
- Chaque ressource a son propre ensemble de tuiles.

### Règles
- Certaines tuiles nécessitent un **niveau minimal** ou une **carte spécifique**.
- Il existe un **coût croissant** pour chaque nouvelle tuile d’un même type :
  - 1re gratuite, 2e → 5 coins, 3e → 10 coins, etc.
- Chaque niveau de joueur limite le **nombre total de tuiles** qu’il peut posséder :
  - Niveau 0 → 2 tiles max  
  - Niveau 1 → 4 tiles  
  - Niveau 2 → 6 tiles  
  - etc.

---

## ⚙️ 4. Crafting System

### Principe
Les ressources collectées servent à **fabriquer des items** (outils, matériaux, équipements…).

### Données de craft
- `item_key` — identifiant unique de l’item  
- `inputs` — dictionnaire des ressources requises  
- `output_qty` — quantité produite  
- `craft_seconds` — durée de craft  
- `requires_building_key` — ex. `craft_table`, `forge`  
- `min_level` — niveau minimal pour crafter l’item

### Exemple de recettes
| Item | Entrées | Bâtiment | Durée | Effet |
|------|----------|-----------|--------|-------|
| `rope` | 3× palm_leaf | craft_table | 60 s | Matériau |
| `wooden_axe` | 1× twig + 1× rope + 1× stone | craft_table | 300 s | Permet la collecte du bois |
| `raft` | 10× wood + 2× rope | shipyard | 2 h | Débloque la pêche |

### Améliorations possibles
- Système de **“craft slots”** (1 au départ → cartes permettent d’en débloquer plus)
- Système de **“craft speed boost”** (effets de cartes)
- Système de **file d’attente / jobs de craft** avec fin différée :
  - `CraftJob` → `status: running/done/claimed`
  - `/api/craft` pour lancer, `/api/craft/claim` pour récupérer

---

## 🎴 5. Cartes (Card System)

### But
Les cartes ajoutent de la **profondeur stratégique** :
- Débloquer de nouvelles ressources, bâtiments ou mécaniques
- Accorder des **boosts** (XP, cooldown, sell price, craft speed…)
- Être **upgradables** et **échangeables**

### Données d’une carte
| Champ | Description |
|--------|--------------|
| `key` | identifiant unique |
| `display_name` | nom affiché |
| `rarity` | basic / silver / gold |
| `tradable` | booléen |
| `max_level` | niveau max de la carte |
| `base_cost_json` | coût d’achat |
| `type` | unlock / boost / building / etc. |
| `available_quantity` | stock (None = infini) |
| `unlock_condition` | conditions pour pouvoir l’acheter / l’utiliser |

### Types de cartes
- **Unlock** → débloque une ressource ou un bâtiment (ex. “Hache de palmier”)  
- **Boost** → modifie une statistique (ex. cooldown × 0.9, sell × 1.2)  
- **Building Access** → donne accès à un bâtiment (shop, forge, craft table)  
- **Upgrade** → améliore un bâtiment (ex. craft table lvl 2 → +1 slot)

### Effets possibles
| Cible (`target`) | Statistique (`stat`) | Opération (`op`) | Exemple |
|------------------|----------------------|------------------|----------|
| `resource` | `cooldown` | `mul` | cooldown × 0.9 |
| `resource` | `yield_qty` | `add` | +1 item par récolte |
| `sell` | `sell_price` | `mul` | +20 % sur prix de vente |
| `craft` | `craft_speed` | `mul` | craft × 0.8 |
| `craft` | `craft_slots` | `add` | +1 slot |
| `global` | `xp_gain` | `mul` | XP × 1.1 |

---

## 🧭 6. Progression & Niveaux

### XP & Level
- Chaque collecte rapporte de l’XP.
- Le niveau détermine :
  - le nombre max de tiles,
  - l’accès à certaines ressources ou cartes,
  - le déblocage de nouvelles zones ou bâtiments.

### Barème de niveau
- Défini dans `progression.py`  
  (ex: `[0, 10, 25, 50, 100, 200, 400, 800, ...]`)

### Effets de niveau
| Niveau | Max Tiles | Nouveautés |
|---------|------------|------------|
| 0 | 2 | ressources basiques |
| 1 | 4 | shop débloqué |
| 2 | 6 | carte “forge” dispo |
| 3 | 8 | quêtes hebdo |
| 5 | 10 | carte “village” dispo |

---

## 🎁 7. Daily Chest (Coffre quotidien)

### Fonctionnement actuel
- `/api/daily`
- Donne des coins + XP bonus
- Vérifie si le joueur a déjà réclamé dans la journée (via `last_daily`)

### Évolution prévue
- **Streak system** :
  - Bonus cumulatif si le joueur se connecte plusieurs jours d’affilée  
  - 7 jours → bonus de diams  
  - 15 jours → carte rare  
  - 30 jours → boost spécial
- Sauvegardé dans `daily_streak` dans la table `players`.

---

## 📜 8. Quêtes (Daily / Weekly)

### MVP
- Une quête journalière simple : “Collecter X ressources Y”
- Récompense : XP + coins
- Endpoints :
  - `GET /api/quests/today`
  - `POST /api/quests/claim`

### Évolution
- Système hebdomadaire (bonus plus élevés)
- Quêtes liées à des événements
- Suivi de progression par ressource

---

## 🏝️ 9. Map & Expansion

### Principe
- L’île du joueur grandit au fil du temps.
- Chaque expansion débloque plus d’espace de collecte.

### Données
- `map_size` dans `players` (nombre de tiles max)
- `/api/map/expand` : consomme coins/diams pour augmenter `map_size`
- Cartes “Land Expansion” peuvent réduire le coût d’expansion.

---

## 🧠 10. Backend et Structure Technique

### Technologies
- **Flask 3.1** (Python 3.12)
- **SQLAlchemy 2.0 + Alembic**
- **SQLite** (dev) → PostgreSQL (prod possible)
- **pytest** pour les tests unitaires
- **Bootstrap + Vanilla JS** pour la mini-UI actuelle

### Principaux modules
| Module | Rôle |
|--------|------|
| `app/__init__.py` | Routes principales API |
| `app/models.py` | Joueurs, tuiles, stocks |
| `app/models_content.py` | Définitions statiques (ressources, cartes, recettes) |
| `app/progression.py` | Niveaux, XP, seuils |
| `app/crafting.py` | Logique de craft et jobs |
| `tests/test_api.py` | Couverture de test des endpoints |

---

## 🧩 11. Roadmap technique

| Étape | Objectif | Statut |
|--------|-----------|---------|
| ✅ Daily Chest MVP | Coins & XP une fois par jour | done |
| ✅ XP & Level system | Gain XP, seuils, progress bar | done |
| ✅ Inventaire visuel | Stock de ressources affiché dans UI | done |
| ⚙️ Yields/cooldowns par ressource | Paramétrés via `ResourceDef` | in progress |
| ⏳ Unlock cost scaling | Coût croissant des tuiles | planned |
| ⏳ Craft system (recipes + jobs) | Création d’objets avec durée | planned |
| ⏳ Card system (unlock + boosts) | Déblocage et effets cumulables | planned |
| ⏳ Quêtes journalières | Simple objectif + récompense | planned |
| ⏳ Map expansion | Déblocage de nouvelles zones | planned |
| ⏳ Shop cartes/items | Débloqué niveau 3 | planned |
| ⏳ UI gameplay | Interface graphique complète | later |
| ⏳ Online save & multiplayer sync | Cloud save & events | future phase |

---

## 🧭 12. À venir (game design évolutif)
- **Streak du coffre quotidien** (7 j / 15 j / 30 j bonus)  
- **Système météo** (impact sur ressources)  
- **PNJ / Quêtes scénarisées**  
- **Événements saisonniers** (Halloween, Noël, etc.)  
- **Système de “village” partagé / leaderboard**  
- **Support mobile / PWA**  

---

## 💾 Maintenance du contenu
Tout le contenu du jeu (ressources, cartes, recettes, prix, conditions) sera centralisé dans des fichiers YAML sous `/content/` :

content/
├── resources.yml
├── cards.yml
├── recipes.yml
├── prices.yml
├── quests.yml


Ces fichiers seront chargés automatiquement à chaque lancement (ou via `/api/dev/reseed`).

---

## 📚 Notes de design
- Chaque ressource ou carte doit pouvoir être **modifiée sans toucher au code**.  
- Les effets et conditions doivent être **combinables** et **scalables** (niveau, rareté, multiplicateurs).  
- Les actions clés du joueur doivent toutes passer par des endpoints REST (`/api/...`) pour rester testables.

---

> 💡 **Philosophie du projet :**
> - Code minimal → données puissantes  
> - Un joueur = une île vivante qui évolue  
> - Tout doit être testable, extensible et amusant à développer 🌴

---

