// static/GAME_UI/js/village/village_pedro.js
// Pedro — Master Builder : deposit, start, construction progress bars

/* global http */

document.addEventListener("DOMContentLoaded", () => {
  setupDepositButtons();
  setupStartButtons();
  setupConstructionBars();
});

// ============================================================
// Deposit
// ============================================================
function setupDepositButtons() {
  document.querySelectorAll(".pb-deposit-btn").forEach((btn) => {
    btn.addEventListener("click", () => handleDeposit(btn));
  });

  // Quand on change la ressource sélectionnée, mettre qty max = min(stock, manquant)
  document.querySelectorAll(".pb-mat-select").forEach((select) => {
    const card     = select.closest("[data-building-key]");
    const qtyInput = card?.querySelector(".pb-qty-input");
    function updateMax() {
      const opt   = select.options[select.selectedIndex];
      if (!opt || !qtyInput) return;
      const stock   = parseInt(opt.dataset.playerStock || "0");
      const req     = parseInt(opt.dataset.required    || "0");
      const banked  = parseInt(opt.dataset.banked      || "0");
      const maxDeposit = Math.min(stock, req - banked);
      qtyInput.max   = maxDeposit;
      qtyInput.value = Math.max(1, Math.min(parseInt(qtyInput.value || "1"), maxDeposit));
    }
    select.addEventListener("change", updateMax);
    updateMax(); // initialiser au chargement
  });
}

async function handleDeposit(btn) {
  const card         = btn.closest("[data-building-key]");
  const buildingKey  = card.dataset.buildingKey;
  const select       = card.querySelector(".pb-mat-select");
  const qtyInput     = card.querySelector(".pb-qty-input");
  const resource     = select?.value;
  const qty          = parseInt(qtyInput?.value || "0", 10);

  if (!resource || qty <= 0) return;

  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = "…";

  try {
    const r = await http("POST", "/api/village/pedro/deposit", {
      building_key: buildingKey,
      resource,
      qty,
    });

    if (!r.ok) {
      alert("Erreur : " + ((r.data || {}).error || "?"));
      btn.disabled = false;
      btn.textContent = old;
      return;
    }

    const { banked_materials, status, deposited } = r.data;

    // Réactiver le bouton
    btn.disabled    = false;
    btn.textContent = old;

    // Mettre à jour le stock affiché (déduit localement)
    const stockEl = card.querySelector(`.pb-player-stock[data-mat="${resource}"]`);
    if (stockEl) {
      const newStock = Math.max(0, parseInt(stockEl.textContent || "0") - (deposited ?? qty));
      stockEl.textContent = newStock;
      stockEl.style.color = newStock > 0 ? "#86efac" : "#f87171";
      // Mettre à jour le data-player-stock dans le select
      const opt = card.querySelector(`.pb-mat-select option[value="${resource}"]`);
      if (opt) opt.dataset.playerStock = newStock;
    }

    // Mettre à jour les barres de progression dans la carte
    updateMaterialBars(card, banked_materials);

    // Mettre à jour le select (retirer les options pleines)
    refreshMatSelect(card, banked_materials);

    // Si tous réunis → passer le statut à "pending_construction"
    if (status === "pending_construction") {
      setCardStatus(card, "pending_construction");
    }

  } catch (e) {
    console.error("[pedro] deposit error", e);
    alert("Erreur réseau.");
    btn.disabled = false;
    btn.textContent = old;
  }
}

function updateMaterialBars(card, banked) {
  card.querySelectorAll(".pb-mat-bar").forEach((bar) => {
    const mat    = bar.dataset.mat;
    const counter = card.querySelector(`.pb-mat-counter[data-mat="${mat}"]`);
    const parts  = (counter?.textContent || "").split("/");
    const req    = parseInt(parts[1] || "0");
    const got    = parseInt(banked[mat] || 0);
    const pct    = req > 0 ? Math.min(100, Math.round((got / req) * 100)) : 0;

    bar.style.width      = pct + "%";
    bar.style.background = pct >= 100 ? "#22c55e" : "#facc15";
    if (counter) counter.textContent = `${got} / ${req}`;
  });
}

