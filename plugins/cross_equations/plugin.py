from __future__ import annotations

import json
import random
from itertools import product
from typing import Any

from app.puzzles import GeneratedPuzzle, GenerationField, PrintLayout, PuzzleType, register_puzzle_type
from app.group_actions import cell_collaboration


DigitGrid = list[list[int]]
OpGrid = list[list[str]]


DEFAULT_GRID_SIZE = 3
MAX_GRID_SIZE = 5


def digit_coords(grid_size: int = DEFAULT_GRID_SIZE) -> list[tuple[int, int]]:
    return [(x * 2, y * 2) for y in range(grid_size) for x in range(grid_size)]


def build_source(_source_entries: Any, _difficulty: str, _excluded_tag_ids: set[int] | None = None) -> dict:
    return {}


def apply_operator(
    left: int,
    right: int,
    operator: str,
    result_min: int = 1,
    result_max: int = 9,
    whole_number_division: bool = True,
) -> int | None:
    if operator == "+":
        value = left + right
    elif operator == "-":
        value = left - right
    elif operator == "x":
        value = left * right
    elif operator == "/":
        if right == 0:
            return None
        if whole_number_division:
            if left % right != 0:
                return None
            value = left // right
        else:
            quotient = left / right
            if quotient != int(quotient):
                return None
            value = int(quotient)
    else:
        return None
    return value if result_min <= value <= result_max else None


def apply_operator_sequence(
    values: list[int],
    operators: list[str],
    result_min: int = 1,
    result_max: int = 9,
    whole_number_division: bool = True,
) -> int | None:
    if not values or len(operators) != len(values) - 1:
        return None
    current = values[0]
    for operator, value in zip(operators, values[1:], strict=False):
        current = apply_operator(current, value, operator, result_min, result_max, whole_number_division)
        if current is None:
            return None
    return current


def operator_choices_from_options(options: dict[str, Any], difficulty: str) -> list[str]:
    raw_choices = options.get("operators", [])
    if isinstance(raw_choices, str):
        raw_choices = [value.strip() for value in raw_choices.split(",") if value.strip()]
    choices = [str(value).strip() for value in raw_choices if str(value).strip()]
    valid = ["+", "-", "x", "/"]
    selected = [operator for operator in valid if operator in choices]
    if selected:
        return selected

    operator_set = str(options.get("operator_set") or "").strip()
    if operator_set == "difficulty_default":
        operator_set = ""
    allow_division = bool_option(options, "allow_division", True)
    return allowed_operators(difficulty, operator_set, allow_division)


def allowed_operators(difficulty: str, operator_set: str = "", allow_division: bool = True) -> list[str]:
    if operator_set == "add_subtract":
        return ["+", "-"]
    if operator_set == "add_subtract_multiply":
        return ["+", "-", "x"]
    if operator_set == "all":
        return ["+", "-", "x", "/"] if allow_division else ["+", "-", "x"]
    if difficulty == "hard":
        return ["+", "-", "x", "/"] if allow_division else ["+", "-", "x"]
    if difficulty == "medium":
        return ["+", "-", "x"]
    return ["+", "-"]


def find_solution(
    rng: random.Random,
    difficulty: str,
    operators: list[str] | None = None,
    number_max: int = 9,
    result_min: int = 1,
    result_max: int = 9,
    whole_number_division: bool = True,
    grid_size: int = DEFAULT_GRID_SIZE,
) -> tuple[DigitGrid, OpGrid]:
    operators = operators or allowed_operators(difficulty)
    fallback_base = [[1 for _x in range(grid_size - 1)] for _y in range(grid_size - 1)]
    fallback_digits = build_solution_from_base(
        fallback_base,
        [["+" for _x in range(grid_size - 2)] for _y in range(grid_size)],
        [["+" for _x in range(grid_size - 2)] for _y in range(grid_size)],
        result_min,
        result_max,
        whole_number_division,
    ) or [[1 for _x in range(grid_size)] for _y in range(grid_size)]
    fallback_ops = [
        [["+" for _x in range(grid_size - 2)] for _y in range(grid_size)],
        [["+" for _x in range(grid_size - 2)] for _y in range(grid_size)],
    ]

    for _attempt in range(12000):
        base = [[rng.randint(1, number_max) for _x in range(grid_size - 1)] for _y in range(grid_size - 1)]
        row_ops = [[rng.choice(operators) for _x in range(grid_size - 2)] for _y in range(grid_size)]
        col_ops = [[rng.choice(operators) for _y in range(grid_size - 2)] for _x in range(grid_size)]
        solution = build_solution_from_base(base, row_ops, col_ops, result_min, result_max, whole_number_division)
        if solution is None:
            continue
        return solution, [row_ops, col_ops]

    return fallback_digits, fallback_ops


