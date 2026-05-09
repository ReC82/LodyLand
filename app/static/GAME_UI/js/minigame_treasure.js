/*
  File: static/GAME_UI/js/minigame_treasure.js
  Purpose: Treasure Hunt mini-game UI
  APIs used:
    POST /api/treasure/start  → { ok, created, state }
    POST /api/treasure/dig    → { ok, result, reward_shards, shovel_count, state }
    GET  /api/treasure/state  → { ok, game | null, shovel_count }
*/

/* ---------------------------------------------------------------------------
   State
--------------------------------------------------------------------------- */

let _state     = null;   // current serialised game state from server
let _digging   = false;  // prevent concurrent dig requests
const I18N     = window.TREASURE_I18N || {};

/* ---------------------------------------------------------------------------
   Object helpers
--------------------------------------------------------------------------- */

function _objLabel(key) {
  return I18N[`obj_${key}`] || key;
}

// t() may return the raw key when translation is missing — treat as untranslated
function _i18n(key, fallback) {
  const v = I18N[key];
  // If value looks like a dotted i18n path, it wasn't resolved → use fallback
  return (v && !v.includes(".")) ? v : fallback;
}

/* ---------------------------------------------------------------------------
   Clue rendering (i18n via template-injected strings)
   Clue format strings use {n} placeholders:
     {0} = object label (or obj_a/obj_b for closer_to)
     {1} = distance (distance clues)
     {2} = obj_b label (closer_to)
--------------------------------------------------------------------------- */

function _fmt(template, ...args) {
  return template.replace(/\{(\d+)\}/g, (_, i) => args[i] ?? "");
}

function _renderClue(clue) {
  const t = clue.type;

  if (t === "distance") {
    return _fmt(I18N.clue_distance, _objLabel(clue.object_key), clue.distance);
  }
  if (t === "same_row") {
    return _fmt(I18N.clue_same_row, _objLabel(clue.object_key));
  }
  if (t === "same_col") {
    return _fmt(I18N.clue_same_col, _objLabel(clue.object_key));
  }
  if (t === "adjacent") {
    return _fmt(I18N.clue_adjacent, _objLabel(clue.object_key));
  }
  if (t === "zone") {
    const key = {
      left:   "clue_zone_left",
      right:  "clue_zone_right",
      top:    "clue_zone_top",
      bottom: "clue_zone_bot",
    }[clue.zone] || "clue_zone_left";
    return I18N[key] || clue.zone;
  }
  if (t === "closer_to") {
    return _fmt(I18N.clue_closer_to,
      _objLabel(clue.obj_a_key),
      _objLabel(clue.obj_b_key)
    );
  }
  return JSON.stringify(clue);
}

/* ---------------------------------------------------------------------------
   Reward preview
--------------------------------------------------------------------------- */

function _previewReward(gridSize, dugCount) {
  const max     = gridSize * 8;
  const penalty = Math.max(0, dugCount - 1) * 3;
  return Math.max(5, max - penalty);
}

/* ---------------------------------------------------------------------------
   UI helpers
--------------------------------------------------------------------------- */

function _show(id)   { const el = document.getElementById(id); if (el) { el.classList.remove("d-none"); el.style.display = ""; } }
function _hide(id)   { const el = document.getElementById(id); if (el) el.classList.add("d-none"); }
function _text(id, v){ const el = document.getElementById(id); if (el) el.textContent = v; }

function _showToast(msg, type = "info") {
  const toast = document.getElementById("tDigToast");
  if (!toast) return;
  toast.textContent = msg;
  toast.className = `mg-treasure-toast mg-treasure-toast--${type}`;
  toast.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.hidden = true; }, 2500);
}

/* ---------------------------------------------------------------------------
   Grid rendering
--------------------------------------------------------------------------- */

function _buildObjectMap(objects) {
  const m = {};
  (objects || []).forEach(o => { m[`${o.row},${o.col}`] = o.key; });
  return m;
}