function refreshMatSelect(card, banked) {
  const select = card.querySelector(".pb-mat-select");
  if (!select) return;
  select.querySelectorAll("option").forEach((opt) => {
    const mat = opt.value;
    const req = parseInt(opt.dataset.required || "0");
    const got = parseInt(banked[mat] || 0);
    opt.dataset.banked = got;
    if (got >= req) {
      opt.remove();
    } else {
      const stock = parseInt(opt.dataset.playerStock || "0");
      opt.textContent = `${mat.replace(/_/g, " ")} — déposé ${got}/${req} — stock: ${stock}`;
    }
  });
  // Recalculer le max sur l'option désormais sélectionnée
  const qtyInput = card.querySelector(".pb-qty-input");
  const opt = select.options[select.selectedIndex];
  if (opt && qtyInput) {
    const stock  = parseInt(opt.dataset.playerStock || "0");
    const req    = parseInt(opt.dataset.required    || "0");
    const banked2 = parseInt(opt.dataset.banked     || "0");
    const maxDep = Math.min(stock, req - banked2);
    qtyInput.max   = maxDep;
    qtyInput.value = Math.max(1, Math.min(parseInt(qtyInput.value || "1"), maxDep));
  }
  // Cacher le formulaire seulement si vraiment tout est déposé
  if (select.options.length === 0) {
    const form = card.querySelector(".pb-deposit-form");
    if (form) form.style.display = "none";
  }
}

function setCardStatus(card, status) {
  const label = card.querySelector(".pb-status");
  if (label) label.dataset.status = status;

  const actionsDiv = card.querySelector(".vs-offer-actions");
  if (!actionsDiv) return;

  if (status === "pending_construction") {
    if (label) label.textContent = label.dataset.status; // sera traduit côté serveur au reload
    // Remplacer le bouton disabled par le bouton "Lancer"
    actionsDiv.innerHTML = `
      <button type="button" class="btn btn-sm btn-success pb-start-btn"
              data-building-key="${card.dataset.buildingKey}">
        Lancer la construction
      </button>`;
    setupStartButtons(); // rebind
  }
}

// ============================================================
// Start construction
// ============================================================
function setupStartButtons() {
  document.querySelectorAll(".pb-start-btn").forEach((btn) => {
    btn.addEventListener("click", () => handleStart(btn));
  });
}

async function handleStart(btn) {
  const card        = btn.closest("[data-building-key]");
  const buildingKey = card.dataset.buildingKey;

  btn.disabled = true;
  btn.textContent = "…";

  try {
    const r = await http("POST", "/api/village/pedro/start", { building_key: buildingKey });
    if (!r.ok) {
      alert("Erreur : " + ((r.data || {}).error || "?"));
      btn.disabled = false;
      btn.textContent = "Lancer la construction";
      return;
    }

    // Recharger la page pour afficher la barre de progression de construction
    location.reload();

  } catch (e) {
    console.error("[pedro] start error", e);
    alert("Erreur réseau.");
    btn.disabled = false;
  }
}

// ============================================================
// Construction progress bars (temps restant)
// ============================================================
function setupConstructionBars() {
  document.querySelectorAll(".pb-construction-bar").forEach((bar) => {
    const endsAt   = bar.dataset.endsAt;
    const duration = parseInt(bar.dataset.duration || "0", 10);
    if (!endsAt || !duration) return;

    const card     = bar.closest("[data-building-key]");
    const label    = card?.querySelector(".pb-construction-remaining");
    const endMs    = new Date(endsAt).getTime();

    function tick() {
      const nowMs     = Date.now();
      const remaining = Math.max(0, endMs - nowMs);
      const elapsed   = duration * 1000 - remaining;
      const pct       = Math.min(100, Math.round((elapsed / (duration * 1000)) * 100));

      bar.style.width = pct + "%";
      if (label) label.textContent = formatDuration(Math.ceil(remaining / 1000));

      if (remaining <= 0) {
        // Construction terminée — notifier le serveur et recharger
        http("POST", "/api/village/pedro/check_complete", {
          building_key: card.dataset.buildingKey,
        }).then(() => location.reload());
        return;
      }
      setTimeout(tick, 1000);
    }
    tick();
  });
}

function formatDuration(seconds) {
  if (seconds <= 0) return "0s";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}min`;
  if (m > 0) return `${m}min ${s}s`;
  return `${s}s`;
}
