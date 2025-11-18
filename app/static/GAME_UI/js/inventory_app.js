/*
  File: static/GAME_UI/js/inventory_app.js
  Purpose: Affichage de l'inventaire joueur (ressources + cartes).
  Notes:
  - http() et $() viennent de common.js / game_app.js
  - currentPlayer est déjà rempli par /api/me via game_app.js
*/

async function loadInventoryResources() {
  const listEl = document.getElementById("invResourcesList");
  const emptyEl = document.getElementById("invResourcesEmpty");
  if (!listEl || !emptyEl) return;

  listEl.innerHTML = "";
  emptyEl.classList.add("d-none");

  try {
    // On récupère :
    // - l'inventaire (quantités)
    // - les définitions de ressources (labels, icônes, etc.)
    const [invRes, defsRes] = await Promise.all([
      http("GET", "/api/inventory"),
      http("GET", "/api/resources"),
    ]);

    if (!invRes.ok) {
      listEl.innerHTML =
        "<div class='inv-empty'>Erreur en chargeant l'inventaire.</div>";
      return;
    }
    if (!defsRes.ok) {
      listEl.innerHTML =
        "<div class='inv-empty'>Erreur en chargeant les ressources.</div>";
      return;
    }

    const inventory = invRes.data || [];
    const defs = defsRes.data || [];

    const defsByKey = {};
    defs.forEach((d) => {
      if (d.key) defsByKey[d.key] = d;
    });

    // On normalise : certains endpoints utilisent qty, d'autres quantity
    const items = inventory.map((raw) => {
      const key = raw.resource || raw.key || raw.code;
      const qty = raw.qty ?? raw.quantity ?? 0;
      return { key, qty };
    });

    const nonEmpty = items.filter((it) => it.qty > 0);
    if (!nonEmpty.length) {
      emptyEl.classList.remove("d-none");
      return;
    }

    nonEmpty.forEach((it) => {
      const def = defsByKey[it.key] || {};
      const label = def.label || it.key;
      const icon = def.icon || null;

      const row = document.createElement("div");
      row.className = "inv-row inv-row-resource";

      row.innerHTML = `
        <div class="inv-main">
          <div class="inv-icon">
            ${
              icon
                ? `<img src="${icon}" alt="${label}">`
                : "📦"
            }
          </div>
          <div>
            <div class="inv-text-label">${label}</div>
            <div class="inv-text-sub">${it.key}</div>
          </div>
        </div>
        <div class="inv-meta">
          Quantité<br><strong>${it.qty}</strong>
        </div>
      `;

      listEl.appendChild(row);
    });
  } catch (err) {
    console.error("[Inventory] loadInventoryResources error:", err);
    listEl.innerHTML =
      "<div class='inv-empty'>Erreur inattendue en chargeant l'inventaire.</div>";
  }
}

async function loadInventoryCards() {
  const listEl = document.getElementById("invCardsList");
  const emptyEl = document.getElementById("invCardsEmpty");
  if (!listEl || !emptyEl) return;

  listEl.innerHTML = "";
  emptyEl.classList.add("d-none");

  try {
    const r = await http("GET", "/api/cards");
    if (!r.ok) {
      listEl.innerHTML =
        "<div class='inv-empty'>Erreur en chargeant les cartes.</div>";
      console.error("[Inventory] /api/cards error:", r);
      return;
    }

    const cards = (r.data || []).filter((c) => (c.owned_qty || 0) > 0);
    if (!cards.length) {
      emptyEl.classList.remove("d-none");
      return;
    }

    cards.forEach((card) => {
      const icon = card.icon || null;
      const label = card.label || card.key;
      const desc = card.description || "";
      const type = card.type || "card";
      const owned = card.owned_qty || 0;

      const row = document.createElement("div");
      row.className = "inv-row inv-row-card";

      row.innerHTML = `
        <div class="inv-main">
          <div class="inv-icon">
            ${
              icon
                ? `<img src="${icon}" alt="${label}">`
                : "🃏"
            }
          </div>
          <div>
            <div class="inv-text-label">${label}</div>
            <div class="inv-text-sub">
              Type : ${type}${desc ? " • " + desc : ""}
            </div>
          </div>
        </div>
        <div class="inv-meta">
          Possédées<br><strong>${owned}</strong>
        </div>
      `;

      listEl.appendChild(row);
    });
  } catch (err) {
    console.error("[Inventory] loadInventoryCards error:", err);
    listEl.innerHTML =
      "<div class='inv-empty'>Erreur inattendue en chargeant les cartes.</div>";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  // HUD déjà géré par game_app.js (appel à /api/me)
  await loadInventoryResources();
  await loadInventoryCards();
});