function _buildDugMap(dug) {
  const m = {};
  (dug || []).forEach(d => { m[`${d.row},${d.col}`] = d.content; });
  return m;
}

function _renderGrid(state) {
  const grid    = document.getElementById("tGrid");
  if (!grid) return;

  const size    = state.grid_size;
  const objMap  = _buildObjectMap(state.objects);
  const dugMap  = _buildDugMap(state.dug);
  const won     = state.status === "won";
  const tPos    = state.treasure_pos;  // only present when won

  grid.innerHTML = "";
  grid.style.setProperty("--tg-size", size);

  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      const key    = `${r},${c}`;
      const cell   = document.createElement("div");
      cell.className = "mg-treasure-cell";
      cell.dataset.row = r;
      cell.dataset.col = c;

      const isObj  = key in objMap;
      const isDug  = key in dugMap;
      const isTreasure = won && tPos && tPos.row === r && tPos.col === c;

      if (isTreasure) {
        cell.classList.add("mg-treasure-cell--treasure");
        cell.innerHTML = "💎";
      } else if (isObj) {
        cell.classList.add("mg-treasure-cell--object");
        const objKey  = objMap[key];
        const objInfo = state.objects.find(o => o.row === r && o.col === c);
        cell.title = _objLabel(objKey);
        cell.innerHTML = objInfo?.icon
          ? `<img src="${objInfo.icon}" alt="${_objLabel(objKey)}" style="width:70%;height:70%;object-fit:contain;" />`
          : "?";
      } else if (isDug) {
        cell.classList.add("mg-treasure-cell--dug");
        cell.innerHTML = "✗";
      } else {
        cell.classList.add("mg-treasure-cell--undug");
        if (!won && state.status === "active") {
          cell.addEventListener("click", () => _onCellClick(r, c));
        }
      }

      grid.appendChild(cell);
    }
  }
}

function _renderClues(clues, totalClues) {
  const list = document.getElementById("tClueList");
  if (!list) return;
  list.innerHTML = "";

  // Revealed clues
  (clues || []).forEach((clue, i) => {
    const li = document.createElement("li");
    li.className = "mg-treasure-clue-item";
    li.innerHTML = `<span class="mg-treasure-clue-num">${i + 1}</span>${_renderClue(clue)}`;
    list.appendChild(li);
  });

  // Locked (not yet revealed) slots
  const revealed = (clues || []).length;
  const locked   = (totalClues || 0) - revealed;
  for (let i = 0; i < locked; i++) {
    const li = document.createElement("li");
    li.className = "mg-treasure-clue-item mg-treasure-clue-locked";
    li.innerHTML = `<span class="mg-treasure-clue-num">${revealed + i + 1}</span>
      <span class="mg-treasure-clue-lock-text">⛏ ${_i18n("clue_locked", "Creuse pour découvrir…")}</span>`;
    list.appendChild(li);
  }
}

function _updateStatBar(state) {
  _text("tShovelCount", state.shovel_count ?? "–");
  _text("tDugCount",    state.dug_count   ?? 0);

  if (state.status === "active") {
    const preview = _previewReward(state.grid_size, state.dug_count + 1);
    _text("tRewardPreview", _fmt(I18N.stat_reward_fmt || "{0}", preview));
  } else if (state.status === "won") {
    _text("tRewardPreview", _fmt(I18N.stat_reward_fmt || "{0}", state.reward_shards ?? "–"));
  }
}

/* ---------------------------------------------------------------------------
   Full UI update from a game state object
--------------------------------------------------------------------------- */

function _applyState(state) {
  _state = state;

  _hide("tPanelStart");
  _hide("tPanelNoShovel");
  _hide("tPanelWon");
  _show("tLayout");
  _show("tLegend");

  _updateStatBar(state);
  _renderGrid(state);
  _renderClues(state.clues, state.total_clues);

  if (state.status === "won") {
    _showWonPanel(state);
  }
}