def build_solution_from_base(
    base: list[list[int]],
    row_ops: list[list[str]],
    col_ops: list[list[str]],
    result_min: int,
    result_max: int,
    whole_number_division: bool,
) -> DigitGrid | None:
    grid_size = len(row_ops)
    solution = [[0 for _x in range(grid_size)] for _y in range(grid_size)]
    for y in range(grid_size - 1):
        for x in range(grid_size - 1):
            solution[y][x] = base[y][x]

    for y in range(grid_size - 1):
        value = apply_operator_sequence(solution[y][: grid_size - 1], row_ops[y], result_min, result_max, whole_number_division)
        if value is None:
            return None
        solution[y][grid_size - 1] = value

    for x in range(grid_size - 1):
        value = apply_operator_sequence(
            [solution[y][x] for y in range(grid_size - 1)],
            col_ops[x],
            result_min,
            result_max,
            whole_number_division,
        )
        if value is None:
            return None
        solution[grid_size - 1][x] = value

    row_value = apply_operator_sequence(solution[grid_size - 1][: grid_size - 1], row_ops[grid_size - 1], result_min, result_max, whole_number_division)
    col_value = apply_operator_sequence(
        [solution[y][grid_size - 1] for y in range(grid_size - 1)],
        col_ops[grid_size - 1],
        result_min,
        result_max,
        whole_number_division,
    )
    if row_value is None or row_value != col_value:
        return None
    solution[grid_size - 1][grid_size - 1] = row_value
    return solution


def derive_solution(
    a: int,
    b: int,
    d: int,
    e: int,
    ops: OpGrid,
    result_min: int = 1,
    result_max: int = 9,
    whole_number_division: bool = True,
) -> DigitGrid | None:
    c = apply_operator(a, b, ops[0][0][0], result_min, result_max, whole_number_division)
    f = apply_operator(d, e, ops[0][1][0], result_min, result_max, whole_number_division)
    g = apply_operator(a, d, ops[1][0][0], result_min, result_max, whole_number_division)
    h = apply_operator(b, e, ops[1][1][0], result_min, result_max, whole_number_division)
    if None in (c, f, g, h):
        return None

    i_from_row = apply_operator(g, h, ops[0][2][0], result_min, result_max, whole_number_division)
    i_from_col = apply_operator(c, f, ops[1][2][0], result_min, result_max, whole_number_division)
    if i_from_row is None or i_from_row != i_from_col:
        return None

    return [[a, b, c], [d, e, f], [g, h, i_from_row]]


