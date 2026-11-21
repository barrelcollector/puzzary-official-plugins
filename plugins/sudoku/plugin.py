from __future__ import annotations

import json
import random
import re
from typing import Any

from app.puzzles import GeneratedPuzzle, GenerationField, PrintLayout, PuzzleType, register_puzzle_type
from app.group_actions import cell_collaboration


Grid = list[list[int]]
BOX_DEFAULTS = {
    4: (2, 2),
    6: (2, 3),
    9: (3, 3),
}


def build_source(_source_entries: Any, _difficulty: str, _excluded_tag_ids: set[int] | None = None) -> dict:
    return {}


def integer_option(options: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(options.get(key, "")).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def bool_option(options: dict[str, Any], key: str, default: bool) -> bool:
    raw = str(options.get(key, "")).strip().lower()
    if raw in {"yes", "true", "1", "on"}:
        return True
    if raw in {"no", "false", "0", "off"}:
        return False
    return default


def sudoku_shape(options: dict[str, Any]) -> tuple[int, int, int]:
    preset = str(options.get("grid_size", "")).strip().lower()
    if preset == "custom":
        size = integer_option(options, "custom_grid_size", 9, 4, 9)
        box_rows = integer_option(options, "box_rows", BOX_DEFAULTS.get(size, (3, 3))[0], 1, size)
        box_cols = integer_option(options, "box_cols", BOX_DEFAULTS.get(size, (3, 3))[1], 1, size)
    elif preset:
        try:
            size = int(preset)
        except ValueError:
            size = 9
        box_rows, box_cols = BOX_DEFAULTS.get(size, (3, 3))
    else:
        size = 9
        box_rows, box_cols = BOX_DEFAULTS[size]
    if box_rows * box_cols != size:
        raise ValueError("Sudoku custom size requires box rows x box columns to equal the grid size.")
    return size, box_rows, box_cols


def base_solution(size: int, box_rows: int, box_cols: int) -> Grid:
    return [[((row * box_cols + row // box_rows + col) % size) + 1 for col in range(size)] for row in range(size)]


def shuffled_solution(rng: random.Random, size: int, box_rows: int, box_cols: int) -> Grid:
    rows = [
        band * box_rows + row
        for band in rng.sample(range(box_cols), box_cols)
        for row in rng.sample(range(box_rows), box_rows)
    ]
    cols = [
        stack * box_cols + col
        for stack in rng.sample(range(box_rows), box_rows)
        for col in rng.sample(range(box_cols), box_cols)
    ]
    values = rng.sample(range(1, size + 1), size)
    base = base_solution(size, box_rows, box_cols)
    return [[values[base[row][col] - 1] for col in cols] for row in rows]


def mirror_cell(row: int, col: int, size: int, symmetry: str) -> tuple[int, int] | None:
    if symmetry == "rotational":
        return size - 1 - row, size - 1 - col
    if symmetry == "mirrored":
        return row, size - 1 - col
    return None


def count_solutions(puzzle: Grid, size: int, box_rows: int, box_cols: int, limit: int = 2) -> int:
    grid = [row[:] for row in puzzle]
    rows = [set(row) - {0} for row in grid]
    cols = [{grid[row][col] for row in range(size)} - {0} for col in range(size)]
    boxes = [
        {grid[row][col] for row in range(br * box_rows, (br + 1) * box_rows) for col in range(bc * box_cols, (bc + 1) * box_cols)} - {0}
        for br in range(box_cols)
        for bc in range(box_rows)
    ]

    def box_index(row: int, col: int) -> int:
        return (row // box_rows) * box_rows + (col // box_cols)

    def solve() -> int:
        best_cell = None
        best_candidates: list[int] = []
        for row in range(size):
            for col in range(size):
                if grid[row][col]:
                    continue
                used = rows[row] | cols[col] | boxes[box_index(row, col)]
                candidates = [value for value in range(1, size + 1) if value not in used]
                if not candidates:
                    return 0
                if best_cell is None or len(candidates) < len(best_candidates):
                    best_cell = (row, col)
                    best_candidates = candidates
        if best_cell is None:
            return 1
        found = 0
        row, col = best_cell
        box = box_index(row, col)
        for value in best_candidates:
            grid[row][col] = value
            rows[row].add(value)
            cols[col].add(value)
            boxes[box].add(value)
            found += solve()
            rows[row].remove(value)
            cols[col].remove(value)
            boxes[box].remove(value)
            grid[row][col] = 0
            if found >= limit:
                return found
        return found

    return solve()


def puzzle_from_solution(
    solution: Grid,
    difficulty: str,
    rng: random.Random,
    given_count: int | None,
    symmetry: str,
) -> Grid:
    size = len(solution)
    default_ratio = {"easy": 0.52, "medium": 0.42, "hard": 0.35}.get(difficulty, 0.42)
    givens = given_count or round(size * size * default_ratio)
    givens = max(size, min(size * size - 1, givens))
    puzzle = [row[:] for row in solution]
    cells = [(row, col) for row in range(size) for col in range(size)]
    rng.shuffle(cells)
    blanks_needed = size * size - givens
    removed = 0
    for row, col in cells:
        if removed >= blanks_needed:
            break
        targets = {(row, col)}
        mirrored = mirror_cell(row, col, size, symmetry)
        if mirrored is not None:
            targets.add(mirrored)
        open_targets = [(r, c) for r, c in targets if puzzle[r][c]]
        if not open_targets or removed + len(open_targets) > blanks_needed:
            continue
        for target_row, target_col in open_targets:
            puzzle[target_row][target_col] = 0
        removed += len(open_targets)
    if removed < blanks_needed:
        for row, col in cells:
            if removed >= blanks_needed:
                break
            if puzzle[row][col]:
                puzzle[row][col] = 0
                removed += 1
    return puzzle


def unique_puzzle(
    rng: random.Random,
    difficulty: str,
    size: int,
    box_rows: int,
    box_cols: int,
    given_count: int | None,
    symmetry: str,
    require_unique: bool,
) -> tuple[Grid, Grid, bool]:
    for _ in range(60 if require_unique else 1):
        solution = shuffled_solution(rng, size, box_rows, box_cols)
        puzzle = puzzle_from_solution(solution, difficulty, rng, given_count, symmetry)
        if not require_unique or count_solutions(puzzle, size, box_rows, box_cols) == 1:
            return solution, puzzle, require_unique
    solution = shuffled_solution(rng, size, box_rows, box_cols)
    puzzle = puzzle_from_solution(solution, difficulty, rng, given_count, symmetry)
    return solution, puzzle, False


def flat_answer_from_payload(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
        if isinstance(parsed, dict):
            value = parsed
        else:
            digits = [char for char in str(parsed) if char.isdigit()]
            return {f"{index % 9},{index // 9}": digit for index, digit in enumerate(digits[:81]) if digit != "0"}
    if not isinstance(value, dict):
        return {}
    answers = value.get("answers", value)
    if not isinstance(answers, dict):
        return {}
    normalized = {}
    for key, raw_value in answers.items():
        digit = str(raw_value).strip()[:1]
        if key and digit.isdigit() and digit != "0":
            normalized[str(key)] = digit
    return normalized


def given_cells(puzzle_grid: Grid) -> dict[str, str]:
    return {
        f"{col},{row}": str(value)
        for row, line in enumerate(puzzle_grid)
        for col, value in enumerate(line)
        if value
    }


PROGRESSIVE_TYPES = ("row", "column", "box")


def option_values(options: dict[str, Any], key: str) -> list[str]:
    value = options.get(key, [])
    values = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    return [str(item).strip().lower() for item in values if str(item).strip()]


def sudoku_unit_map(size: int, box_rows: int, box_cols: int, unit_types: list[str]) -> dict[str, list[str]]:
    units: dict[str, list[str]] = {}
    if "row" in unit_types:
        for row in range(size):
            units[f"row:{row + 1}"] = [f"{col},{row}" for col in range(size)]
    if "column" in unit_types:
        for col in range(size):
            units[f"column:{col + 1}"] = [f"{col},{row}" for row in range(size)]
    if "box" in unit_types:
        number = 0
        for top in range(0, size, box_rows):
            for left in range(0, size, box_cols):
                number += 1
                units[f"box:{number}"] = [
                    f"{col},{row}"
                    for row in range(top, top + box_rows)
                    for col in range(left, left + box_cols)
                ]
    return units


def normalize_unit_id(value: str) -> str:
    compact = value.strip().lower().replace(" ", "").replace("-", ":")
    aliases = {"r": "row", "row": "row", "c": "column", "col": "column", "column": "column", "b": "box", "box": "box"}
    match = re.fullmatch(r"([a-z]+):?(\d+)", compact)
    if not match or match.group(1) not in aliases:
        raise ValueError(f"Unknown progressive Sudoku unit '{value.strip()}'. Use values such as row:1, column:2, or box:3.")
    return f"{aliases[match.group(1)]}:{int(match.group(2))}"


def progressive_settings(options: dict[str, Any], size: int, box_rows: int, box_cols: int) -> dict[str, Any]:
    enabled = bool_option(options, "progressive_solve", False)
    selected = option_values(options, "progressive_units")
    unit_types = [kind for kind in PROGRESSIVE_TYPES if kind in selected]
    if enabled and not unit_types:
        unit_types = ["row"]
    validation = str(options.get("progressive_validation", "automatic")).strip().lower()
    if validation not in {"automatic", "manual"}:
        validation = "automatic"
    order = str(options.get("progressive_order", "any")).strip().lower()
    if order not in {"any", "sequence"}:
        order = "any"
    units = sudoku_unit_map(size, box_rows, box_cols, unit_types)
    sequence: list[str] = []
    if enabled and order == "sequence":
        raw_sequence = str(options.get("progressive_sequence", "")).replace("\n", ",").split(",")
        sequence = [normalize_unit_id(value) for value in raw_sequence if value.strip()] or list(units)
        if len(sequence) != len(set(sequence)):
            raise ValueError("Progressive Sudoku sequence cannot contain duplicate units.")
        if set(sequence) != set(units):
            raise ValueError("Progressive Sudoku sequence must include every selected unit exactly once.")
    return {
        "enabled": enabled,
        "units": unit_types,
        "validation": validation,
        "mark_completed": bool_option(options, "progressive_mark", True),
        "lock_completed": bool_option(options, "progressive_lock", False),
        "order": order,
        "sequence": sequence,
    }


def progressive_unit_state(state: dict, solution_payload: dict) -> tuple[dict[str, list[str]], dict[str, str], dict[str, str], dict]:
    settings = solution_payload.get("settings", {})
    progressive = settings.get("progressive", {}) if isinstance(settings, dict) else {}
    if not isinstance(progressive, dict) or not progressive.get("enabled"):
        return {}, {}, {}, {}
    size = int(settings.get("grid_size", len(solution_payload.get("grid", [])) or 9))
    units = sudoku_unit_map(size, int(settings.get("box_rows", 3)), int(settings.get("box_cols", 3)), list(progressive.get("units", [])))
    expected = {
        f"{col},{row}": str(value)
        for row, line in enumerate(solution_payload.get("grid", []))
        for col, value in enumerate(line)
    }
    givens = {str(key): str(value) for key, value in solution_payload.get("givens", {}).items()}
    answers = state.get("answers", {}) if isinstance(state.get("answers"), dict) else {}
    return units, expected, {**givens, **{str(key): str(value) for key, value in answers.items()}}, progressive


def update_progressive_state(state: dict, action: dict, solution_payload: dict) -> dict:
    units, expected, combined, progressive = progressive_unit_state(state, solution_payload)
    if not units:
        for key in ("progressive_completed", "progressive_authors", "progressive_blocked", "progressive_active"):
            state.pop(key, None)
        return state
    correct = {unit_id for unit_id, keys in units.items() if all(combined.get(key) == expected.get(key) for key in keys)}
    full = {unit_id for unit_id, keys in units.items() if all(combined.get(key) for key in keys)}
    completed = {unit_id for unit_id in state.get("progressive_completed", []) if unit_id in correct}
    authors = {str(key): value for key, value in state.get("progressive_authors", {}).items() if key in completed}
    blocked = {unit_id for unit_id in state.get("progressive_blocked", []) if unit_id in full and unit_id not in completed}
    sequence = list(progressive.get("sequence") or units)
    ordered = progressive.get("order") == "sequence"
    actor = action.get("_actor")
    validate = action.get("kind") in {"check", "progressive_check", "reveal"} or (
        progressive.get("validation") == "automatic" and action.get("kind") in {"patch", "hint"}
    )

    def complete(unit_id: str) -> None:
        completed.add(unit_id)
        blocked.discard(unit_id)
        if actor is not None:
            authors[unit_id] = actor

    if action.get("kind") == "reveal":
        for unit_id in units:
            complete(unit_id)
    elif validate and ordered:
        while True:
            active = next((unit_id for unit_id in sequence if unit_id not in completed), None)
            if active is None or active not in full or active in blocked:
                break
            if active in correct:
                complete(active)
            else:
                blocked.add(active)
                break
    elif validate:
        for unit_id in units:
            if unit_id in completed or unit_id not in full or unit_id in blocked:
                continue
            if unit_id in correct:
                complete(unit_id)
            else:
                blocked.add(unit_id)

    ordered_completed = [unit_id for unit_id in units if unit_id in completed]
    state["progressive_completed"] = ordered_completed
    state["progressive_authors"] = {unit_id: authors[unit_id] for unit_id in ordered_completed if unit_id in authors}
    state["progressive_blocked"] = [unit_id for unit_id in units if unit_id in blocked]
    state["progressive_active"] = next((unit_id for unit_id in sequence if unit_id not in completed), "") if ordered else ""
    return state


def check_answer(answer: str, solution_payload: dict) -> tuple[bool, int, int]:
    supplied = flat_answer_from_payload(answer)
    expected = {
        f"{col},{row}": str(value)
        for row, line in enumerate(solution_payload.get("grid", []))
        for col, value in enumerate(line)
    }
    givens = {str(key): str(value) for key, value in solution_payload.get("givens", {}).items()}
    supplied = {**givens, **supplied}
    matched = sum(1 for key, value in expected.items() if supplied.get(key) == value)
    return matched == len(expected), len(expected), matched


def normalize_progress(payload: Any, solution_payload: dict) -> dict:
    supplied = flat_answer_from_payload(getattr(payload, "answers", {}) if payload is not None else {})
    givens = {str(key): str(value) for key, value in solution_payload.get("givens", {}).items()}
    return {"answers": {key: value for key, value in supplied.items() if key not in givens}}


_cell_collaboration = cell_collaboration(normalize_progress)


def sudoku_collaboration(state: dict, action: dict, solution_payload: dict) -> dict:
    units, _expected, _combined, progressive = progressive_unit_state(state, solution_payload)
    if units and progressive.get("lock_completed") and action.get("kind") == "patch":
        completed = set(state.get("progressive_completed", []))
        locked = {key for unit_id in completed for key in units.get(unit_id, [])}
        if locked.intersection(action.get("changes", {})):
            raise ValueError("Completed Sudoku units are locked")
    base_action = action if action.get("kind") != "progressive_check" else {**action, "kind": "patch", "changes": {}}
    updated = _cell_collaboration(state, base_action, solution_payload)
    return update_progressive_state(updated, action, solution_payload)


def count_progress(progress_payload: dict, solution_payload: dict) -> tuple[int, int]:
    expected = {
        f"{col},{row}": str(value)
        for row, line in enumerate(solution_payload.get("grid", []))
        for col, value in enumerate(line)
    }
    givens = {str(key): str(value) for key, value in solution_payload.get("givens", {}).items()}
    supplied = progress_payload.get("answers", {}) if isinstance(progress_payload, dict) else {}
    if not isinstance(supplied, dict):
        supplied = {}
    combined = {**givens, **{str(key): str(value) for key, value in supplied.items()}}
    total = len(expected)
    complete = total > 0 and all(combined.get(key) == value for key, value in expected.items())
    filled = sum(1 for key in expected if combined.get(key))
    return (total if complete else min(filled, max(0, total - 1))), total


def build_preview(print_payload: dict, play_payload: dict, metadata: dict) -> dict:
    payload = print_payload if isinstance(print_payload, dict) else play_payload
    grid = payload.get("grid", []) if isinstance(payload, dict) else []
    givens = payload.get("givens", {}) if isinstance(payload, dict) else {}
    settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
    return {
        "kind": "sudoku",
        "grid": grid[:9],
        "givens": {str(key): str(value) for key, value in givens.items()} if isinstance(givens, dict) else {},
        "size": int(settings.get("grid_size", len(grid) or 9)),
        "box_rows": int(settings.get("box_rows", 3)),
        "box_cols": int(settings.get("box_cols", 3)),
        "meta": f"{len(givens) if isinstance(givens, dict) else 0} givens",
    }


def generate(
    theme: str,
    difficulty: str,
    _source_data: Any = None,
    seed: str | None = None,
    _generation_options: dict[str, Any] | None = None,
) -> GeneratedPuzzle:
    generation_options = _generation_options or {}
    generation_seed = seed or f"sudoku:{theme}:{difficulty}"
    rng = random.Random(generation_seed)
    size, box_rows, box_cols = sudoku_shape(generation_options)
    given_count = integer_option(generation_options, "given_count", 0, 0, size * size - 1) or None
    symmetry = str(generation_options.get("symmetry", "random")).strip().lower()
    if symmetry not in {"random", "rotational", "mirrored"}:
        symmetry = "random"
    check_mode = str(generation_options.get("check_mode", "check_puzzle")).strip().lower()
    if check_mode not in {"none", "check_cell", "check_puzzle"}:
        check_mode = "check_puzzle"
    show_candidate_notes = bool_option(generation_options, "candidate_notes", False)
    require_unique = bool_option(generation_options, "require_unique", True)
    solution, puzzle, uniqueness_verified = unique_puzzle(
        rng,
        difficulty,
        size,
        box_rows,
        box_cols,
        given_count,
        symmetry,
        require_unique,
    )
    givens = given_cells(puzzle)
    blank_count = size * size - len(givens)
    settings = {
        "grid_size": size,
        "box_rows": box_rows,
        "box_cols": box_cols,
        "symmetry": symmetry,
        "candidate_notes": show_candidate_notes,
        "check_mode": check_mode,
        "uniqueness_verified": uniqueness_verified,
        "progressive": progressive_settings(generation_options, size, box_rows, box_cols),
    }
    payload = {
        "kind": "sudoku",
        "grid": puzzle,
        "givens": givens,
        "settings": settings,
    }
    solution_payload = {
        "grid": solution,
        "givens": givens,
        "settings": settings,
    }
    title_prefix = theme.replace("_", " ").replace("-", " ").title().strip()
    title = f"{title_prefix} Sudoku" if title_prefix else "Sudoku"
    return GeneratedPuzzle(
        title=title,
        prompt=f"Fill every row, column, and {box_rows}x{box_cols} box with digits 1 through {size}.",
        print_payload=payload,
        play_payload=payload,
        solution_payload=solution_payload,
        hints=[
            f"Each row must contain 1 through {size} without repeats.",
            f"Each column must contain 1 through {size} without repeats.",
            f"Each {box_rows}x{box_cols} box must contain 1 through {size} without repeats.",
            f"This puzzle starts with {len(givens)} givens and {blank_count} blanks.",
        ],
        metadata={
            "generator": "local.sudoku.v1",
            "seed": generation_seed,
            "givens": len(givens),
            "blanks": blank_count,
            "generation_options": settings | {"given_count": len(givens)},
        },
    )


def build_manual_puzzle(options: dict[str, Any]) -> GeneratedPuzzle:
    if str(options.get("solution_grid") or "").strip():
        return build_manual_grid_puzzle(options)
    theme = str(options.get("_theme") or "").strip()
    difficulty = str(options.get("_difficulty") or "medium").strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"
    generated = generate(theme, difficulty, None, str(options.get("seed") or "") or None, options)
    return GeneratedPuzzle(
        title="Manual Sudoku",
        prompt=generated.prompt,
        print_payload=generated.print_payload,
        play_payload=generated.play_payload,
        solution_payload=generated.solution_payload,
        hints=generated.hints,
        metadata={
            **generated.metadata,
            "generator": "manual.sudoku.v1",
            "manual": True,
        },
    )


def parse_manual_grid(value: Any) -> Grid:
    rows = []
    for line in str(value or "").splitlines():
        digits = [int(char) for char in line if char.isdigit() and char != "0"]
        if digits:
            rows.append(digits)
    if not rows:
        raise ValueError("Sudoku canvas needs a full solution grid.")
    size = len(rows[0])
    if size not in BOX_DEFAULTS and not (4 <= size <= 9):
        raise ValueError("Sudoku canvas supports grid sizes 4 through 9.")
    if len(rows) != size or any(len(row) != size for row in rows):
        raise ValueError("Sudoku solution grid must be square.")
    return rows


def parse_manual_givens(value: Any, solution: Grid) -> dict[str, str]:
    givens = {}
    size = len(solution)
    for line in str(value or "").splitlines():
        cleaned = line.replace("=", ",").replace(":", ",")
        parts = [part.strip() for part in cleaned.split(",") if part.strip()]
        if len(parts) < 3:
            continue
        try:
            x, y, digit = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if 0 <= x < size and 0 <= y < size and solution[y][x] == digit:
            givens[f"{x},{y}"] = str(digit)
    if not givens:
        givens = given_cells(solution)
    return givens


def validate_manual_solution(solution: Grid, box_rows: int, box_cols: int) -> None:
    size = len(solution)
    expected = set(range(1, size + 1))
    for row in solution:
        if set(row) != expected:
            raise ValueError("Each Sudoku solution row must contain every digit once.")
    for col in range(size):
        if {solution[row][col] for row in range(size)} != expected:
            raise ValueError("Each Sudoku solution column must contain every digit once.")
    for top in range(0, size, box_rows):
        for left in range(0, size, box_cols):
            box = {solution[row][col] for row in range(top, top + box_rows) for col in range(left, left + box_cols)}
            if box != expected:
                raise ValueError("Each Sudoku box must contain every digit once.")


def build_manual_grid_puzzle(options: dict[str, Any]) -> GeneratedPuzzle:
    solution = parse_manual_grid(options.get("solution_grid", ""))
    size = len(solution)
    if str(options.get("grid_size") or "").strip().lower() == "custom":
        box_rows = integer_option(options, "box_rows", BOX_DEFAULTS.get(size, (3, 3))[0], 1, size)
        box_cols = integer_option(options, "box_cols", BOX_DEFAULTS.get(size, (3, 3))[1], 1, size)
    else:
        box_rows, box_cols = BOX_DEFAULTS.get(size, (3, 3))
    if box_rows * box_cols != size:
        raise ValueError("Sudoku canvas box rows x box columns must equal grid size.")
    validate_manual_solution(solution, box_rows, box_cols)
    givens = parse_manual_givens(options.get("givens", ""), solution)
    puzzle = [[solution[row][col] if f"{col},{row}" in givens else 0 for col in range(size)] for row in range(size)]
    settings = {
        "grid_size": size,
        "box_rows": box_rows,
        "box_cols": box_cols,
        "symmetry": "manual",
        "candidate_notes": bool_option(options, "candidate_notes", False),
        "check_mode": str(options.get("check_mode") or "check_puzzle"),
        "uniqueness_verified": False,
        "progressive": progressive_settings(options, size, box_rows, box_cols),
    }
    payload = {"kind": "sudoku", "grid": puzzle, "givens": givens, "settings": settings}
    return GeneratedPuzzle(
        title="Manual Sudoku",
        prompt=f"Fill every row, column, and {box_rows}x{box_cols} box with digits 1 through {size}.",
        print_payload=payload,
        play_payload=payload,
        solution_payload={"grid": solution, "givens": givens, "settings": settings},
        hints=[
            f"Each row must contain 1 through {size} without repeats.",
            f"Each column must contain 1 through {size} without repeats.",
            f"This manual puzzle starts with {len(givens)} givens.",
        ],
        metadata={
            "generator": "manual.sudoku.canvas.v1",
            "manual": True,
            "givens": len(givens),
            "blanks": size * size - len(givens),
            "generation_options": settings | {"given_count": len(givens)},
        },
    )


PROGRESSIVE_FIELDS = (
    GenerationField(
        name="progressive_solve",
        label="Progressive solve",
        field_type="select",
        default="no",
        help_text="Acknowledge complete rows, columns, or boxes without revealing individual cell correctness.",
        options=(
            {"value": "no", "label": "Off"},
            {"value": "yes", "label": "On"},
        ),
    ),
    GenerationField(
        name="progressive_units",
        label="Progression units",
        field_type="checkboxes",
        default=("row",),
        help_text="Choose one or more unit types.",
        options=(
            {"value": "row", "label": "Rows"},
            {"value": "column", "label": "Columns"},
            {"value": "box", "label": "Boxes"},
        ),
        enabled_when=(("progressive_solve", "yes"),),
    ),
    GenerationField(
        name="progressive_validation",
        label="Unit validation",
        field_type="select",
        default="automatic",
        options=(
            {"value": "automatic", "label": "Automatic when a unit becomes full"},
            {"value": "manual", "label": "Only when Check Units is pressed"},
        ),
        enabled_when=(("progressive_solve", "yes"),),
    ),
    GenerationField(
        name="progressive_mark",
        label="Mark completed cells",
        field_type="select",
        default="yes",
        options=(
            {"value": "yes", "label": "Yes"},
            {"value": "no", "label": "No, show progress list only"},
        ),
        enabled_when=(("progressive_solve", "yes"),),
    ),
    GenerationField(
        name="progressive_lock",
        label="Lock completed units",
        field_type="select",
        default="no",
        options=(
            {"value": "no", "label": "No"},
            {"value": "yes", "label": "Yes"},
        ),
        enabled_when=(("progressive_solve", "yes"),),
    ),
    GenerationField(
        name="progressive_order",
        label="Progression order",
        field_type="select",
        default="any",
        options=(
            {"value": "any", "label": "Any order"},
            {"value": "sequence", "label": "Required sequence"},
        ),
        enabled_when=(("progressive_solve", "yes"),),
    ),
    GenerationField(
        name="progressive_sequence",
        label="Required unit sequence",
        field_type="text",
        default="",
        help_text="Optional. Comma-separated units such as row:1,row:2,column:1. Leave blank for rows, then columns, then boxes.",
        enabled_when=(("progressive_solve", "yes"), ("progressive_order", "sequence")),
    ),
)


register_puzzle_type(
    PuzzleType(
        slug="sudoku",
        collaboration=sudoku_collaboration,
        label="Sudoku",
        generator=generate,
        source_builder=build_source,
        answer_checker=check_answer,
        progress_normalizer=normalize_progress,
        progress_counter=count_progress,
        preview_builder=build_preview,
        description="A classic 9x9 number-placement puzzle.",
        play_script="/plugins/sudoku/static/sudoku.js?v=10",
        **({"supports_offline": True, "offline_progress_fields": ("answers",), "offline_validation": "local_rules", "offline_notes": "Completed grids can be checked against Sudoku rules offline; the server confirms completion after sync."} if "supports_offline" in PuzzleType.__dataclass_fields__ else {}),
        supports_print=True,
        supports_web_play=True,
        theme_mode="none",
        print_layout=PrintLayout(
            slug="sudoku",
            sheet_class="print-layout-sudoku",
            instructions="Fill every row, column, and box with the required digits.",
            notes=("Box boundaries are emphasized for print review.",),
        ),
        manual_builder=build_manual_puzzle,
        manual_editor_fields=(
            GenerationField(
                name="solution_grid",
                label="Canvas solution grid",
                field_type="textarea",
                default="",
                help_text="Managed by the visual editor.",
            ),
            GenerationField(
                name="givens",
                label="Canvas givens",
                field_type="textarea",
                default="",
                help_text="Managed by the visual editor.",
            ),
            GenerationField(
                name="grid_size",
                label="Grid size",
                field_type="select",
                default="9",
                options=(
                    {"value": "4", "label": "4x4"},
                    {"value": "6", "label": "6x6"},
                    {"value": "9", "label": "9x9"},
                    {"value": "custom", "label": "Custom"},
                ),
            ),
            GenerationField(
                name="custom_grid_size",
                label="Custom grid size",
                field_type="number",
                default="",
                help_text="Only used for Custom. Values above 9 are not supported yet.",
                minimum=4,
                maximum=9,
            ),
            GenerationField(
                name="box_rows",
                label="Box rows",
                field_type="number",
                default="",
                help_text="Only used for Custom. Box rows x box columns must equal grid size.",
                minimum=1,
                maximum=9,
            ),
            GenerationField(
                name="box_cols",
                label="Box columns",
                field_type="number",
                default="",
                help_text="Only used for Custom.",
                minimum=1,
                maximum=9,
            ),
            GenerationField(
                name="given_count",
                label="Given count",
                field_type="number",
                default="",
                help_text="Optional. Leave blank to let difficulty choose.",
                minimum=4,
                maximum=80,
            ),
            GenerationField(
                name="symmetry",
                label="Symmetry",
                field_type="select",
                default="random",
                options=(
                    {"value": "random", "label": "Random"},
                    {"value": "rotational", "label": "Rotational"},
                    {"value": "mirrored", "label": "Mirrored"},
                ),
            ),
            GenerationField(
                name="candidate_notes",
                label="Candidate notes",
                field_type="select",
                default="no",
                options=(
                    {"value": "no", "label": "Off"},
                    {"value": "yes", "label": "On"},
                ),
            ),
            GenerationField(
                name="check_mode",
                label="Check mode",
                field_type="select",
                default="check_puzzle",
                options=(
                    {"value": "none", "label": "No checking"},
                    {"value": "check_cell", "label": "Check cell"},
                    {"value": "check_puzzle", "label": "Check puzzle"},
                ),
            ),
            GenerationField(
                name="require_unique",
                label="Require unique solution",
                field_type="select",
                default="yes",
                options=(
                    {"value": "yes", "label": "Yes"},
                    {"value": "no", "label": "No"},
                ),
            ),
            GenerationField(
                name="seed",
                label="Seed",
                field_type="text",
                default="",
                help_text="Optional. Reuse to recreate the same puzzle.",
            ),
        ) + PROGRESSIVE_FIELDS,
        generation_fields=(
            GenerationField(
                name="grid_size",
                label="Grid size",
                field_type="select",
                default="9",
                options=(
                    {"value": "4", "label": "4x4"},
                    {"value": "6", "label": "6x6"},
                    {"value": "9", "label": "9x9"},
                    {"value": "custom", "label": "Custom"},
                ),
            ),
            GenerationField(
                name="custom_grid_size",
                label="Custom grid size",
                field_type="number",
                default="",
                help_text="Only used for Custom. Values above 9 are not supported yet.",
                minimum=4,
                maximum=9,
            ),
            GenerationField(
                name="box_rows",
                label="Box rows",
                field_type="number",
                default="",
                help_text="Only used for Custom. Box rows x box columns must equal grid size.",
                minimum=1,
                maximum=9,
            ),
            GenerationField(
                name="box_cols",
                label="Box columns",
                field_type="number",
                default="",
                help_text="Only used for Custom.",
                minimum=1,
                maximum=9,
            ),
            GenerationField(
                name="given_count",
                label="Given count",
                field_type="number",
                default="",
                help_text="Optional. Leave blank to let difficulty choose.",
                minimum=4,
                maximum=80,
            ),
            GenerationField(
                name="symmetry",
                label="Symmetry",
                field_type="select",
                default="random",
                options=(
                    {"value": "random", "label": "Random"},
                    {"value": "rotational", "label": "Rotational"},
                    {"value": "mirrored", "label": "Mirrored"},
                ),
            ),
            GenerationField(
                name="candidate_notes",
                label="Candidate notes",
                field_type="select",
                default="no",
                options=(
                    {"value": "no", "label": "Off"},
                    {"value": "yes", "label": "On"},
                ),
            ),
            GenerationField(
                name="check_mode",
                label="Check mode",
                field_type="select",
                default="check_puzzle",
                options=(
                    {"value": "none", "label": "No checking"},
                    {"value": "check_cell", "label": "Check cell"},
                    {"value": "check_puzzle", "label": "Check puzzle"},
                ),
            ),
            GenerationField(
                name="require_unique",
                label="Require unique solution",
                field_type="select",
                default="yes",
                options=(
                    {"value": "yes", "label": "Yes"},
                    {"value": "no", "label": "No"},
                ),
            ),
        ) + PROGRESSIVE_FIELDS,
    )
)
