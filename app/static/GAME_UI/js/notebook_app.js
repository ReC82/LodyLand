/* File: static/GAME_UI/js/notebook_app.js
   Purpose: Fullscreen Notebook modal (Lands/Crafts/Tips)
   Depends:
   - common.js (window.http)
   Notes:
   - Lands tab: one row per land + accordion details
   - Improvements:
     - Search (land / tools / resources) via injected input
     - Tool accordions (inside each land accordion)
     - Loot displayed as ICON GRID (no text list), showing qty + % under icon
     - Resource icons resolved via API if present (lootRow.icon), otherwise fallback by kind
     - Tool icons resolved via API if present (tool.icon), otherwise emoji only
     - XP shown if present (tool.xp_gain or tool.xp_multiplier as fallback)
*/

(function () {
  "use strict";

  const API_BASE = "/api";

  const el = {
    btnOpen: document.getElementById("hud-notebook-btn"),
    modal: document.getElementById("notebookModal"),
    backdrop: document.getElementById("notebookModalBackdrop"),
    btnClose: document.getElementById("notebookCloseBtn"),
    tabs: Array.from(document.querySelectorAll(".notebook-tab")),
    panels: Array.from(document.querySelectorAll(".notebook-panel")),
    landsList: document.getElementById("notebookLandsList"),
  };

  let cache = {
    loaded: false,
    data: null,
    query: "",
  };

  function setModalOpen(isOpen) {
    if (!el.modal) return;

    if (isOpen) {
      el.modal.classList.add("is-open");
      el.modal.setAttribute("aria-hidden", "false");
      ensureNotebookLoaded();
    } else {
      el.modal.classList.remove("is-open");
      el.modal.setAttribute("aria-hidden", "true");
    }
  }

  function setActiveTab(tabKey) {
    el.tabs.forEach((b) => b.classList.toggle("is-active", b.dataset.tab === tabKey));
    el.panels.forEach((p) => p.classList.toggle("is-active", p.dataset.panel === tabKey));
  }

  async function apiGet(path) {
    if (typeof window.http === "function") {
      const r = await window.http("GET", path);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.data;
    }

    const res = await fetch(path, { credentials: "same-origin" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  function safeText(s) {
    return (s ?? "").toString();
  }

  function norm(s) {
    return safeText(s).trim().toLowerCase();
  }

  function fmtChancePct(n) {
    const v = Number(n || 0);
    return `${Math.max(0, Math.min(100, Math.round(v)))}%`;
  }

  function fmtCooldown(sec) {
    const s = Number(sec || 0);
    if (!s) return "—";
    return `${s}s`;
  }

  function fmtSlotMeta(land) {
    const slots = land?.slots;
    if (!slots) return "";

    const total = Number(slots.total ?? 0);
    const next = Number(slots.next_cost_diams ?? 0);

    const line1 = `Slots: ${total}`;
    const line2 = next > 0 ? `Next: ${next} diams` : `Next: —`;

    return `<div>${line1}</div><div class="muted">${line2}</div>`;
  }

  // ---------
  // ICON RESOLUTION
  // ---------
  function normalizeAssetPath(p) {
    if (!p) return "";

    const s = String(p).trim();
    if (!s) return "";

    // Allow absolute URLs
    if (s.startsWith("http://") || s.startsWith("https://")) return s;

    // Already absolute path on this host
    if (s.startsWith("/")) return s;

    // Common case: "static/..."
    if (s.startsWith("static/")) return "/" + s;

    // Otherwise treat as root-relative
    return "/" + s.replace(/^\/+/, "");
  }

  // IMPORTANT: pass the LOOT ROW, not resource_obj
  function getResourceIcon(resourceKey, lootRow) {
    // Prefer API-provided icon (items.yml)
    const apiIcon = lootRow && lootRow.icon;
    if (apiIcon) return normalizeAssetPath(apiIcon);

    // Fallback by kind (treasure vs resource)
    const kind = safeText(lootRow && lootRow.kind).toLowerCase();
    if (kind === "treasure") {
      return `/static/assets/img/items/treasures/${safeText(resourceKey)}.png`;
    }

    return `/static/assets/img/items/resources/${safeText(resourceKey)}.png`;
  }

  function getToolIcon(tool) {
    const apiIcon = tool?.icon;
    if (apiIcon) return normalizeAssetPath(apiIcon);
    return "";
  }

  // ---------
  // SEARCH
  // ---------
  function ensureSearchUI() {
    if (!el.landsList) return;

    const parent = el.landsList.parentElement;
    if (!parent) return;

    if (parent.querySelector("#notebookSearch")) return;

    const wrap = document.createElement("div");
    wrap.className = "nb-search-row";
    wrap.innerHTML = `
      <input id="notebookSearch" class="nb-search-input" type="search"
             placeholder="Rechercher land / outil / ressource...">
      <button id="notebookSearchClear" class="nb-search-clear" type="button">Effacer</button>
    `;

    parent.insertBefore(wrap, el.landsList);

    const input = parent.querySelector("#notebookSearch");
    const clear = parent.querySelector("#notebookSearchClear");

    if (input) {
      input.value = cache.query || "";
      input.addEventListener("input", () => {
        cache.query = input.value || "";
        if (cache.data) renderLandsList(cache.data);
      });
    }

    if (clear) {
      clear.addEventListener("click", () => {
        cache.query = "";
        if (input) input.value = "";
        if (cache.data) renderLandsList(cache.data);
      });
    }
  }

  function lootMatchesQuery(loot, q) {
    if (!q) return true;
    const rk = norm(loot?.resource);
    const rl = norm(loot?.label);
    return rk.includes(q) || rl.includes(q);
  }

  function toolMatchesQuery(tool, q) {
    if (!q) return true;

    const k = norm(tool?.tool_key);
    const l = norm(tool?.label);
    if (k.includes(q) || l.includes(q)) return true;

    const loot = Array.isArray(tool?.loot) ? tool.loot : [];
    return loot.some((x) => lootMatchesQuery(x, q));
  }

  function landMatchesQuery(land, q) {
    if (!q) return true;

    const k = norm(land?.key);
    const l = norm(land?.label);
    const d = norm(land?.short_description);

    if (k.includes(q) || l.includes(q) || d.includes(q)) return true;

    const tools = Array.isArray(land?.tools) ? land.tools : [];
    return tools.some((t) => toolMatchesQuery(t, q));
  }

  // ---------
  // RENDER: LOOT GRID (icons + qty + %)
  // ---------
  function renderToolLootGrid(tool, q) {
    const loot = Array.isArray(tool?.loot) ? tool.loot : [];
    const filtered = loot.filter((x) => lootMatchesQuery(x, q));

    if (!filtered.length) {
      return `<div class="nb-muted-line">Aucun loot défini.</div>`;
    }

    const sorted = filtered.slice().sort((a, b) => {
      const ca = Number(a.chance || 0);
      const cb = Number(b.chance || 0);
      if (cb !== ca) return cb - ca;
      return safeText(a.resource).localeCompare(safeText(b.resource));
    });

    return `
      <div class="nb-loot-grid">
        ${sorted
          .map((x) => {
            const resourceKey = safeText(x.resource);
            const icon = getResourceIcon(resourceKey, x); // ✅ FIX HERE
            const pct = fmtChancePct(x.chance_pct ?? (Number(x.chance || 0) * 100));

            const mn = Number(x.min ?? 1);
            const mx = Number(x.max ?? mn);
            const qty = mn === mx ? `x${mn}` : `x${mn}–${mx}`;

            // Optional: fallback if image missing
            const fallback = `/static/assets/img/items/resources/${safeText(resourceKey)}.png`;

            return `
              <div class="nb-loot-tile" title="${safeText(x.label || resourceKey)}">
                <div class="nb-loot-ico">
                  <img
                    src="${icon}"
                    alt="${safeText(x.label || resourceKey)}"
                    class="nb-loot-img"
                    onerror="this.onerror=null; this.src='${fallback}';"
                  >
                </div>
                <div class="nb-loot-line1">${qty}</div>
                <div class="nb-loot-pct">${pct}</div>
              </div>
            `;
          })
          .join("")}
      </div>
    `;
  }

  // ---------
  // RENDER: TOOL ACCORDIONS (inside land)
  // ---------
  function toolTitle(tool) {
    const emoji = safeText(tool?.emoji);
    const name = safeText(tool?.label || tool?.tool_key);
    return `${emoji ? emoji + " " : ""}${name}`;
  }

  function toolMetaLine(tool) {
    const cd = fmtCooldown(tool?.cooldown_seconds);

    const parts = [];
    parts.push(`Cooldown: ${cd}`);

    if (tool?.xp_gain !== undefined && tool?.xp_gain !== null) {
      parts.push(`XP: ${Number(tool.xp_gain)}`);
    } else if (tool?.xp_per_collect !== undefined && tool?.xp_per_collect !== null) {
      parts.push(`XP: ${Number(tool.xp_per_collect)}`);
    } else if (tool?.xp_multiplier !== undefined && tool?.xp_multiplier !== null) {
      parts.push(`XP x${Number(tool.xp_multiplier)}`);
    }

    return parts.join(" • ");
  }

  function renderToolAccordion(tool, q) {
    const icon = getToolIcon(tool);
    const title = toolTitle(tool);
    const meta = toolMetaLine(tool);

    const iconHtml = icon ? `<img src="${icon}" alt="" class="nb-tool-icon">` : "";

    return `
      <div class="nb-tool-row">
        <button type="button" class="nb-tool-btn" aria-expanded="false">
          <div class="nb-tool-left">
            <div class="nb-tool-ico">${iconHtml}</div>
            <div class="nb-tool-text">
              <div class="nb-tool-name">${title}</div>
              <div class="nb-tool-meta">${meta}</div>
            </div>
          </div>

          <div class="nb-tool-right">
            <span class="nb-tool-chevron">▼</span>
          </div>
        </button>

        <div class="nb-tool-body">
          ${renderToolLootGrid(tool, q)}
        </div>
      </div>
    `;
  }

  function wireToolAccordions(landRow) {
    if (!landRow) return;

    const toolRows = Array.from(landRow.querySelectorAll(".nb-tool-row"));
    if (!toolRows.length) return;

    toolRows.forEach((row) => {
      const btn = row.querySelector(".nb-tool-btn");
      const body = row.querySelector(".nb-tool-body");
      if (!btn || !body) return;

      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";

      btn.addEventListener("click", () => {
        const isOpen = row.classList.contains("is-open");

        toolRows.forEach((r) => {
          r.classList.remove("is-open");
          const b = r.querySelector(".nb-tool-btn");
          if (b) b.setAttribute("aria-expanded", "false");
        });

        if (!isOpen) {
          row.classList.add("is-open");
          btn.setAttribute("aria-expanded", "true");
        }
      });
    });
  }

  // ---------
  // LAND DETAILS
  // ---------
  function renderLandDetails(land, q) {
    if (!land.unlocked) {
      return `<div class="nb-muted-line">Verrouillé — débloque via cartes / progression.</div>`;
    }

    const tools = Array.isArray(land.tools) ? land.tools : [];
    const filteredTools = tools.filter((t) => toolMatchesQuery(t, q));

    if (!filteredTools.length) {
      return q
        ? `<div class="nb-muted-line">Aucun outil/loot ne correspond à la recherche.</div>`
        : `<div class="nb-muted-line">Aucun outil défini pour ce land.</div>`;
    }

    return `
      <div class="nb-details-grid">
        <div>
          <div class="nb-details-section-title">Loot par outil</div>
          ${filteredTools.map((t) => renderToolAccordion(t, q)).join("")}
        </div>
      </div>
    `;
  }

  // ---------
  // MAIN LIST (lands)
  // ---------
  function renderLandsList(data) {
    if (!el.landsList) return;

    ensureSearchUI();

    const q = norm(cache.query);

    const lands = Array.isArray(data?.lands) ? data.lands : [];
    const filteredLands = lands.filter((land) => landMatchesQuery(land, q));

    if (!filteredLands.length) {
      el.landsList.innerHTML = `<div class="notebook-empty">Aucun résultat.</div>`;
      return;
    }

    el.landsList.innerHTML = filteredLands
      .map((land) => {
        const lockedClass = land.unlocked ? "" : " is-locked";
        const logo = safeText(land.logo);
        const title = safeText(land.label || land.key);
        const desc = safeText(land.short_description || "");
        const meta = fmtSlotMeta(land);

        const thumbHtml = logo
          ? `<img class="notebook-land-icon" src="/${logo.replace(/^\/?/, "")}" alt="${title}">`
          : `<div class="nb-muted-line">?</div>`;

        return `
          <div class="nb-land-row${lockedClass}" data-land-key="${safeText(land.key)}">
            <button type="button" class="nb-land-head" aria-expanded="false">
              <div class="nb-land-thumb">${thumbHtml}</div>

              <div class="nb-land-main">
                <div class="nb-land-title">${title}</div>
                ${desc ? `<div class="nb-land-sub">${desc}</div>` : ""}
                ${
                  !land.unlocked
                    ? `<div class="nb-land-lock-hint">Verrouillé — pages illisibles pour l’instant.</div>`
                    : ""
                }
              </div>

              <div class="nb-land-meta">
                ${meta}
                <span class="nb-land-chevron">▼</span>
              </div>
            </button>

            <div class="nb-land-details">
              ${renderLandDetails(land, q)}
            </div>
          </div>
        `;
      })
      .join("");

    el.landsList.querySelectorAll(".nb-land-row .nb-land-head").forEach((btn) => {
      btn.addEventListener("click", () => {
        const row = btn.closest(".nb-land-row");
        if (!row) return;

        const isOpen = row.classList.contains("is-open");

        el.landsList.querySelectorAll(".nb-land-row").forEach((r) => {
          r.classList.remove("is-open");
          const head = r.querySelector(".nb-land-head");
          if (head) head.setAttribute("aria-expanded", "false");
        });

        if (!isOpen) {
          row.classList.add("is-open");
          btn.setAttribute("aria-expanded", "true");
          wireToolAccordions(row);
        }
      });
    });

    if (q) {
      const first = el.landsList.querySelector(".nb-land-row .nb-land-head");
      if (first) first.click();
    }
  }

  async function ensureNotebookLoaded() {
    if (cache.loaded) return;

    if (el.landsList) {
      el.landsList.innerHTML = `<div class="notebook-empty">Chargement...</div>`;
    }

    try {
      const data = await apiGet(`${API_BASE}/notebook`);
      cache.loaded = true;
      cache.data = data;
      renderLandsList(data);
    } catch (err) {
      console.error("[notebook] Failed to load", err);
      if (el.landsList) {
        el.landsList.innerHTML = `<div class="notebook-empty">Erreur de chargement du notebook.</div>`;
      }
    }
  }

  function wireEvents() {
    if (el.btnOpen) el.btnOpen.addEventListener("click", () => setModalOpen(true));
    if (el.btnClose) el.btnClose.addEventListener("click", () => setModalOpen(false));
    if (el.backdrop) el.backdrop.addEventListener("click", () => setModalOpen(false));

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setModalOpen(false);
    });

    el.tabs.forEach((b) => {
      b.addEventListener("click", () => setActiveTab(b.dataset.tab));
    });
  }

  wireEvents();
})();
