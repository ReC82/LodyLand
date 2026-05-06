# =============================================================================
# app/minigames/treasure_generator.py
# Purpose: Pure logic for generating a Treasure Hunt game grid and clues.
#
# Design:
#   - Grid is a square of size GRID_MIN..GRID_MAX
#   - Objects are visible landmarks (reference points for clues)
#   - Treasure is hidden; player finds it by digging
#   - Clues are generated AFTER grid placement and are always true
#   - Greedy clue selection reduces candidate cells to <= TARGET_CANDIDATES
#   - All state is serialisable to JSON (no ORM objects stored here)
# =============================================================================
from __future__ import annotations

import random
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRID_MIN = 8
GRID_MAX = 12

# Landmark object keys — must match real item keys in items.yml so icons resolve
OBJECT_KEYS = ["flint", "pearl", "stone_chunk", "seashell", "branch", "starfish", "coal"]

# Stop adding clues when candidate count is at or below this
TARGET_CANDIDATES = 6

# Maximum clues to emit (safety cap)
MAX_CLUES = 8


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _obj_pos(idx: int, objects: list[dict]) -> tuple[int, int]:
    o = objects[idx]
    return (o["row"], o["col"])


# ---------------------------------------------------------------------------
# Candidate filtering: given a clue, which cells are still consistent?
# ---------------------------------------------------------------------------

def _filter_candidates(
    candidates: set[tuple[int, int]],
    clue: dict,
    grid_size: int,
    objects: list[dict],
) -> set[tuple[int, int]]:
    t = clue["type"]

    if t == "distance":
        op = _obj_pos(clue["obj_idx"], objects)
        d = clue["distance"]
        return {p for p in candidates if _manhattan(p, op) <= d}

    if t == "same_row":
        op = _obj_pos(clue["obj_idx"], objects)
        return {p for p in candidates if p[0] == op[0]}

    if t == "same_col":
        op = _obj_pos(clue["obj_idx"], objects)
        return {p for p in candidates if p[1] == op[1]}

    if t == "adjacent":
        op = _obj_pos(clue["obj_idx"], objects)
        return {p for p in candidates if _manhattan(p, op) == 1}

    if t == "zone":
        half = grid_size // 2
        zone = clue["zone"]
        if zone == "left":
            return {p for p in candidates if p[1] < half}
        if zone == "right":
            return {p for p in candidates if p[1] >= half}
        if zone == "top":
            return {p for p in candidates if p[0] < half}
        if zone == "bottom":
            return {p for p in candidates if p[0] >= half}

    if t == "closer_to":
        pa = _obj_pos(clue["obj_a_idx"], objects)
        pb = _obj_pos(clue["obj_b_idx"], objects)
        return {p for p in candidates if _manhattan(p, pa) < _manhattan(p, pb)}

    return candidates  # unknown type: no filtering


# ---------------------------------------------------------------------------
# Clue pool: all true clues for a given treasure position
# ---------------------------------------------------------------------------