def solution_matches_givens(solution: DigitGrid, givens: dict[str, str]) -> bool:
    return all(str(solution[int(y) // 2][int(x) // 2]) == str(value) for key, value in givens.items() for x, y in [key.split(",", 1)])


def count_solutions(
    ops: OpGrid,
    givens: dict[str, str],
    number_max: int = 9,
    result_min: int = 1,
    result_max: int = 9,
    whole_number_division: bool = True,
    limit: int = 2,
) -> int:
    found = 0
    for a, b, d, e in product(range(1, number_max + 1), repeat=4):
        solution = derive_solution(a, b, d, e, ops, result_min, result_max, whole_number_division)
        if solution is None or not solution_matches_givens(solution, givens):
            continue
        found += 1
        if found >= limit:
            return found
    return found


def find_unique_puzzle(
    rng: random.Random,
    difficulty: str,
    operators: list[str] | None = None,
    requested_given_count: int | None = None,
    number_max: int = 9,
    result_min: int = 1,
    result_max: int = 9,
    whole_number_division: bool = True,
    grid_size: int = DEFAULT_GRID_SIZE,
) -> tuple[DigitGrid, OpGrid, dict[str, str]]:
    fallback_digits = [[1, 2, 3], [3, 1, 4], [4, 3, 7]]
    fallback_ops = [[["+"], ["+"], ["+"]], [["+"], ["+"], ["+"]]]

    if grid_size != DEFAULT_GRID_SIZE:
        solution, ops = find_solution(
            rng,
            difficulty,
            operators,
            number_max,
            result_min,
            result_max,
            whole_number_division,
            grid_size,
        )
        givens = given_cells(solution, difficulty, rng, requested_given_count)
        return solution, ops, givens

    for _attempt in range(12000):
        solution, ops = find_solution(
            rng,
            difficulty,
            operators,
            number_max,
            result_min,
            result_max,
            whole_number_division,
            grid_size,
        )
        givens = given_cells(solution, difficulty, rng, requested_given_count)
        if count_solutions(ops, givens, number_max, result_min, result_max, whole_number_division) == 1:
            return solution, ops, givens

    fallback_givens = {
        "0,0": "1",
        "2,0": "2",
        "0,2": "3",
        "2,2": "1",
        "4,2": "4",
    }
    return fallback_digits, fallback_ops, fallback_givens


def given_cells(
    solution: DigitGrid,
    difficulty: str,
    rng: random.Random,
    requested_count: int | None = None,
) -> dict[str, str]:
    grid_size = len(solution)
    given_count = requested_count or {"easy": 4, "medium": 3, "hard": 2}.get(difficulty, 3)
    given_count = max(2, min((grid_size * grid_size) - 1, given_count))
    coords = digit_coords(grid_size)
    rng.shuffle(coords)
    return {f"{x},{y}": str(solution[y // 2][x // 2]) for x, y in coords[:given_count]}


def symbol_cell(value: str) -> dict:
    return {"type": "symbol", "value": value}


def spacer_cell() -> dict:
    return {"type": "spacer", "value": ""}


def number_cell(x: int, y: int, solution: DigitGrid, givens: dict[str, str], include_solution: bool = False) -> dict:
    key = f"{x},{y}"
    value = solution[y // 2][x // 2]
    cell = {
        "type": "number",
        "key": key,
        "value": int(givens[key]) if key in givens else 0,
        "given": key in givens,
    }
    if include_solution:
        cell["solution"] = value
    return cell


def build_cells(solution: DigitGrid, ops: OpGrid, givens: dict[str, str], include_solution: bool = False) -> list[list[dict]]:
    grid_size = len(solution)
    rendered_size = grid_size * 2 - 1
    cells = []
    row_ops, col_ops = ops
    for rendered_y in range(rendered_size):
        row = []
        for rendered_x in range(rendered_size):
            if rendered_x % 2 == 0 and rendered_y % 2 == 0:
                row.append(number_cell(rendered_x, rendered_y, solution, givens, include_solution))
            elif rendered_y % 2 == 0:
                number_x = rendered_x // 2
                number_y = rendered_y // 2
                row.append(symbol_cell("=" if number_x == grid_size - 2 else row_ops[number_y][number_x]))
            elif rendered_x % 2 == 0:
                number_x = rendered_x // 2
                number_y = rendered_y // 2
                row.append(symbol_cell("=" if number_y == grid_size - 2 else col_ops[number_x][number_y]))
            else:
                row.append(spacer_cell())
        cells.append(row)
    return cells


def equation_text(values: list[int], operators: list[str]) -> str:
    expression = " ".join(str(value) if index == 0 else f"{operators[index - 1]} {value}" for index, value in enumerate(values[:-1]))
    return f"{expression} = {values[-1]}"


def equations(solution: DigitGrid, ops: OpGrid) -> list[dict]:
    grid_size = len(solution)
    row_ops, col_ops = ops
    items = []
    for y in range(grid_size):
        items.append(
            {
                "number": y + 1,
                "direction": "across",
                "label": f"Across {y + 1}",
                "cells": [f"{x * 2},{y * 2}" for x in range(grid_size)],
                "equation": equation_text(solution[y], row_ops[y]),
            }
        )
    for x in range(grid_size):
        items.append(
            {
                "number": x + 1,
                "direction": "down",
                "label": f"Down {x + 1}",
                "cells": [f"{x * 2},{y * 2}" for y in range(grid_size)],
                "equation": equation_text([solution[y][x] for y in range(grid_size)], col_ops[x]),
            }
        )
    return items


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
            return {f"{x},{y}": digit for (x, y), digit in zip(digit_coords(), digits, strict=False)}
    if not isinstance(value, dict):
        return {}
    answers = value.get("answers", value)
    if not isinstance(answers, dict):
        return {}
    normalized = {}
    for key, raw_value in answers.items():
        text = str(raw_value).strip()
        if str(key) and text.lstrip("-").isdigit():
            normalized[str(key)] = text
    return normalized


def expected_answers(solution_payload: dict) -> dict[str, str]:
    answers = solution_payload.get("answers", {})
    if not isinstance(answers, dict):
        return {}
    return {str(key): str(value) for key, value in answers.items()}


def check_answer(answer: str, solution_payload: dict) -> tuple[bool, int, int]:
    supplied = flat_answer_from_payload(answer)
    givens = {str(key): str(value) for key, value in solution_payload.get("givens", {}).items()}
    expected = expected_answers(solution_payload)
    supplied = {**givens, **supplied}
    matched = sum(1 for key, value in expected.items() if supplied.get(key) == value)
    return matched == len(expected), len(expected), matched


def normalize_progress(payload: Any, solution_payload: dict) -> dict:
    supplied = flat_answer_from_payload(getattr(payload, "answers", {}) if payload is not None else {})
    givens = {str(key): str(value) for key, value in solution_payload.get("givens", {}).items()}
    return {"answers": {key: value for key, value in supplied.items() if key not in givens}}


def count_progress(progress_payload: dict, solution_payload: dict) -> tuple[int, int]:
    expected = expected_answers(solution_payload)
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
    cells = payload.get("cells", []) if isinstance(payload, dict) else []
    settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
    givens = payload.get("givens", {}) if isinstance(payload, dict) else {}
    return {
        "kind": "cross_equations",
        "cells": cells[:9],
        "size": int(settings.get("rendered_size", len(cells) or 5)),
        "meta": f"{len(givens) if isinstance(givens, dict) else 0} starters",
    }


def integer_option(options: dict[str, Any], key: str) -> int | None:
    try:
        return int(str(options.get(key, "")).strip())
    except (TypeError, ValueError):
        return None


def bool_option(options: dict[str, Any], key: str, default: bool) -> bool:
    raw = str(options.get(key, "")).strip().lower()
    if raw in {"yes", "true", "1", "on"}:
        return True
    if raw in {"no", "false", "0", "off"}:
        return False
    return default


def ranged_integer_option(options: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    value = integer_option(options, key)
    if value is None:
        value = default
    return max(minimum, min(maximum, value))


def number_max_option(options: dict[str, Any]) -> int:
    value = str(options.get("number_range", "1-9")).strip()
    return {"1-9": 9, "1-12": 12, "1-20": 20}.get(value, 9)


def result_limits(options: dict[str, Any], number_max: int) -> tuple[int, int]:
    constraint = str(options.get("result_constraints", "positive_only")).strip().lower()
    if constraint == "allow_negative":
        return -number_max * number_max, number_max * number_max
    if constraint == "allow_zero":
        return 0, number_max * number_max
    return 1, number_max * number_max


def generate(
    theme: str,
    difficulty: str,
    _source_data: Any = None,
    seed: str | None = None,
    generation_options: dict[str, Any] | None = None,
) -> GeneratedPuzzle:
    generation_seed = seed or f"cross_equations:{theme}:{difficulty}"
    rng = random.Random(generation_seed)
    generation_options = generation_options or {}
    operators = operator_choices_from_options(generation_options, difficulty)
    grid_size = ranged_integer_option(generation_options, "grid_size", DEFAULT_GRID_SIZE, DEFAULT_GRID_SIZE, MAX_GRID_SIZE)
    custom_grid_size = integer_option(generation_options, "custom_grid_size")
    if str(generation_options.get("grid_size", "")).strip().lower() == "custom" and custom_grid_size is not None:
        grid_size = max(DEFAULT_GRID_SIZE, min(MAX_GRID_SIZE, custom_grid_size))
    number_max = number_max_option(generation_options)
    result_min, result_max = result_limits(generation_options, number_max)
    whole_number_division = bool_option(generation_options, "whole_number_division", True)
    allow_multiple_operations = bool_option(generation_options, "allow_multiple_operations", grid_size > DEFAULT_GRID_SIZE)
    if grid_size > DEFAULT_GRID_SIZE:
        allow_multiple_operations = True
    allow_multiple_equations = bool_option(generation_options, "allow_multiple_equations", False)
    difficulty_style = str(generation_options.get("difficulty_style", "balanced")).strip().lower()
    if difficulty_style not in {"more_givens", "balanced", "harder_operators"}:
        difficulty_style = "balanced"
    if difficulty_style == "more_givens":
        requested_default = {"easy": 6, "medium": 5, "hard": 4}.get(difficulty, 5)
    else:
        requested_default = {"easy": 4, "medium": 3, "hard": 2}.get(difficulty, 3)
    given_count = integer_option(generation_options, "given_count") or requested_default
    if difficulty_style == "harder_operators" and "operators" not in generation_options and not generation_options.get("operator_set"):
        operators = ["+", "-", "x", "/"]
    solution, ops, givens = find_unique_puzzle(
        rng,
        difficulty,
        operators,
        given_count,
        number_max,
        result_min,
        result_max,
        whole_number_division,
        grid_size,
    )
    answer_map = {f"{x},{y}": str(solution[y // 2][x // 2]) for x, y in digit_coords(grid_size)}
    equation_list = equations(solution, ops)
    payload = {
        "kind": "cross_equations",
        "cells": build_cells(solution, ops, givens),
        "givens": givens,
        "equations": [{"number": item["number"], "direction": item["direction"], "label": item["label"], "cells": item["cells"]} for item in equation_list],
        "settings": {
            "grid_size": grid_size,
            "number_range": f"1-{number_max}",
            "operators": operators,
            "whole_number_division": whole_number_division,
            "allow_multiple_operations": allow_multiple_operations,
            "allow_multiple_equations": allow_multiple_equations,
            "result_min": result_min,
            "result_max": result_max,
            "difficulty_style": difficulty_style,
            "rendered_size": grid_size * 2 - 1,
        },
    }
    solution_payload = {
        "answers": answer_map,
        "givens": givens,
        "cells": build_cells(solution, ops, answer_map, include_solution=True),
        "equations": equation_list,
    }
    blank_count = len(answer_map) - len(givens)
    title_prefix = theme.replace("_", " ").replace("-", " ").title().strip()
    title = f"{title_prefix} Cross Equations" if title_prefix else "Cross Equations"
    return GeneratedPuzzle(
        title=title,
        prompt="Fill the shared number cells so every across and down equation is true.",
        print_payload=payload,
        play_payload=payload,
        solution_payload=solution_payload,
        hints=[
            "Each row with numbers is an across equation.",
            "Each column with numbers is a down equation.",
            "A shared cell must satisfy both its across and down equation.",
            f"This puzzle starts with {len(givens)} givens and {blank_count} blanks.",
        ],
        metadata={
            "generator": "local.cross_equations.v1",
            "seed": generation_seed,
            "givens": len(givens),
            "blanks": blank_count,
            "operators": sorted({operator for group in ops for row in group for operator in row if operator}),
            "generation_options": {
                "operators": operators,
                "given_count": len(givens),
                "grid_size": grid_size,
                "number_range": f"1-{number_max}",
                "whole_number_division": whole_number_division,
                "allow_multiple_operations": allow_multiple_operations,
                "allow_multiple_equations": allow_multiple_equations,
                "result_min": result_min,
                "result_max": result_max,
                "difficulty_style": difficulty_style,
            },
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
        title="Manual Cross Equations",
        prompt=generated.prompt,
        print_payload=generated.print_payload,
        play_payload=generated.play_payload,
        solution_payload=generated.solution_payload,
        hints=generated.hints,
        metadata={
            **generated.metadata,
            "generator": "manual.cross_equations.v1",
            "manual": True,
        },
    )


def parse_manual_number_grid(value: Any) -> DigitGrid:
    rows = []
    for line in str(value or "").splitlines():
        parts = [part.strip() for part in line.replace(" ", ",").split(",") if part.strip()]
        if not parts:
            continue
        try:
            rows.append([int(part) for part in parts])
        except ValueError as error:
            raise ValueError("Cross Equations number grid must contain numbers only.") from error
    if not rows:
        raise ValueError("Cross Equations canvas needs a number grid.")
    size = len(rows[0])
    if size < DEFAULT_GRID_SIZE or size > MAX_GRID_SIZE or len(rows) != size or any(len(row) != size for row in rows):
        raise ValueError("Cross Equations number grid must be square, 3x3 to 5x5.")
    return rows


def parse_manual_ops(value: Any, grid_size: int, fallback: str = "+") -> list[list[str]]:
    valid = {"+", "-", "x", "/"}
    operator_count = max(1, grid_size - 2)
    rows = []
    for line in str(value or "").splitlines():
        parts = [part.strip().replace("*", "x") for part in line.replace(" ", ",").split(",") if part.strip()]
        if parts:
            rows.append([part if part in valid else fallback for part in parts[:operator_count]])
    while len(rows) < grid_size:
        rows.append([fallback for _ in range(operator_count)])
    return [(row + [fallback for _ in range(operator_count)])[:operator_count] for row in rows[:grid_size]]


def parse_manual_cross_givens(value: Any, solution: DigitGrid) -> dict[str, str]:
    givens = {}
    grid_size = len(solution)
    for line in str(value or "").splitlines():
        cleaned = line.replace("=", ",").replace(":", ",")
        parts = [part.strip() for part in cleaned.split(",") if part.strip()]
        if len(parts) < 3:
            continue
        try:
            x, y, digit = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if x % 2 == 0 and y % 2 == 0 and 0 <= x // 2 < grid_size and 0 <= y // 2 < grid_size and solution[y // 2][x // 2] == digit:
            givens[f"{x},{y}"] = str(digit)
    if not givens:
        givens = {"0,0": str(solution[0][0])}
    return givens


def build_manual_grid_puzzle(options: dict[str, Any]) -> GeneratedPuzzle:
    solution = parse_manual_number_grid(options.get("solution_grid", ""))
    grid_size = len(solution)
    row_ops = parse_manual_ops(options.get("row_ops", ""), grid_size)
    col_ops = parse_manual_ops(options.get("col_ops", ""), grid_size)
    number_max = max(max(row) for row in solution)
    result_min, result_max = result_limits(options, number_max)
    whole_number_division = bool_option(options, "whole_number_division", True)
    for row_index, row in enumerate(solution):
        if apply_operator_sequence(row[:-1], row_ops[row_index], result_min, result_max, whole_number_division) != row[-1]:
            raise ValueError("A Cross Equations row does not match its operators and result.")
    for col_index in range(grid_size):
        col_values = [solution[row][col_index] for row in range(grid_size)]
        if apply_operator_sequence(col_values[:-1], col_ops[col_index], result_min, result_max, whole_number_division) != col_values[-1]:
            raise ValueError("A Cross Equations column does not match its operators and result.")
    givens = parse_manual_cross_givens(options.get("givens", ""), solution)
    answer_map = {f"{x},{y}": str(solution[y // 2][x // 2]) for x, y in digit_coords(grid_size)}
    ops = [row_ops, col_ops]
    equation_list = equations(solution, ops)
    operators = sorted({operator for group in ops for row in group for operator in row if operator})
    settings = {
        "grid_size": grid_size,
        "number_range": f"1-{number_max}",
        "operators": operators,
        "whole_number_division": whole_number_division,
        "allow_multiple_operations": grid_size > DEFAULT_GRID_SIZE,
        "allow_multiple_equations": False,
        "result_min": result_min,
        "result_max": result_max,
        "difficulty_style": "manual",
        "rendered_size": grid_size * 2 - 1,
    }
    payload = {
        "kind": "cross_equations",
        "cells": build_cells(solution, ops, givens),
        "givens": givens,
        "equations": [{"number": item["number"], "direction": item["direction"], "label": item["label"], "cells": item["cells"]} for item in equation_list],
        "settings": settings,
    }
    return GeneratedPuzzle(
        title="Manual Cross Equations",
        prompt="Fill the shared number cells so every across and down equation is true.",
        print_payload=payload,
        play_payload=payload,
        solution_payload={
            "answers": answer_map,
            "givens": givens,
            "cells": build_cells(solution, ops, answer_map, include_solution=True),
            "equations": equation_list,
        },
        hints=[
            "Each row with numbers is an across equation.",
            "Each column with numbers is a down equation.",
            f"This manual puzzle starts with {len(givens)} givens.",
        ],
        metadata={
            "generator": "manual.cross_equations.canvas.v1",
            "manual": True,
            "givens": len(givens),
            "operators": operators,
            "generation_options": settings,
        },
    )


register_puzzle_type(
    PuzzleType(
        slug="cross_equations",
        collaboration=cell_collaboration(normalize_progress),
        label="Cross Equations",
        generator=generate,
        source_builder=build_source,
        answer_checker=check_answer,
        progress_normalizer=normalize_progress,
        progress_counter=count_progress,
        preview_builder=build_preview,
        description="A crossing arithmetic grid where rows and columns share number cells.",
        play_script="/plugins/cross_equations/static/cross-equations.js?v=8",
        **({"supports_offline": True, "offline_progress_fields": ("answers",), "offline_notes": "Progress works offline; checking requires a connection."} if "supports_offline" in PuzzleType.__dataclass_fields__ else {}),
        supports_print=True,
        supports_web_play=True,
        theme_mode="none",
        print_layout=PrintLayout(
            slug="cross_equations",
            sheet_class="print-layout-cross-equations",
            instructions="Fill the shared number cells so every across and down equation is true.",
            notes=("Number cells are boxed; operation/result cells stay unboxed for paper solving.",),
        ),
        manual_builder=build_manual_puzzle,
        manual_editor_fields=(
            GenerationField(
                name="solution_grid",
                label="Canvas number grid",
                field_type="textarea",
                default="",
                help_text="Managed by the visual editor.",
            ),
            GenerationField(
                name="row_ops",
                label="Canvas row operators",
                field_type="textarea",
                default="",
                help_text="Managed by the visual editor.",
            ),
            GenerationField(
                name="col_ops",
                label="Canvas column operators",
                field_type="textarea",
                default="",
                help_text="Managed by the visual editor.",
            ),
            GenerationField(
                name="givens",
                label="Canvas starter numbers",
                field_type="textarea",
                default="",
                help_text="Managed by the visual editor.",
            ),
            GenerationField(
                name="grid_size",
                label="Grid size",
                field_type="select",
                default="3",
                help_text="Number cells per side. Larger grids use longer row and column equations.",
                options=(
                    {"value": "3", "label": "3x3 equation grid"},
                    {"value": "4", "label": "4x4 equation grid"},
                    {"value": "5", "label": "5x5 equation grid"},
                    {"value": "custom", "label": "Custom"},
                ),
            ),
            GenerationField(
                name="custom_grid_size",
                label="Custom grid size",
                field_type="number",
                default="",
                help_text="Valid range is 3 to 5.",
                minimum=3,
                maximum=5,
            ),
            GenerationField(
                name="operators",
                label="Operators",
                field_type="checkboxes",
                default=(),
                help_text="Leave unchecked to use the difficulty default. Check specific operators to override it.",
                options=(
                    {"value": "+", "label": "Add"},
                    {"value": "-", "label": "Subtract"},
                    {"value": "x", "label": "Multiply"},
                    {"value": "/", "label": "Divide"},
                ),
            ),
            GenerationField(
                name="number_range",
                label="Number range",
                field_type="select",
                default="1-9",
                options=(
                    {"value": "1-9", "label": "1-9"},
                    {"value": "1-12", "label": "1-12"},
                    {"value": "1-20", "label": "1-20"},
                ),
            ),
            GenerationField(
                name="whole_number_division",
                label="Whole-number division",
                field_type="select",
                default="yes",
                options=(
                    {"value": "yes", "label": "Yes"},
                    {"value": "no", "label": "No"},
                ),
            ),
            GenerationField(
                name="allow_multiple_operations",
                label="Allow multiple operations per equation",
                field_type="select",
                default="no",
                options=(
                    {"value": "no", "label": "No"},
                    {"value": "yes", "label": "Yes"},
                ),
            ),
            GenerationField(
                name="allow_multiple_equations",
                label="Allow multiple equations per row/column",
                field_type="select",
                default="no",
                options=(
                    {"value": "no", "label": "No"},
                    {"value": "yes", "label": "Yes"},
                ),
            ),
            GenerationField(
                name="result_constraints",
                label="Result constraints",
                field_type="select",
                default="positive_only",
                options=(
                    {"value": "positive_only", "label": "Positive only"},
                    {"value": "allow_zero", "label": "Allow zero"},
                    {"value": "allow_negative", "label": "Allow negative"},
                ),
            ),
            GenerationField(
                name="difficulty_style",
                label="Difficulty style",
                field_type="select",
                default="balanced",
                options=(
                    {"value": "more_givens", "label": "More givens"},
                    {"value": "balanced", "label": "Balanced"},
                    {"value": "harder_operators", "label": "Harder operators"},
                ),
            ),
            GenerationField(
                name="given_count",
                label="Starter numbers",
                field_type="number",
                default="",
                help_text="Optional. Leave blank to let difficulty choose; valid range is 2 to 24.",
                minimum=2,
                maximum=24,
            ),
            GenerationField(
                name="seed",
                label="Seed",
                field_type="text",
                default="",
                help_text="Optional. Reuse to recreate the same puzzle.",
            ),
        ),
        generation_fields=(
            GenerationField(
                name="grid_size",
                label="Grid size",
                field_type="select",
                default="3",
                help_text="Number cells per side. Larger grids use longer row and column equations.",
                options=(
                    {"value": "3", "label": "3x3 equation grid"},
                    {"value": "4", "label": "4x4 equation grid"},
                    {"value": "5", "label": "5x5 equation grid"},
                    {"value": "custom", "label": "Custom"},
                ),
            ),
            GenerationField(
                name="custom_grid_size",
                label="Custom grid size",
                field_type="number",
                default="",
                help_text="Valid range is 3 to 5.",
                minimum=3,
                maximum=5,
            ),
            GenerationField(
                name="operators",
                label="Operators",
                field_type="checkboxes",
                default=(),
                help_text="Leave unchecked to use the difficulty default. Check specific operators to override it.",
                options=(
                    {"value": "+", "label": "Add"},
                    {"value": "-", "label": "Subtract"},
                    {"value": "x", "label": "Multiply"},
                    {"value": "/", "label": "Divide"},
                ),
            ),
            GenerationField(
                name="number_range",
                label="Number range",
                field_type="select",
                default="1-9",
                options=(
                    {"value": "1-9", "label": "1-9"},
                    {"value": "1-12", "label": "1-12"},
                    {"value": "1-20", "label": "1-20"},
                ),
            ),
            GenerationField(
                name="whole_number_division",
                label="Whole-number division",
                field_type="select",
                default="yes",
                options=(
                    {"value": "yes", "label": "Yes"},
                    {"value": "no", "label": "No"},
                ),
            ),
            GenerationField(
                name="allow_multiple_operations",
                label="Allow multiple operations per equation",
                field_type="select",
                default="no",
                options=(
                    {"value": "no", "label": "No"},
                    {"value": "yes", "label": "Yes"},
                ),
            ),
            GenerationField(
                name="allow_multiple_equations",
                label="Allow multiple equations per row/column",
                field_type="select",
                default="no",
                options=(
                    {"value": "no", "label": "No"},
                    {"value": "yes", "label": "Yes"},
                ),
            ),
            GenerationField(
                name="result_constraints",
                label="Result constraints",
                field_type="select",
                default="positive_only",
                options=(
                    {"value": "positive_only", "label": "Positive only"},
                    {"value": "allow_zero", "label": "Allow zero"},
                    {"value": "allow_negative", "label": "Allow negative"},
                ),
            ),
            GenerationField(
                name="difficulty_style",
                label="Difficulty style",
                field_type="select",
                default="balanced",
                options=(
                    {"value": "more_givens", "label": "More givens"},
                    {"value": "balanced", "label": "Balanced"},
                    {"value": "harder_operators", "label": "Harder operators"},
                ),
            ),
            GenerationField(
                name="given_count",
                label="Starter numbers",
                field_type="number",
                default="",
                help_text="Optional. Leave blank to let difficulty choose; valid range is 2 to 24.",
                minimum=2,
                maximum=24,
            ),
        ),
    )
)
