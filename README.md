![Tests](https://github.com/ReC82/LodyLand/actions/workflows/tests.yml/badge.svg)
# 🌾 LodyLand — Clicker Game API + UI

Un mini-jeu web inspiré de **Sunflower Land**, construit en Flask (Python) avec une base SQLite + interface HTML/JS minimaliste.  
Le joueur récolte des ressources, gagne de l’XP, monte de niveau et débloque des tuiles supplémentaires.

---

## 🚀 Fonctionnalités actuelles

- [x] Création de joueur (`/api/player`, `/api/register`)
- [x] Auth simple par cookie (`player_id`)
- [x] Déblocage de tuiles (`/api/tiles/unlock`)
- [x] Collecte avec cooldown (10s)
- [x] Gain d’XP et de niveaux
- [x] Inventaire de ressources
- [x] Interface Debug UI (Bootstrap)
- [x] Tests unitaires (pytest + GitHub Actions)

---

## 🧩 Structure du projet

LodyLand/
├── app/
│ ├── init.py # Routes Flask (API)
│ ├── db.py # Base SQLAlchemy + session
│ ├── models.py # Player, Tile, ResourceStock
│ ├── progression.py # Niveau et XP
│ └── static/ui/ # Interface debug (HTML, JS, CSS)
├── tests/
│ └── test_api.py # Tests pytest
├── alembic/ # Migrations
├── requirements.txt
├── run.py
└── README.md


---

## 🧠 Roadmap

| Étape | Objectif | Statut |
|-------|-----------|--------|
| 1 | Backend Flask + DB | ✅ |
| 2 | XP & cooldowns | ✅ |
| 3 | UI basique Bootstrap | ✅ |
| 4 | Inventaire visuel | ✅ |
| 5 | Toast notifications (succès / erreur / level up) | 🚧 |
| 6 | Auth + leaderboard | 🔜 |
| 7 | Village / mini-jeu | 🔜 |

---

## 🧪 Tests

Exécuter les tests localement :
```bash
pytest -q

CI/CD GitHub Actions : .github/workflows/tests.yml

# 1. Créer l'environnement
python -m venv .venv
.venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Lancer l'application
python run.py

Ouvre http://127.0.0.1:8000/ui

🧱 Technologies

Backend : Flask + SQLAlchemy + Alembic

Frontend : HTML, Bootstrap 5, Vanilla JS

Tests : Pytest + GitHub Actions

Database : SQLite (dev)

© Crédit

Projet pédagogique by Lloyd Malfliet – 2025
Inspiré de Sunflower Land 🌻
