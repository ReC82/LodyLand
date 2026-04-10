# 🎨 Guide artiste – LodyLand (version Git en ligne de commande)

## Objectif

Ajouter des fichiers graphiques au projet avec Git.

## Outils à installer

* Git
* VSCode ou un éditeur de fichiers
* Un logiciel de dessin/export PNG/SVG

---

## 1. Cloner le projet

Ouvrir un terminal dans le dossier où tu veux récupérer le projet, puis lancer :

```bash
git clone https://github.com/ReC82/LodyLand.git
cd LodyLand
```

---

## 2. Créer une branche de travail

Pour le logo :

```bash
git checkout -b artist/logo-v1
```

---

## 3. Ajouter les fichiers

Placer les fichiers dans :

```text
assets/ui/logo/
```

Exemples :

* `logo_v1.png`
* `logo_v1.svg`

---

## 4. Vérifier l’état du projet

```bash
git status
```

Cette commande montre les fichiers ajoutés ou modifiés.

---

## 5. Ajouter les fichiers au commit

```bash
git add .
```

---

## 6. Créer le commit

```bash
git commit -m "Ajout logo v1"
```

---

## 7. Envoyer la branche sur GitHub

```bash
git push origin artist/logo-v1
```

---

## 8. Créer la Pull Request

Après le push :

* ouvrir GitHub dans le navigateur
* GitHub proposera souvent un bouton **Compare & pull request**
* cliquer dessus
* créer la Pull Request

Titre conseillé :

```text
Logo v1
```

Description conseillée :

```text
Ajout de la première version du logo dans assets/ui/logo/.
Formats fournis : PNG et SVG.
```

---

## Commandes utiles

Voir l’état du projet :

```bash
git status
```

Voir la branche actuelle :

```bash
git branch
```

---

## Règles importantes

* Ne jamais travailler sur `main`
* Travailler uniquement dans les dossiers `assets/...`
* Faire une branche par tâche
* Faire une Pull Request quand le travail est prêt

---

## En cas de doute

Ne pas utiliser de commandes Git non comprises, et demander avant d’aller plus loin.
