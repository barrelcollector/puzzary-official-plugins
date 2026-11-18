"""Seeded, server-authoritative Minesweeper puzzles."""
from copy import deepcopy
import json
import random
import uuid

from app.puzzles import GeneratedPuzzle, GenerationField, PuzzleType, register_puzzle_type


def whole_number(value, label):
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a whole number.")
    if type(value) is bool or (isinstance(value, float) and value != result):
        raise ValueError(f"{label} must be a whole number.")
    return result


def yes_no(value, label):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("yes", "true", "1", "on"):
        return True
    if normalized in ("no", "false", "0", "off"):
        return False
    raise ValueError(f"{label} must be yes or no.")


def key(x, y):
    return f"{x},{y}"


def coordinates(value):
    try:
        x, y = (int(part) for part in value.split(","))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Cell is outside the board.")
    return x, y


def board(solution):
    width = int(solution.get("width", 0))
    height = int(solution.get("height", 0))
    raw_mines = solution.get("mines", [])
    mines = set(raw_mines) if isinstance(raw_mines, list) else set()
    valid = {key(x, y) for y in range(height) for x in range(width)}
    if (width < 1 or height < 1 or not mines or not mines < valid
            or len(mines) != len(raw_mines) or solution.get("mine_count") != len(mines)):
        raise ValueError("Invalid Minesweeper solution.")
    return width, height, mines, valid


def neighbors(cell, width, height):
    x, y = coordinates(cell)
    return [key(nx, ny) for ny in range(max(0, y - 1), min(height, y + 2))
            for nx in range(max(0, x - 1), min(width, x + 2)) if (nx, ny) != (x, y)]


def counts_for(width, height, mines):
    return {key(x, y): str(sum(neighbor in mines for neighbor in neighbors(key(x, y), width, height)))
            for y in range(height) for x in range(width) if key(x, y) not in mines}


def clean_state(state, solution):
    width, height, mines, valid = board(solution)
    counts = counts_for(width, height, mines)
    raw = state.get("answers", {}) if isinstance(state, dict) else {}
    answers = {}
    if isinstance(raw, dict):
        for cell, value in raw.items():
            value = str(value)
            if cell in valid and value == "F":
                answers[cell] = value
            elif cell in counts and value == counts[cell]:
                answers[cell] = value
    exploded = state.get("exploded", "") if isinstance(state, dict) else ""
    raw_status = state.get("status", "playing") if isinstance(state, dict) else "playing"
    if exploded in mines and raw_status == "lost":
        answers.update({cell: "M" for cell in mines})
        status = "lost"
    elif raw_status == "revealed":
        answers.update(counts)
        answers.update({cell: "M" for cell in mines})
        exploded = ""
        status = "revealed"
    elif all(cell in answers for cell in counts):
        status, exploded = "won", ""
    else:
        status, exploded = "playing", ""
    return {"answers": answers, "status": status, "exploded": exploded}


def reveal_from(answers, start, width, height, mines, counts, open_connected=True):
    if start in mines:
        return False
    pending = [start]
    seen = set()
    while pending:
        cell = pending.pop()
        if cell in seen or cell in mines or answers.get(cell) == "F":
            continue
        seen.add(cell)
        answers[cell] = counts[cell]
        if open_connected and counts[cell] == "0":
            pending.extend(neighbors(cell, width, height))
    return True


def collaboration(state, action, solution):
    result = clean_state(deepcopy(state), solution)
    width, height, mines, valid = board(solution)
    counts = counts_for(width, height, mines)
    settings = solution.get("settings", {}) if isinstance(solution.get("settings", {}), dict) else {}
    open_connected = settings.get("open_connected_safe_spaces", True) is not False
    kind = action.get("kind")
    if kind == "reset":
        return {"answers": {}, "status": "playing", "exploded": ""}
    if kind == "patch":
        if action.get("changes"):
            raise ValueError("Minesweeper cells must be changed with reveal or flag actions.")
        return result
    if result["status"] != "playing":
        return result
    answers = result["answers"]
    target = action.get("target", "")
    if kind in ("reveal_cell", "flag"):
        if target not in valid:
            raise ValueError("Cell is outside the board.")
        if kind == "flag":
            if target in answers and answers[target] != "F":
                return result
            if answers.get(target) == "F":
                answers.pop(target)
            elif sum(value == "F" for value in answers.values()) < len(mines):
                answers[target] = "F"
        elif answers.get(target) != "F":
            if target in mines:
                result["status"], result["exploded"] = "lost", target
                answers.update({cell: "M" for cell in mines})
            elif target in answers:
                adjacent = neighbors(target, width, height)
                if sum(answers.get(cell) == "F" for cell in adjacent) == int(counts[target]):
                    for cell in adjacent:
                        if cell not in answers and not reveal_from(
                                answers, cell, width, height, mines, counts, open_connected):
                            result["status"], result["exploded"] = "lost", cell
                            answers.update({mine: "M" for mine in mines})
                            break
            else:
                reveal_from(answers, target, width, height, mines, counts, open_connected)
    elif kind == "hint":
        target = next((cell for cell in sorted(counts) if cell not in answers), "")
        if target:
            reveal_from(answers, target, width, height, mines, counts, open_connected)
            result["hints_used"] = int(result.get("hints_used", 0)) + 1
    elif kind == "reveal":
        result.update({"answers": {**counts, **{cell: "M" for cell in mines}}, "status": "revealed", "exploded": ""})
        return result
    else:
        raise ValueError("Unsupported Minesweeper action.")
    if result["status"] == "playing" and all(cell in answers for cell in counts):
        result["status"] = "won"
    return result