def _build_clue_pool(
    grid_size: int,
    treasure: tuple[int, int],
    objects: list[dict],
) -> list[dict]:
    """
    Generate every possible valid clue (true given actual treasure position).
    Clues reference object indices rather than keys to handle duplicates correctly.
    """
    pool: list[dict] = []
    tr, tc = treasure

    for idx, obj in enumerate(objects):
        or_, oc = obj["row"], obj["col"]
        dist = _manhattan(treasure, (or_, oc))

        # Distance clues: exact distance and up to two slightly looser thresholds
        for threshold in sorted({dist, dist + 2, dist + 3}):
            if 1 < threshold < grid_size:
                pool.append({
                    "type": "distance",
                    "obj_idx": idx,
                    "object_key": obj["key"],
                    "distance": threshold,
                })

        # Same-row / same-col (very strong clues)
        if tr == or_:
            pool.append({"type": "same_row", "obj_idx": idx, "object_key": obj["key"]})
        if tc == oc:
            pool.append({"type": "same_col", "obj_idx": idx, "object_key": obj["key"]})

        # Adjacent (treasure is exactly 1 step from this object)
        if dist == 1:
            pool.append({"type": "adjacent", "obj_idx": idx, "object_key": obj["key"]})

    # Zone clues (half-grid)
    half = grid_size // 2
    pool.append({"type": "zone", "zone": "left" if tc < half else "right"})
    pool.append({"type": "zone", "zone": "top"  if tr < half else "bottom"})

    # Closer-to clues (pairwise objects)
    for i in range(len(objects)):
        for j in range(i + 1, len(objects)):
            di = _manhattan(treasure, (objects[i]["row"], objects[i]["col"]))
            dj = _manhattan(treasure, (objects[j]["row"], objects[j]["col"]))
            if di == dj:
                continue  # equidistant → no useful clue
            a, b = (i, j) if di < dj else (j, i)
            pool.append({
                "type": "closer_to",
                "obj_a_idx": a,
                "obj_a_key": objects[a]["key"],
                "obj_b_idx": b,
                "obj_b_key": objects[b]["key"],
            })

    return pool


# ---------------------------------------------------------------------------
# Greedy clue selection
# ---------------------------------------------------------------------------

def _select_clues(
    grid_size: int,
    treasure: tuple[int, int],
    objects: list[dict],
    rng: random.Random,
) -> list[dict]:
    """
    Greedily add clues until candidate cells <= TARGET_CANDIDATES or pool is exhausted.
    Ties broken by pool shuffle (randomised order).
    """
    occupied = {(o["row"], o["col"]) for o in objects}
    candidates: set[tuple[int, int]] = {
        (r, c)
        for r in range(grid_size)
        for c in range(grid_size)
        if (r, c) not in occupied
    }

    pool = _build_clue_pool(grid_size, treasure, objects)
    rng.shuffle(pool)  # randomise tie-breaking

    chosen: list[dict] = []

    while len(candidates) > TARGET_CANDIDATES and pool and len(chosen) < MAX_CLUES:
        best_clue: dict | None = None
        best_size = len(candidates)
        best_remaining: set = candidates

        for clue in pool:
            after = _filter_candidates(candidates, clue, grid_size, objects)
            if 0 < len(after) < best_size:
                best_size = len(after)
                best_clue = clue
                best_remaining = after

        if best_clue is None:
            break  # No clue reduces candidates further

        chosen.append(best_clue)
        pool.remove(best_clue)
        candidates = best_remaining

    return chosen


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TreasureGenerator:
    """
    Generates a complete treasure-hunt game state as a plain dict (JSON-safe).

    Usage:
        gen = TreasureGenerator(seed=12345)
        state = gen.generate()
        # state keys: grid_size, treasure, objects, clues, dug
    """

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def generate(self) -> dict[str, Any]:
        grid_size = self.rng.randint(GRID_MIN, GRID_MAX)
        n_objects = self.rng.randint(3, 5)

        # Pick distinct random positions for treasure + objects
        all_cells: list[tuple[int, int]] = [
            (r, c) for r in range(grid_size) for c in range(grid_size)
        ]
        self.rng.shuffle(all_cells)

        treasure_pos = all_cells[0]
        object_cells = all_cells[1: n_objects + 1]

        # Assign object keys (may repeat; obj_idx disambiguates in clues)
        objects = [
            {
                "key": self.rng.choice(OBJECT_KEYS),
                "row": r,
                "col": c,
            }
            for r, c in object_cells
        ]

        clues = _select_clues(grid_size, treasure_pos, objects, self.rng)

        return {
            "grid_size": grid_size,
            "treasure": {"row": treasure_pos[0], "col": treasure_pos[1]},
            "objects": objects,
            "clues": clues,
            "dug": [],
        }
