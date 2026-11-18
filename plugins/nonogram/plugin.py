"""Nonogram clue generation and uniqueness validation using OR-Tools CP-SAT."""
from __future__ import annotations

import itertools
import json
import random
import time
import uuid
from functools import lru_cache
from typing import Any

from ortools.sat.python import cp_model

from app.puzzles import GeneratedPuzzle, GenerationField, PrintLayout, PuzzleType, register_puzzle_type
from app.group_actions import cell_collaboration


def runs(line):
    result, length = [], 0
    for value in [*line, 0]:
        if value:
            length += 1
        elif length:
            result.append(length)
            length = 0
    return result or [0]


@lru_cache(maxsize=512)
def line_patterns(size, clues):
    if clues == (0,):
        return (tuple([0] * size),)
    if not clues or any(n <= 0 for n in clues) or sum(clues) + len(clues) - 1 > size:
        raise ValueError("Invalid Nonogram clues")
    slack = size - sum(clues) - len(clues) + 1
    patterns = []
    for gaps in itertools.combinations(range(slack + len(clues)), len(clues)):
        line, previous = [], -1
        for i, length in enumerate(clues):
            line.extend([0] * (gaps[i] - previous - 1))
            line.extend([1] * length)
            if i + 1 < len(clues):
                line.append(0)
            previous = gaps[i]
        line.extend([0] * (size - len(line)))
        patterns.append(tuple(line))
    return tuple(patterns)


def unique_givens(grid, rng, initial_count=0):
    size = len(grid)
    model = cp_model.CpModel()
    cells = [[model.new_bool_var(f"c{x}_{y}") for x in range(size)] for y in range(size)]
    for y in range(size):
        model.add_allowed_assignments(cells[y], line_patterns(size, tuple(runs(grid[y]))))
    for x in range(size):
        model.add_allowed_assignments([cells[y][x] for y in range(size)],
                                     line_patterns(size, tuple(runs([grid[y][x] for y in range(size)]))))
    # Exclude the generated picture. Infeasibility then proves no second answer exists.
    model.add_bool_or([cells[y][x].Not() if grid[y][x] else cells[y][x]
                       for y in range(size) for x in range(size)])
    givens = {}
    coordinates = [(x, y) for y in range(size) for x in range(size)]
    rng.shuffle(coordinates)
    for x, y in coordinates[:initial_count]:
        model.add(cells[y][x] == grid[y][x])
        givens[f"{x},{y}"] = "1" if grid[y][x] else "0"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = min(2, max(0.01, deadline - time.monotonic()))
        solver.parameters.num_search_workers = 1
        status = solver.solve(model)
        if status == cp_model.INFEASIBLE:
            return givens
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        differences = [(x, y) for x, y in coordinates if solver.value(cells[y][x]) != grid[y][x]]
        x, y = rng.choice(differences)
        model.add(cells[y][x] == grid[y][x])
        givens[f"{x},{y}"] = "1" if grid[y][x] else "0"
    raise ValueError("Could not prove a unique Nonogram within the time limit. Try a smaller grid or another seed.")


def answers_from(value, solution):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    if not isinstance(value, dict):
        return {}
    value = value.get("answers", value)
    if not isinstance(value, dict):
        return {}
    size = len(solution.get("grid", []))
    valid = {f"{x},{y}" for y in range(size) for x in range(size)}
    return {str(k): str(v) for k, v in value.items() if k in valid and str(v) in {"0", "1"}}


def normalize_progress(payload, solution):
    answers = answers_from(getattr(payload, "answers", {}) if payload is not None else {}, solution)
    return {"answers": {k: v for k, v in answers.items() if k not in solution.get("givens", {})}}


def count_progress(progress, solution):
    answers = {**answers_from(progress, solution), **solution.get("givens", {})}
    grid = solution.get("grid", [])
    # Unmarked white squares may remain blank, but an incorrect fill or X cannot complete a puzzle.
    complete = all(answers.get(f"{x},{y}", "0") == str(value)
                   for y, row in enumerate(grid) for x, value in enumerate(row))
    total = len(grid) ** 2
    filled = sum(1 for y, row in enumerate(grid) for x, _value in enumerate(row)
                 if answers.get(f"{x},{y}") in ("0", "1"))
    return total if complete else min(filled, max(0, total - 1)), total


def check_answer(answer, solution):
    matched, total = count_progress(answer, solution)
    return total > 0 and matched == total, total, matched