function _showWonPanel(state) {
  const shards = state.reward_shards ?? 0;
  const digs   = state.dug_count     ?? 0;
  _text("tWonMsg",    _fmt(I18N.won_msg_fmt || "Trouvé en {0} coups !", digs));
  document.getElementById("tWonReward").innerHTML =
    `<span class="mg-treasure-reward-badge">+${shards} ${I18N.reward_label || "éclats"}</span>`;
  _show("tPanelWon");
}

/* ---------------------------------------------------------------------------
   Cell click handler
--------------------------------------------------------------------------- */

async function _onCellClick(row, col) {
  if (_digging) return;
  if (!_state || _state.status !== "active") return;

  // Optimistic feedback
  const cell = document.querySelector(
    `.mg-treasure-cell[data-row="${row}"][data-col="${col}"]`
  );
  if (cell) cell.classList.add("mg-treasure-cell--digging");

  _digging = true;
  try {
    const res = await http("POST", "/api/treasure/dig", { row, col });
    if (!res.ok) {
      const err = res.data?.error || "error";
      if (err === "no_shovel") {
        _showToast(I18N.no_shovel || "Pas de pelle !", "warning");
        _show("tPanelNoShovel");
      } else if (err === "game_over") {
        _showToast(I18N.game_over || "Partie terminée.", "warning");
      } else {
        _showToast(err, "error");
      }
      if (cell) cell.classList.remove("mg-treasure-cell--digging");
      return;
    }

    const { result, state } = res.data;

    if (result === "treasure") {
      _showToast(I18N.result_treasure || "💎 Trésor trouvé !", "success");
    } else {
      _showToast(I18N.result_empty || "Rien ici…", "info");
    }

    _applyState(state);

  } finally {
    _digging = false;
    const updatedCell = document.querySelector(
      `.mg-treasure-cell[data-row="${row}"][data-col="${col}"]`
    );
    if (updatedCell) updatedCell.classList.remove("mg-treasure-cell--digging");
  }
}

/* ---------------------------------------------------------------------------
   Start / load game
--------------------------------------------------------------------------- */

async function _startGame() {
  const btn = document.getElementById("tBtnStart");
  if (btn) { btn.disabled = true; btn.textContent = "…"; }

  try {
    const res = await http("POST", "/api/treasure/start");
    if (!res.ok) {
      const err = res.data?.error || "error";
      if (err === "level_required") {
        _text("tStartMsg",
          _fmt(I18N.level_required || "Niveau {0} requis.", res.data.min_level));
      }
      if (btn) { btn.disabled = false; btn.textContent = "🌟 " + (I18N.start_button || "Commencer"); }
      return;
    }
    _applyState(res.data.state);
  } catch (e) {
    if (btn) { btn.disabled = false; }
  }
}

async function _loadState() {
  const res = await http("GET", "/api/treasure/state");
  if (!res.ok) return;

  const { game, shovel_count } = res.data;

  // Update shovel count in stat bar regardless
  _text("tShovelCount", shovel_count ?? "–");

  if (!game) {
    // No game today yet → show start panel
    _show("tPanelStart");
    _hide("tLayout");
    _hide("tLegend");
    return;
  }

  _applyState(game);
}

/* ---------------------------------------------------------------------------
   Init
--------------------------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("tBtnStart")?.addEventListener("click", _startGame);

  // Check level gate client-side for instant feedback
  if (typeof window.PLAYER_LEVEL !== "undefined" &&
      typeof window.MIN_LEVEL    !== "undefined" &&
      window.PLAYER_LEVEL < window.MIN_LEVEL) {
    _text("tStartMsg",
      _fmt(I18N.level_required || "Niveau {0} requis.", window.MIN_LEVEL));
    const btn = document.getElementById("tBtnStart");
    if (btn) btn.disabled = true;
    _show("tPanelStart");
    return;
  }

  await _loadState();
});