def normalize_progress(_payload, _solution):
    # Browser-supplied progress cannot be trusted because mine locations are private.
    return {"answers": {}, "status": "playing", "exploded": ""}


def count_progress(progress, solution):
    state = clean_state(progress if isinstance(progress, dict) else {}, solution)
    _width, _height, mines, valid = board(solution)
    total = len(valid) - len(mines)
    found = sum(value.isdigit() for value in state["answers"].values())
    if state["status"] == "won":
        return total, total
    return min(found, max(0, total - 1)), total


def check_answer(answer, solution):
    try:
        value = json.loads(answer) if isinstance(answer, str) else answer
    except (TypeError, ValueError):
        value = {}
    state = clean_state(value if isinstance(value, dict) else {}, solution)
    found, total = count_progress(state, solution)
    return state["status"] == "won", total, found


def generate(_theme, _difficulty, source_data=None, seed=None, generation_options=None):
    options = generation_options or {}
    width = whole_number(options.get("width", 9), "Width")
    height = whole_number(options.get("height", 9), "Height")
    mine_count = whole_number(options.get("mine_count", 10), "Mine count")
    open_connected = yes_no(options.get("open_connected_safe_spaces", "yes"), "Open connected safe spaces")
    if not 5 <= width <= 30:
        raise ValueError("Width must be from 5 to 30.")
    if not 5 <= height <= 24:
        raise ValueError("Height must be from 5 to 24.")
    if not 1 <= mine_count < width * height:
        raise ValueError("Mine count must be at least 1 and less than the number of cells.")
    seed = str(seed or uuid.uuid4().hex)
    cells = [key(x, y) for y in range(height) for x in range(width)]
    mines = sorted(random.Random(seed).sample(cells, mine_count))
    public = {"kind": "minesweeper", "width": width, "height": height, "mine_count": mine_count,
              "settings": {"open_connected_safe_spaces": open_connected}}
    solution = {**public, "mines": mines, "counts": counts_for(width, height, set(mines))}
    return GeneratedPuzzle(
        title=f"{width}x{height} Minesweeper",
        prompt="Reveal every safe cell without opening a mine. Numbers show how many mines touch that cell; flag suspected mines.",
        print_payload=public,
        play_payload=public,
        solution_payload=solution,
        hints=["Start with open areas and use the numbers around revealed cells.",
               "When a number already touches that many flags, its other hidden neighbors are safe.",
               "When a number has exactly that many hidden neighbors left, those neighbors must be mines."],
        metadata={"generator": "local.minesweeper.v1", "seed": seed,
                  "generation_options": {"width": width, "height": height, "mine_count": mine_count,
                                         "open_connected_safe_spaces": open_connected}},
    )


register_puzzle_type(PuzzleType(
    slug="minesweeper", label="Minesweeper",
    description="Reveal safe cells, read adjacent-mine counts, and flag every mine.",
    generator=generate, source_builder=lambda *_: {}, answer_checker=check_answer,
    progress_normalizer=normalize_progress, progress_counter=count_progress,
    collaboration=collaboration, theme_mode="none", supports_print=False, digital_only=True,
    generation_fields=(
        GenerationField("width", "Width", "number", 9, minimum=5, maximum=30),
        GenerationField("height", "Height", "number", 9, minimum=5, maximum=24),
        GenerationField("mine_count", "Mines", "number", 10, minimum=1, maximum=719),
        GenerationField("open_connected_safe_spaces", "Open connected safe spaces", "select", "yes",
                        help_text="When a revealed space has no adjacent mines, open its connected clear area and numbered boundary.",
                        options=({"value": "yes", "label": "On"}, {"value": "no", "label": "Off"})),
    ),
    play_script="/plugins/minesweeper/static/minesweeper.js?v=1",
))
