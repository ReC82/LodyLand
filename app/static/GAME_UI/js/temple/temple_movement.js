/* ============================================================
   File: temple_movement.js
   Purpose: Pure gameplay rules for Temple lateral movement
   Notes:
   - NO Phaser
   - NO fetch / API
   - NO DOM
   - Single source of truth for movement rules
   ============================================================ */

/**
 * Can the player stand on this tile?
 * @param {number} gridRow
 * @param {number} col
 * @param {Set<string>} brokenTiles
 * @param {Function} tileKeyFn
 */
export function canStandOn(gridRow, col, brokenTiles, tileKeyFn) {
  if (gridRow < 0) return false;
  if (col < 0) return false;
  return !brokenTiles.has(tileKeyFn(gridRow, col));
}

/**
 * Find next valid column in a direction, skipping broken tiles.
 * This is the CORE RULE that fixes backward movement forever.
 *
 * @param {Object} params
 * @param {number} params.gridRow
 * @param {number} params.fromCol
 * @param {number} params.dir        -1 (left) or +1 (right)
 * @param {number} params.maxCols
 * @param {Set<string>} params.brokenTiles
 * @param {Function} params.tileKeyFn
 *
 * @returns {number|null} destination col or null if none
 */
export function findLateralDestination({
  gridRow,
  fromCol,
  dir,
  maxCols,
  brokenTiles,
  tileKeyFn,
}) {
  let c = fromCol + dir;

  while (c >= 0 && c < maxCols) {
    if (canStandOn(gridRow, c, brokenTiles, tileKeyFn)) {
      return c;
    }
    c += dir; // jump over broken tiles
  }

  return null;
}

/**
 * Decide if a lateral move is possible and where.
 * This function NEVER blocks backward movement.
 *
 * @param {Object} params
 */
export function computeLateralMove({
  gridRow,
  currentCol,
  dir,
  cols,
  brokenTiles,
  tileKeyFn,
}) {
  // Sanity
  if (dir !== -1 && dir !== 1) {
    return { ok: false, reason: "invalid_direction" };
  }

  // Try to find next safe tile in that direction
  const dest = findLateralDestination({
    gridRow,
    fromCol: currentCol,
    dir,
    maxCols: cols,
    brokenTiles,
    tileKeyFn,
  });

  if (dest === null) {
    return { ok: false, reason: "no_available_tile" };
  }

  return {
    ok: true,
    destCol: dest,
  };
}

/**
 * Interpret server response for a lateral step.
 * This is where already_broken is correctly handled.
 *
 * @param {Object} params
 */
export function interpretStepResult({
  serverResult,
}) {
  switch (serverResult) {
    case "safe":
      return { type: "SAFE" };

    case "trap":
      return { type: "TRAP" };

    case "already_broken":
      // IMPORTANT:
      // This is NOT an error.
      // Movement is allowed, no animation, no life loss.
      return { type: "BROKEN_KNOWN" };

    default:
      return { type: "ERROR", reason: serverResult };
  }
}