def make_puzzle(grid, difficulty, seed, options):
    size = len(grid)
    if not 5 <= size <= 15 or any(len(row) != size or any(type(v) is not int or v not in (0, 1) for v in row) for row in grid):
        raise ValueError("Nonogram grids must be square, 5 to 15 cells, and contain only 0 and 1.")
    if not any(any(row) for row in grid):
        raise ValueError("The picture must contain at least one filled cell.")
    try:
        initial = int(options.get("gimme_count") or 0)
    except (ValueError, TypeError):
        raise ValueError("Gimme count must be a number.")
    if not 0 <= initial < size * size:
        raise ValueError("Gimme count must be smaller than the number of cells.")
    givens = unique_givens(grid, random.Random(seed), initial)
    auto_confirm = str(options.get("auto_confirm_rows", "yes")).lower() in {"yes", "true", "1", "on"}
    payload = {"kind": "nonogram", "size": size, "row_clues": [runs(row) for row in grid],
               "column_clues": [runs([grid[y][x] for y in range(size)]) for x in range(size)],
               "givens": givens, "settings": {"grid_size": size, "uniqueness_verified": True,
                                              "auto_confirm_rows": auto_confirm,
                                              "auto_confirm_columns": str(options.get("auto_confirm_columns", "yes")).lower() in {"yes", "true", "1", "on"}}}
    return GeneratedPuzzle(
        title=f"{size}x{size} Nonogram", prompt="Fill cells to match the numbered runs in each row and column. Separate runs with at least one empty cell.",
        print_payload=payload, play_payload=payload,
        solution_payload={"grid": grid, "givens": givens},
        hints=["Numbers give filled runs in order, not individual cell positions.",
               "A zero means the entire line is empty.", "Start with long runs and lines that fill the available space."],
        metadata={"generator": "local.nonogram.v1", "seed": seed, "uniqueness_verified": True,
                  "generation_options": {**options, "grid_size": size}, "givens": len(givens)},
    )


def generate(theme, difficulty, source_data=None, seed=None, generation_options=None):
    options = generation_options or {}
    try:
        size = int(options.get("grid_size") or {"easy": 5, "medium": 10, "hard": 15}.get(difficulty, 10))
    except (ValueError, TypeError):
        raise ValueError("Grid size must be a number.")
    if not 5 <= size <= 15:
        raise ValueError("Grid size must be between 5 and 15.")
    seed = seed or uuid.uuid4().hex
    rng = random.Random(seed)
    symmetry = options.get("symmetry", "mirror")
    if symmetry not in {"mirror", "rotational", "random"}:
        raise ValueError("Unknown symmetry.")
    grid = [[int(rng.random() < 0.55) for _ in range(size)] for _ in range(size)]
    for y in range(size):
        for x in range(size):
            if symmetry == "mirror" and x >= (size + 1) // 2:
                grid[y][x] = grid[y][size - x - 1]
            elif symmetry == "rotational" and y * size + x >= size * size // 2:
                grid[y][x] = grid[size - y - 1][size - x - 1]
    return make_puzzle(grid, difficulty, seed, options)


def build_manual(options):
    raw = options.get("solution_grid", "")
    try:
        grid = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        raise ValueError("Solution grid must be a JSON array of rows of 0 and 1.")
    if not isinstance(grid, list) or any(not isinstance(row, list) for row in grid):
        raise ValueError("Solution grid must contain rows.")
    return make_puzzle(grid, "custom", str(options.get("seed") or uuid.uuid4().hex), options)


register_puzzle_type(PuzzleType(
    slug="nonogram", label="Nonogram / Picross", description="Picture logic grids with numbered row and column runs.",
    collaboration=cell_collaboration(normalize_progress),
    generator=generate, source_builder=lambda *_: {}, answer_checker=check_answer,
    progress_normalizer=normalize_progress, progress_counter=count_progress, theme_mode="none",
    print_layout=PrintLayout(slug="nonogram", sheet_class="print-layout-nonogram"),
    generation_fields=(
        GenerationField("grid_size", "Grid size", "number", "10", minimum=5, maximum=15),
        GenerationField("symmetry", "Picture symmetry", "select", "mirror", options=(
            {"value": "mirror", "label": "Mirrored"}, {"value": "rotational", "label": "Rotational"},
            {"value": "random", "label": "Random"})),
        GenerationField("gimme_count", "Starter cells", "number", "0", minimum=0, maximum=224,
                        help_text="Extra starter cells may be added to guarantee one solution."),
        GenerationField("auto_confirm_rows", "Auto-confirm completed rows", "select", "yes", options=(
            {"value": "yes", "label": "On"}, {"value": "no", "label": "Off"})),
        GenerationField("auto_confirm_columns", "Auto-confirm completed columns", "select", "yes", options=(
            {"value": "yes", "label": "On"}, {"value": "no", "label": "Off"})),
    ),
    manual_builder=build_manual,
    manual_editor_script="/plugins/nonogram/static/nonogram-editor.js?v=1",
    manual_editor_fields=(GenerationField("solution_grid", "Picture grid", "textarea", required=True,
                                         help_text="JSON rows: 1 for filled, 0 for empty. Square grids from 5 to 15."),
                          GenerationField("auto_confirm_rows", "Auto-confirm completed rows", "select", "yes", options=(
                              {"value": "yes", "label": "On"}, {"value": "no", "label": "Off"})),
                          GenerationField("auto_confirm_columns", "Auto-confirm completed columns", "select", "yes", options=(
                              {"value": "yes", "label": "On"}, {"value": "no", "label": "Off"}))),
))
