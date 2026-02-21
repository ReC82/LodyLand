#!/bin/bash
# Script pour remplacer coins/diams dans les fichiers JS

echo "🔧 Fixing JavaScript currency references..."

# Fonction de remplacement
fix_file() {
    local file=$1
    echo "  Processing: $file"
    
    # Remplacements pour les propriétés d'objets
    sed -i 's/\.coins/.shards/g' "$file"
    sed -i 's/\.diams/.diams/g' "$file"
    
    # Remplacements pour les IDs HTML
    sed -i 's/"hud-coins"/"hud-shards"/g' "$file"
    sed -i 's/"hud-diams"/"hud-essence"/g' "$file"
    sed -i 's/hud-coins-/hud-shards-/g' "$file"
    sed -i 's/hud-diams-/hud-essence-/g' "$file"
    
    # Remplacements dans les chaînes de texte (messages utilisateur)
    sed -i 's/ coins/ shards/g' "$file"
    sed -i 's/ diams/ essence/g' "$file"
    
    # Remplacements pour les erreurs
    sed -i 's/not_enough_coins/not_enough_shards/g' "$file"
    sed -i 's/not_enough_diams/not_enough_essence/g' "$file"
    
    # Remplacements pour les prix
    sed -i 's/price_coins/price_shards/g' "$file"
    sed -i 's/price_diams/price_essence/g' "$file"
    
    # Remplacements pour les clés de récompenses
    sed -i 's/coins_awarded/shards_awarded/g' "$file"
}

# Traiter tous les fichiers JS sauf i18n.js
find app/static/GAME_UI/js -name "*.js" ! -name "i18n.js" -type f | while read file; do
    fix_file "$file"
done

echo "✅ Done! Review changes with: git diff app/static/GAME_UI/js/"