// static/GAME_UI/js/support_app.js
// Player support ticket system: search existing tickets + create new ones.

(function (window) {
  "use strict";

  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------
  const CATEGORIES = ["bug", "suggestion", "account", "gameplay", "performance", "other"];
  const CATEGORY_LABELS = {
    bug: "🐛 Bug",
    suggestion: "💡 Suggestion",
    account: "👤 Compte",
    gameplay: "🎮 Gameplay",
    performance: "⚡ Performance",
    other: "❓ Autre",
  };
  const STATUS_LABELS = {
    open: "Ouvert",
    in_progress: "En cours",
    resolved: "Résolu",
    closed: "Fermé",
  };

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  let _tab = "search";          // "search" | "mine" | "create"
  let _searchQ = "";
  let _searchCat = "";
  let _searchPage = 1;
  let _mineQ = "";
  let _minePage = 1;
  let _expandedId = null;

  // ---------------------------------------------------------------------------
  // Open / close
  // ---------------------------------------------------------------------------
  function openSupportModal() {
    const modal = document.getElementById("supportModal");
    if (!modal) return;
    modal.classList.add("is-open");
    _switchTab("search");
    _loadSearch();
  }

  function closeSupportModal() {
    const modal = document.getElementById("supportModal");
    if (!modal) return;
    modal.classList.remove("is-open");
  }

  // ---------------------------------------------------------------------------
  // Tab switching
  // ---------------------------------------------------------------------------
  function _switchTab(tab) {
    _tab = tab;
    document.querySelectorAll(".support-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    });
    document.querySelectorAll(".support-panel").forEach((p) => {
      p.style.display = p.dataset.panel === tab ? "" : "none";
    });

    if (tab === "mine") _loadMine();
    if (tab === "create") _initCreateForm();
  }

  // ---------------------------------------------------------------------------
  // API helpers
  // ---------------------------------------------------------------------------
  async function _apiFetch(url) {
    const r = await fetch(url, { credentials: "same-origin" });
    if (!r.ok) return null;
    return r.json();
  }

  // ---------------------------------------------------------------------------
  // Search panel
  // ---------------------------------------------------------------------------
  function _loadSearch() {
    const params = new URLSearchParams({ q: _searchQ, category: _searchCat, page: _searchPage });
    _setLoading("searchList", true);
    _apiFetch("/api/tickets?" + params).then((data) => {
      _setLoading("searchList", false);
      if (!data) return;
      _renderTicketList("searchList", data, false);
      _renderPagination("searchPager", data, (p) => { _searchPage = p; _loadSearch(); });
    });
  }

  function _loadMine() {
    const params = new URLSearchParams({ mine: "1", q: _mineQ, page: _minePage });
    _setLoading("mineList", true);
    _apiFetch("/api/tickets?" + params).then((data) => {
      _setLoading("mineList", false);
      if (!data) return;
      _renderTicketList("mineList", data, true);
      _renderPagination("minePager", data, (p) => { _minePage = p; _loadMine(); });
    });
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------
  function _setLoading(containerId, on) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (on) el.innerHTML = '<div class="support-empty">Chargement…</div>';
  }

  function _badgeStatus(status) {
    return `<span class="ticket-badge badge-${status}">${STATUS_LABELS[status] || status}</span>`;
  }
  function _badgeCat(cat) {
    return `<span class="ticket-badge badge-cat">${CATEGORY_LABELS[cat] || cat}</span>`;
  }

  function _renderTicketList(containerId, data, isMine) {
    const el = document.getElementById(containerId);
    if (!el) return;

    if (!data.tickets.length) {
      el.innerHTML = '<div class="support-empty">Aucun ticket trouvé.</div>';
      return;
    }

    el.innerHTML = data.tickets.map((t) => `
      <div class="ticket-card" data-id="${t.id}" onclick="window._supportExpandTicket(${t.id}, this)">
        <div class="ticket-card-header">
          <span class="ticket-card-title">${_esc(t.title)}</span>
          <div style="display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end;">
            ${_badgeCat(t.category)}
            ${_badgeStatus(t.status)}
            ${t.mine ? '<span class="ticket-badge" style="background:#312e81;color:#a5b4fc;">Mien</span>' : ""}
          </div>
        </div>
        <div class="ticket-card-meta">
          #${t.id} · Niveau ${t.player_level} · ${_fmtDate(t.created_at)}
        </div>
        <div class="ticket-detail-panel" id="ticketDetail_${t.id}"></div>
      </div>
    `).join("");
  }

  function _renderPagination(containerId, data, onPage) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (data.pages <= 1) { el.innerHTML = ""; return; }

    el.innerHTML = Array.from({ length: data.pages }, (_, i) => i + 1)
      .map((p) => `<button class="${p === data.page ? "active" : ""}" data-p="${p}">${p}</button>`)
      .join("");
    el.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => onPage(+btn.dataset.p));
    });
  }

  // ---------------------------------------------------------------------------
  // Expand ticket detail (fetches description etc)
  // ---------------------------------------------------------------------------
  window._supportExpandTicket = async function (ticketId, cardEl) {
    const panel = document.getElementById(`ticketDetail_${ticketId}`);
    if (!panel) return;

    if (_expandedId === ticketId) {
      // Collapse
      panel.classList.remove("visible");
      _expandedId = null;
      return;
    }

    // Collapse any open one
    if (_expandedId !== null) {
      const prev = document.getElementById(`ticketDetail_${_expandedId}`);
      if (prev) prev.classList.remove("visible");
    }

    _expandedId = ticketId;
    panel.innerHTML = "<em style='color:#475569;font-size:.8rem'>Chargement…</em>";
    panel.classList.add("visible");

    const data = await _apiFetch(`/api/tickets/${ticketId}`);
    if (!data) {
      panel.innerHTML = "<em style='color:#f87171;font-size:.8rem'>Erreur de chargement.</em>";
      return;
    }

    const note = data.admin_note
      ? `<div class="mt-2">
           <div class="ticket-detail-label">Réponse de l'équipe</div>
           <div class="ticket-detail-text" style="color:#93c5fd;">${_esc(data.admin_note)}</div>
         </div>`
      : "";
    const steps = data.steps
      ? `<div class="mt-2">
           <div class="ticket-detail-label">Étapes pour reproduire</div>
           <div class="ticket-detail-text">${_esc(data.steps)}</div>
         </div>`
      : "";

    panel.innerHTML = `
      <div class="mt-2">
        <div class="ticket-detail-label">Description</div>
        <div class="ticket-detail-text">${_esc(data.description)}</div>
      </div>
      ${steps}
      ${note}
    `;
  };

  // ---------------------------------------------------------------------------
  // Create form
  // ---------------------------------------------------------------------------
  function _initCreateForm() {
    const form = document.getElementById("supportCreateForm");
    if (!form || form.dataset.inited) return;
    form.dataset.inited = "1";

    // Auto-fill context
    const ctxLevel = document.getElementById("ctxLevel");
    const ctxPage  = document.getElementById("ctxPage");
    const ctxBrowser = document.getElementById("ctxBrowser");

    if (ctxLevel) {
      const lvl = window.currentPlayer?.level ?? "?";
      ctxLevel.textContent = lvl;
    }
    if (ctxPage)    ctxPage.textContent    = window.location.pathname;
    if (ctxBrowser) ctxBrowser.textContent = navigator.userAgent.slice(0, 120);
  }

  async function _submitTicket() {
    const title       = (document.getElementById("ticketTitle")?.value || "").trim();
    const category    = document.getElementById("ticketCategory")?.value || "bug";
    const description = (document.getElementById("ticketDescription")?.value || "").trim();
    const steps       = (document.getElementById("ticketSteps")?.value || "").trim();
    const msg         = document.getElementById("ticketMsg");
    const btn         = document.getElementById("btnSubmitTicket");

    if (!title) { _showMsg(msg, "Veuillez entrer un titre.", "error"); return; }
    if (!description) { _showMsg(msg, "Veuillez décrire le problème.", "error"); return; }

    if (btn) btn.disabled = true;
    if (msg) msg.className = "support-msg";

    const payload = {
      title,
      category,
      description,
      steps: steps || null,
      page_url: window.location.href.slice(0, 500),
      browser_info: navigator.userAgent.slice(0, 500),
    };

    try {
      const r = await fetch("/api/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (r.ok && data.ok) {
        _showMsg(msg, `Ticket #${data.id} créé ! Merci pour votre signalement.`, "success");
        // Reset form
        document.getElementById("ticketTitle").value = "";
        document.getElementById("ticketDescription").value = "";
        document.getElementById("ticketSteps").value = "";
      } else {
        _showMsg(msg, data.error === "title_required" ? "Titre requis."
          : data.error === "description_required" ? "Description requise."
          : "Erreur lors de l'envoi.", "error");
      }
    } catch {
      _showMsg(msg, "Erreur réseau.", "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Utils
  // ---------------------------------------------------------------------------
  function _esc(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;").replace(/\n/g, "<br>");
  }

  function _fmtDate(iso) {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString("fr-FR") + " " + d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    } catch { return iso; }
  }

  function _showMsg(el, text, type) {
    if (!el) return;
    el.textContent = text;
    el.className = `support-msg ${type}`;
  }

  // ---------------------------------------------------------------------------
  // Init DOM
  // ---------------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    // Tab buttons
    document.querySelectorAll(".support-tab").forEach((btn) => {
      btn.addEventListener("click", () => _switchTab(btn.dataset.tab));
    });

    // Close button
    document.getElementById("supportModalClose")?.addEventListener("click", closeSupportModal);

    // Search
    document.getElementById("searchTicketsBtn")?.addEventListener("click", () => {
      _searchQ   = document.getElementById("searchTicketsInput")?.value.trim() || "";
      _searchCat = document.getElementById("searchTicketsCat")?.value || "";
      _searchPage = 1;
      _loadSearch();
    });
    document.getElementById("searchTicketsInput")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") document.getElementById("searchTicketsBtn")?.click();
    });

    // Submit ticket
    document.getElementById("btnSubmitTicket")?.addEventListener("click", _submitTicket);

    // Support is now opened via the game menu (data-action="support")
  });

  // Expose globally for external use
  window.openSupportModal  = openSupportModal;
  window.closeSupportModal = closeSupportModal;

})(window);
