from __future__ import annotations

import random
import re
from typing import Any

from app.clues import definition_clue_tiers, word_clue_tiers
from app.content import words_for_theme
from app.puzzles import GeneratedPuzzle, GenerationField, PrintLayout, PuzzleType, normalize_answer, register_puzzle_type
from app.group_actions import cell_collaboration


FALLBACK_CLUES = {
    "MERIDIAN": ["An imaginary north-south line used to measure longitude."],
    "PUZZLE": ["A problem designed to test ingenuity or knowledge."],
    "ZEBRA": ["An African animal known for black-and-white stripes."],
    "PRINT": ["To reproduce words or images on paper."],
    "CLUE": ["Information that helps someone find an answer."],
    "PAPER": ["A thin material used for writing, drawing, or printing."],
    "HINT": ["An indirect suggestion intended to help."],
    "SOLVE": ["To find the answer to a problem."],
    "PORCH": ["A covered entrance attached to a building."],
    "PANTRY": ["A cupboard or room where food is stored."],
    "LAUNDRY": ["Clothes or linens waiting to be washed or newly cleaned."],
    "GARAGE": ["A building or room used to store a vehicle."],
    "KITCHEN": ["A room where food is prepared and cooked."],
    "GARDEN": ["Ground used for growing flowers, fruit, or vegetables."],
    "SHELF": ["A flat horizontal surface used for storage or display."],
    "CLOUD": ["A visible mass of condensed water droplets in the sky."],
    "RAIN": ["Water falling from clouds in drops."],
    "SUNNY": ["Bright with direct light from the sun."],
    "STORM": ["A violent disturbance of the atmosphere."],
    "BREEZE": ["A light and gentle wind."],
    "HUMID": ["Containing a high amount of moisture in the air."],
    "RADAR": ["A system that locates objects using reflected radio waves."],
    "ORBIT": ["The curved path of an object around a planet or star."],
    "COMET": ["An icy celestial body that may develop a glowing tail."],
    "LUNAR": ["Relating to the moon."],
    "ROCKET": ["A vehicle propelled by rapidly expelled exhaust."],
    "PLANET": ["A large body that travels around a star."],
    "STAR": ["A luminous ball of gas held together by gravity."],
    "ECLIPSE": ["An event in which one celestial body obscures another."],
    "SERVER": ["A computer or program that provides services to clients."],
    "DOCKER": ["A platform for packaging applications in containers."],
    "PYTHON": ["A programming language named after a comedy group."],
    "ROUTER": ["A device that forwards data between networks."],
    "SCRIPT": ["A sequence of instructions executed by a computer."],
    "SENSOR": ["A device that detects or measures a physical property."],
}


def word_allowed(word: Any, excluded_tag_ids: set[int] | None) -> bool:
    if getattr(word, "archived_at", None) is not None or getattr(word, "banned_at", None) is not None:
        return False
    if excluded_tag_ids and any(getattr(tag, "id", None) in excluded_tag_ids for tag in getattr(word, "tags", [])):
        return False
    return True


def definition_allowed(definition: Any, excluded_tag_ids: set[int] | None) -> bool:
    if getattr(definition, "archived_at", None) is not None:
        return False
    text = str(getattr(definition, "definition", "")).strip()
    if not text:
        return False
    if excluded_tag_ids and any(getattr(tag, "id", None) in excluded_tag_ids for tag in getattr(definition, "tags", [])):
        return False
    return True


def progressive_clues(clues: list[str], word: str) -> tuple[str, list[str]]:
    if not clues:
        raise ValueError(f"Crossword answer '{word}' needs at least one clue or definition.")
    primary = clues[0]
    match = re.fullmatch(r"(.+) term starting with ([A-Z0-9]) \((\d+) letters\)\.", primary)
    if not match:
        return primary, clues
    theme, first_letter, _length = match.groups()
    stepped = [f"{theme} entry."]
    for clue in clues[1:]:
        if clue not in stepped:
            stepped.append(clue)
    stepped.append(f"Starts with {first_letter}.")
    return stepped[0], stepped


def clue_for_word(word: Any, excluded_tag_ids: set[int] | None) -> tuple[str, list[str], int | None] | None:
    definitions = sorted(getattr(word, "definitions", []), key=lambda item: item.position)
    definitions = [definition for definition in definitions if definition_allowed(definition, excluded_tag_ids)]
    clues = word_clue_tiers(word, definitions)
    if not clues:
        return None
    primary, clue_steps = progressive_clues(clues, str(getattr(word, "display_text", "") or getattr(word, "word", "")))
    return primary, clue_steps, getattr(definitions[0], "id", None) if definitions else None


def clues_for_definition(definition: Any) -> list[str]:
    return definition_clue_tiers(definition)


def build_source(word_entries: Any, difficulty: str, excluded_tag_ids: set[int] | None = None) -> list[dict] | None:
    entries_by_word: dict[int | str, dict] = {}
    for entry in word_entries or []:
        word = entry.get("word") if isinstance(entry, dict) else None
        definition = entry.get("definition") if isinstance(entry, dict) else None
        if word is None or not word_allowed(word, excluded_tag_ids):
            continue
        if definition is not None and not definition_allowed(definition, excluded_tag_ids):
            continue
        key = getattr(word, "id", None) or str(getattr(word, "word", "")).upper()
        built = entries_by_word.setdefault(key, {"word": word, "definitions": []})
        if definition is not None and definition not in built["definitions"]:
            built["definitions"].append(definition)

    entries = []
    for built in entries_by_word.values():
        word = built["word"]
        selected = built["definitions"] or [
            definition for definition in sorted(getattr(word, "definitions", []), key=lambda item: item.position)
            if definition_allowed(definition, excluded_tag_ids)
        ]
        clues = word_clue_tiers(word, selected)
        if not clues:
            continue
        clue_text, clues = progressive_clues(clues, str(getattr(word, "display_text", "") or getattr(word, "word", "")))
        entries.append({
            "word": word.word,
            "clue": clue_text,
            "clues": clues,
            "definition_id": getattr(selected[0], "id", None) if selected else None,
        })
    return entries or None


def gimme_entry_count_for_difficulty(entry_count: int, difficulty: str) -> int:
    count = {"easy": 1, "medium": 1, "hard": 0}.get(difficulty, 0)
    return min(count, max(0, entry_count - 1))


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


def grid_size_option(options: dict[str, Any], difficulty: str) -> int:
    default = {"easy": 11, "medium": 13, "hard": 15}.get(difficulty, 11)
    preset = str(options.get("grid_size", "")).strip().lower()
    legacy = {"mini": 8, "regular": 12, "large": 14}
    if preset in legacy:
        return legacy[preset]
    if preset == "custom":
        return integer_option(options, "custom_grid_size", default, 5, 25)
    if preset:
        try:
            return max(5, min(25, int(preset)))
        except ValueError:
            pass
    return default


def clue_depth_steps(clue_steps: list[str], depth: str) -> list[str]:
    if not clue_steps:
        return clue_steps
    if depth == "none":
        return clue_steps[:1]
    if depth == "one_hint":
        return clue_steps[:2]
    return clue_steps


def styled_clues(raw_clues: list[str], word: str, clue_style: str, depth: str) -> tuple[str, list[str]]:
    primary, clue_steps = progressive_clues(raw_clues, word)
    if clue_style == "definition":
        definition_clues = [clue for clue in clue_steps if str(clue).lower().startswith("definition:")]
        if definition_clues:
            clue_steps = definition_clues + [clue for clue in clue_steps if clue not in definition_clues]
            primary = clue_steps[0]
    elif clue_style == "clue_tag":
        tag_clues = [clue for clue in clue_steps if not str(clue).lower().startswith("definition:")]
        if tag_clues:
            clue_steps = tag_clues + [clue for clue in clue_steps if clue not in tag_clues]
            primary = clue_steps[0]
    elif clue_style == "easier":
        easier = f"{word[0]} starts a {len(word)}-letter answer."
        clue_steps = [primary, easier, *[clue for clue in clue_steps[1:] if clue != easier]]
    elif clue_style == "more_cryptic":
        primary = f"{len(word)} letters; crossings are your best clue."
        clue_steps = [primary, *clue_steps]
    clue_steps = clue_depth_steps(clue_steps, depth)
    return clue_steps[0], clue_steps


def gimme_cells_from_entries(entries: list[dict]) -> dict[str, str]:
    cells = {}
    for entry in entries:
        if not entry.get("gimme"):
            continue
        dx = 1 if entry.get("direction") == "across" else 0
        dy = 1 if entry.get("direction") == "down" else 0
        answer = str(entry.get("answer", "")).upper()
        for index, letter in enumerate(answer):
            x = int(entry.get("x", 0)) + dx * index
            y = int(entry.get("y", 0)) + dy * index
            cells[f"{x},{y}"] = letter
    return cells


def gimme_cells_from_letters(entries: list[dict], count: int, rng: random.Random) -> dict[str, str]:
    available_cells = []
    seen = set()
    for entry in entries:
        dx = 1 if entry.get("direction") == "across" else 0
        dy = 1 if entry.get("direction") == "down" else 0
        answer = str(entry.get("answer", "")).upper()
        for index, letter in enumerate(answer):
            x = int(entry.get("x", 0)) + dx * index
            y = int(entry.get("y", 0)) + dy * index
            key = f"{x},{y}"
            if key in seen:
                continue
            seen.add(key)
            available_cells.append((key, letter))
    rng.shuffle(available_cells)
    return dict(available_cells[:count])


def check_answer(answer: str, solution_payload: dict) -> tuple[bool, int, int]:
    expected = {str(entry["answer"]).upper() for entry in solution_payload.get("entries", [])}
    supplied = normalize_answer(answer) | {
        str(entry.get("answer", "")).upper()
        for entry in solution_payload.get("entries", [])
        if entry.get("gimme")
    }
    matched = len(expected & supplied)
    return expected <= supplied, len(expected), matched


def normalize_progress(payload: Any, solution_payload: dict) -> dict:
    answers = getattr(payload, "answers", {}) if payload is not None else {}
    if not isinstance(answers, dict):
        answers = {}
    gimme_cells = solution_payload.get("gimmes", {}).get("cells", {})
    if not isinstance(gimme_cells, dict):
        gimme_cells = {}
    normalized = {
        str(key): str(value).strip().upper()[:1]
        for key, value in answers.items()
        if str(value).strip()
    }
    normalized.update({str(key): str(value).strip().upper()[:1] for key, value in gimme_cells.items() if str(value).strip()})
    return {
        "answers": normalized
    }


def count_progress(progress_payload: dict, solution_payload: dict) -> tuple[int, int]:
    answers = progress_payload.get("answers", {})
    if not isinstance(answers, dict):
        answers = {}
    gimme_cells = solution_payload.get("gimmes", {}).get("cells", {})
    if not isinstance(gimme_cells, dict):
        gimme_cells = {}
    answers = {**answers, **gimme_cells}
    expected_count = sum(1 for row in solution_payload.get("grid", []) for cell in row if cell)
    correct = 0
    for key, value in answers.items():
        try:
            x_text, y_text = str(key).split(",", 1)
            x = int(x_text)
            y = int(y_text)
        except ValueError:
            continue
        grid = solution_payload.get("grid", [])
        if 0 <= y < len(grid) and 0 <= x < len(grid[y]) and str(grid[y][x]).upper() == str(value).upper():
            correct += 1
    filled = sum(1 for key, value in answers.items() if value and key not in gimme_cells)
    filled += len(gimme_cells)
    complete = expected_count > 0 and correct == expected_count
    return (expected_count if complete else min(filled, max(0, expected_count - 1))), expected_count


def build_preview(print_payload: dict, play_payload: dict, metadata: dict) -> dict:
    payload = print_payload if isinstance(print_payload, dict) else {}
    grid = payload.get("grid", [])
    clues = payload.get("clues", [])
    return {
        "kind": "crossword",
        "grid": [
            [
                {"open": bool(cell.get("open")), "number": cell.get("number")}
                if isinstance(cell, dict) else {"open": False, "number": ""}
                for cell in row[:12]
            ]
            for row in grid[:12]
            if isinstance(row, list)
        ],
        "meta": f"{len(clues)} clues",
    }


def parse_manual_entries(value: Any) -> list[dict[str, Any]]:
    entries = []
    seen = set()
    for line in str(value or "").splitlines():
        parts = [part.strip() for part in line.split("|")]
        word = "".join(ch for ch in (parts[0] if parts else "").upper() if ch.isalnum())
        if not word or word in seen:
            continue
        if len(word) < 3:
            raise ValueError(f"Crossword answer '{word}' must be at least 3 letters.")
        seen.add(word)
        clues = [part for part in parts[1:] if part]
        if not clues:
            raise ValueError(f"Crossword answer '{word}' needs at least one clue or definition.")
        entries.append({"word": word, "clue": clues[0], "clues": clues, "definition_id": None})
    if len(entries) < 3:
        raise ValueError("Manual crossword builder needs at least 3 entries.")
    return entries


def build_manual_puzzle(options: dict[str, Any]) -> GeneratedPuzzle:
    theme = str(options.get("_theme") or "manual").strip() or "manual"
    difficulty = str(options.get("_difficulty") or "medium").strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"
    entries = parse_manual_entries(options.get("entries", ""))
    generation_options = {
        "grid_size": options.get("grid_size") or "difficulty_default",
        "custom_grid_size": options.get("custom_grid_size") or "",
        "answer_count_min": str(len(entries)),
        "answer_count": str(len(entries)),
        "clue_style": "mixed",
        "more_clues_depth": options.get("more_clues_depth") or "multi_step",
        "check_mode": options.get("check_mode") or "whole_puzzle",
        "auto_highlight_correct": options.get("auto_highlight_correct") or "no",
        "reveal_mode": options.get("reveal_mode") or "word",
        "gimme_mode": options.get("gimme_mode") or "letters",
        "gimme_count": options.get("gimme_count") or "0",
    }
    generated = generate(theme, difficulty, entries, str(options.get("seed") or "") or None, generation_options)
    return GeneratedPuzzle(
        title="Manual Crossword",
        prompt=generated.prompt,
        print_payload=generated.print_payload,
        play_payload=generated.play_payload,
        solution_payload=generated.solution_payload,
        hints=generated.hints,
        metadata={
            **generated.metadata,
            "generator": "manual.crossword.v1",
            "manual": True,
            "manual_entry_count": len(entries),
        },
    )


def generate(
    theme: str,
    difficulty: str,
    source_data: list[dict] | None = None,
    seed: str | None = None,
    _generation_options: dict[str, Any] | None = None,
) -> GeneratedPuzzle:
    generation_options = _generation_options or {}
    raw_entries = source_data if source_data is not None else [
        {"word": word, "clues": FALLBACK_CLUES.get(word, [])}
        for word in words_for_theme(theme, difficulty)
    ]
    default_answer_count = {"easy": 5, "medium": 7, "hard": 9}.get(difficulty, 5)
    has_answer_max = "answer_count" in generation_options
    answer_max = integer_option(generation_options, "answer_count", default_answer_count, 3, 30)
    if "answer_count_min" in generation_options:
        answer_min = integer_option(generation_options, "answer_count_min", min(default_answer_count, answer_max), 3, 30)
    else:
        answer_min = min(default_answer_count, answer_max)
    if not has_answer_max and answer_min > answer_max:
        answer_max = answer_min
    if has_answer_max and answer_min > answer_max:
        raise ValueError("Crossword maximum answers must be at least the minimum answers.")
    answer_min = min(answer_min, answer_max)
    size = grid_size_option(generation_options, difficulty)
    clue_style = str(generation_options.get("clue_style", "mixed")).strip().lower()
    if clue_style not in {"mixed", "definition", "clue_tag", "easier", "more_cryptic"}:
        clue_style = "mixed"
    more_clues_depth = str(generation_options.get("more_clues_depth", "multi_step")).strip().lower()
    if more_clues_depth not in {"none", "one_hint", "multi_step"}:
        more_clues_depth = "multi_step"
    check_mode = str(generation_options.get("check_mode", "whole_puzzle")).strip().lower()
    if check_mode not in {"whole_puzzle", "per_word"}:
        check_mode = "whole_puzzle"
    reveal_mode = str(generation_options.get("reveal_mode", "word")).strip().lower()
    if reveal_mode not in {"word", "letter", "whole_puzzle"}:
        reveal_mode = "word"
    auto_highlight_correct = bool_option(generation_options, "auto_highlight_correct", False)
    gimme_mode = str(generation_options.get("gimme_mode", "entries")).strip().lower()
    if gimme_mode not in {"entries", "letters"}:
        gimme_mode = "entries"
    generation_seed = seed or f"crossword:{theme}:{difficulty}:{','.join(str(entry.get('word', '')) for entry in raw_entries)}"
    rng = random.Random(generation_seed)
    candidate_entries = []
    seen = set()
    for entry in raw_entries:
        word = "".join(ch for ch in str(entry.get("word", "")).upper() if ch.isalnum())
        if len(word) < 3 or len(word) > size or word in seen:
            continue
        seen.add(word)
        raw_clues = [str(clue).strip() for clue in entry.get("clues", [entry.get("clue")]) if str(clue or "").strip()]
        if not raw_clues:
            continue
        primary_clue, clue_steps = styled_clues(
            raw_clues,
            word,
            clue_style,
            more_clues_depth,
        )
        candidate_entries.append(
            {
                "word": word,
                "clue": primary_clue,
                "clues": clue_steps,
                "definition_id": entry.get("definition_id"),
            }
        )

    if len(candidate_entries) < answer_min:
        raise ValueError(f"Crossword generation needs at least {answer_min} usable words of 3+ characters.")
    available_max = min(answer_max, len(candidate_entries))
    grid: list[list[str | None]] = [[None for _ in range(size)] for _ in range(size)]
    placements: list[dict] = []
    entries: list[dict] = []

    def can_place(word: str, x: int, y: int, direction: str) -> bool:
        dx, dy = (1, 0) if direction == "across" else (0, 1)
        end_x = x + dx * (len(word) - 1)
        end_y = y + dy * (len(word) - 1)
        if x < 0 or y < 0 or end_x >= size or end_y >= size:
            return False
        before_x, before_y = x - dx, y - dy
        after_x, after_y = end_x + dx, end_y + dy
        if 0 <= before_x < size and 0 <= before_y < size and grid[before_y][before_x]:
            return False
        if 0 <= after_x < size and 0 <= after_y < size and grid[after_y][after_x]:
            return False

        touches = 0
        for index, letter in enumerate(word):
            cx, cy = x + dx * index, y + dy * index
            existing = grid[cy][cx]
            if existing is not None and existing != letter:
                return False
            if existing == letter:
                touches += 1
                continue
            side_checks = [(0, -1), (0, 1)] if direction == "across" else [(-1, 0), (1, 0)]
            for sx, sy in side_checks:
                nx, ny = cx + sx, cy + sy
                if 0 <= nx < size and 0 <= ny < size and grid[ny][nx]:
                    return False
        return not placements or touches > 0

    def place(
        word: str,
        x: int,
        y: int,
        direction: str,
        clue: str,
        clues: list[str],
        definition_id: int | None,
    ) -> None:
        dx, dy = (1, 0) if direction == "across" else (0, 1)
        for index, letter in enumerate(word):
            grid[y + dy * index][x + dx * index] = letter
        placements.append(
            {
                "word": word,
                "x": x,
                "y": y,
                "direction": direction,
                "clue": clue,
                "clues": clues,
                "definition_id": definition_id,
            }
        )

    best_placement_count = 0
    for _attempt in range(80):
        requested_count = rng.randint(answer_min, available_max)
        shuffled_entries = candidate_entries[:]
        rng.shuffle(shuffled_entries)
        entries = shuffled_entries[:requested_count]
        if len(entries) < 3:
            continue

        grid = [[None for _ in range(size)] for _ in range(size)]
        placements = []
        first = max(entries, key=lambda item: len(item["word"]))
        place(
            first["word"],
            max(0, (size - len(first["word"])) // 2),
            size // 2,
            "across",
            first["clue"],
            first["clues"],
            first.get("definition_id"),
        )

        for entry in sorted([item for item in entries if item is not first], key=lambda item: len(item["word"]), reverse=True):
            word = entry["word"]
            candidates = []
            for y, row in enumerate(grid):
                for x, letter in enumerate(row):
                    if not letter or letter not in word:
                        continue
                    for index, word_letter in enumerate(word):
                        if word_letter != letter:
                            continue
                        candidates.append((x, y - index, "down"))
                        candidates.append((x - index, y, "across"))
            rng.shuffle(candidates)
            for x, y, direction in candidates:
                if can_place(word, x, y, direction):
                    place(word, x, y, direction, entry["clue"], entry["clues"], entry.get("definition_id"))
                    break

        best_placement_count = max(best_placement_count, len(placements))
        if len(placements) >= answer_min:
            break
    else:
        raise ValueError(
            f"Unable to place the minimum {answer_min} crossword words on the selected grid. "
            f"Best attempt placed {best_placement_count}; try a larger grid, fewer minimum answers, or a different word bank."
        )

    used_cells = [(x, y) for y, row in enumerate(grid) for x, value in enumerate(row) if value]
    min_x = max(0, min(x for x, _ in used_cells) - 1)
    max_x = min(size - 1, max(x for x, _ in used_cells) + 1)
    min_y = max(0, min(y for _, y in used_cells) - 1)
    max_y = min(size - 1, max(y for _, y in used_cells) + 1)
    cropped = [[grid[y][x] for x in range(min_x, max_x + 1)] for y in range(min_y, max_y + 1)]

    starts: dict[tuple[int, int], int] = {}
    next_number = 1
    for placement in sorted(placements, key=lambda item: (item["y"], item["x"])):
        key = (placement["x"] - min_x, placement["y"] - min_y)
        if key not in starts:
            starts[key] = next_number
            next_number += 1
        placement["number"] = starts[key]
        placement["x"] -= min_x
        placement["y"] -= min_y

    clue_entries = [
        {
            "number": item["number"],
            "direction": item["direction"],
            "clue": item["clue"],
            "clues": item.get("clues") or [item["clue"]],
            "answer": item["word"],
            "length": len(item["word"]),
            "x": item["x"],
            "y": item["y"],
            "definition_id": item.get("definition_id"),
        }
        for item in sorted(placements, key=lambda item: (item["direction"], item["number"]))
    ]
    default_gimme_count = gimme_entry_count_for_difficulty(len(clue_entries), difficulty)
    gimme_count_max = max(0, len(clue_entries) - 1) if gimme_mode == "entries" else sum(len(entry["answer"]) for entry in clue_entries)
    gimme_count = integer_option(generation_options, "gimme_count", default_gimme_count, 0, gimme_count_max)
    sorted_clues = sorted(clue_entries, key=lambda item: (item["number"], item["direction"]))
    gimme_ids = {
        f"{entry['number']}:{entry['direction']}"
        for entry in sorted_clues[:gimme_count]
    } if gimme_mode == "entries" else set()
    for entry in clue_entries:
        entry["gimme"] = f"{entry['number']}:{entry['direction']}" in gimme_ids
    gimme_cells = gimme_cells_from_entries(clue_entries) if gimme_mode == "entries" else gimme_cells_from_letters(clue_entries, gimme_count, rng)
    play_cells = []
    print_cells = []
    for y, row in enumerate(cropped):
        play_row = []
        print_row = []
        for x, value in enumerate(row):
            number = starts.get((x, y), "")
            play_row.append({"letter": value or "", "number": number})
            print_row.append({"open": bool(value), "number": number})
        play_cells.append(play_row)
        print_cells.append(print_row)

    solution_grid = [[cell["letter"] for cell in row] for row in play_cells]
    prompt = "Fill the crossword from the clues."
    settings = {
        "grid_size": size,
        "answer_count_min": answer_min,
        "answer_count": len(clue_entries),
        "answer_count_max": answer_max,
        "clue_style": clue_style,
        "more_clues_depth": more_clues_depth,
        "check_mode": check_mode,
        "auto_highlight_correct": auto_highlight_correct,
        "reveal_mode": reveal_mode,
        "gimme_mode": gimme_mode,
    }
    play_payload = {
        "kind": "crossword",
        "grid": play_cells,
        "clues": clue_entries,
        "settings": settings,
    }
    print_payload = {
        "kind": "crossword",
        "grid": print_cells,
        "clues": [{key: value for key, value in clue.items() if key != "answer"} for clue in clue_entries],
        "settings": settings,
    }
    solution_payload = {
        "entries": clue_entries,
        "grid": solution_grid,
        "gimmes": {
            "mode": gimme_mode,
            "entries": [
                {
                    "number": entry["number"],
                    "direction": entry["direction"],
                    "answer": entry["answer"],
                }
                for entry in clue_entries
                if entry.get("gimme")
            ],
            "cells": gimme_cells,
        },
        "settings": settings,
    }
    return GeneratedPuzzle(
        title=f"{theme.replace('_', ' ').title()} Crossword",
        prompt=prompt,
        print_payload=print_payload,
        play_payload=play_payload,
        solution_payload=solution_payload,
        hints=[
            f"There are {len(clue_entries)} crossword answers.",
            "Use intersecting letters to narrow down uncertain answers.",
            f"The longest answer has {max(len(item['answer']) for item in clue_entries)} letters.",
        ],
        metadata={
            "generator": "local.crossword.v1",
            "grid_size": len(play_cells),
            "seed": generation_seed,
            "gimmes": {"mode": gimme_mode, "count": gimme_count},
            "generation_options": settings | {"gimme_count": gimme_count},
        },
    )


register_puzzle_type(
    PuzzleType(
        slug="crossword",
        collaboration=cell_collaboration(normalize_progress),
        label="Crossword",
        generator=generate,
        source_builder=build_source,
        answer_checker=check_answer,
        progress_normalizer=normalize_progress,
        progress_counter=count_progress,
        preview_builder=build_preview,
        description="A clue-driven crossword built from dictionary definitions.",
        play_script="/plugins/crossword/static/crossword.js?v=16",
        **({"supports_offline": True, "offline_progress_fields": ("answers",), "offline_notes": "Grid entries work offline; answer checks and reveals require a connection."} if "supports_offline" in PuzzleType.__dataclass_fields__ else {}),
        supports_print=True,
        supports_web_play=True,
        source_requirements=("word_bank", "definitions"),
        print_layout=PrintLayout(
            slug="crossword",
            sheet_class="print-layout-crossword",
            instructions="Fill the crossword from the clues.",
            notes=("Clues are grouped by direction and gimme letters are shaded.",),
        ),
        supports_gimmes=True,
        gimme_modes=("entries", "letters"),
        manual_builder=build_manual_puzzle,
        manual_editor_fields=(
            GenerationField(
                name="entries",
                label="Answers and clues",
                field_type="textarea",
                required=True,
                help_text="One answer per line: ANSWER | primary clue | optional extra clue | optional extra clue.",
                default="TIP | A small piece of advice.\nPINT | A liquid measure equal to two cups.\nPOINT | A sharp end, exact location, or main idea.\nPISTON | A moving engine part inside a cylinder.",
            ),
            GenerationField(
                name="grid_size",
                label="Grid size",
                field_type="select",
                default="difficulty_default",
                options=(
                    {"value": "difficulty_default", "label": "Use difficulty default"},
                    {"value": "8", "label": "8x8"},
                    {"value": "10", "label": "10x10"},
                    {"value": "12", "label": "12x12"},
                    {"value": "14", "label": "14x14"},
                    {"value": "custom", "label": "Custom"},
                ),
            ),
            GenerationField(
                name="custom_grid_size",
                label="Custom grid size",
                field_type="number",
                default="",
                help_text="Only used when Grid size is Custom.",
                minimum=5,
                maximum=25,
            ),
            GenerationField(
                name="more_clues_depth",
                label="More clues depth",
                field_type="select",
                default="multi_step",
                options=(
                    {"value": "none", "label": "None"},
                    {"value": "one_hint", "label": "One hint"},
                    {"value": "multi_step", "label": "Multi-step"},
                ),
            ),
            GenerationField(
                name="check_mode",
                label="Check mode",
                field_type="select",
                default="whole_puzzle",
                options=(
                    {"value": "whole_puzzle", "label": "Whole puzzle only"},
                    {"value": "per_word", "label": "Per-word check"},
                ),
            ),
            GenerationField(
                name="auto_highlight_correct",
                label="Auto-highlight correct words",
                field_type="select",
                default="no",
                options=(
                    {"value": "no", "label": "No"},
                    {"value": "yes", "label": "Yes"},
                ),
            ),
            GenerationField(
                name="reveal_mode",
                label="Reveal mode",
                field_type="select",
                default="word",
                options=(
                    {"value": "word", "label": "Per word"},
                    {"value": "letter", "label": "Letter"},
                    {"value": "whole_puzzle", "label": "Whole puzzle"},
                ),
            ),
            GenerationField(
                name="gimme_mode",
                label="Gimme mode",
                field_type="select",
                default="letters",
                options=(
                    {"value": "letters", "label": "Individual letters"},
                    {"value": "entries", "label": "Whole entries"},
                ),
            ),
            GenerationField(
                name="gimme_count",
                label="Gimme count",
                field_type="number",
                default="0",
                help_text="Number of entries or letters to prefill, depending on Gimme mode.",
                minimum=0,
                maximum=30,
            ),
            GenerationField(
                name="seed",
                label="Layout seed",
                field_type="text",
                default="",
                help_text="Optional. Reuse the same seed to keep a layout stable.",
            ),
        ),
        generation_fields=(
            GenerationField(
                name="grid_size",
                label="Grid size",
                field_type="select",
                default="difficulty_default",
                help_text="Pick a target canvas size before the crossword is trimmed.",
                options=(
                    {"value": "difficulty_default", "label": "Use difficulty default"},
                    {"value": "8", "label": "8x8"},
                    {"value": "10", "label": "10x10"},
                    {"value": "12", "label": "12x12"},
                    {"value": "14", "label": "14x14"},
                    {"value": "custom", "label": "Custom"},
                ),
            ),
            GenerationField(
                name="custom_grid_size",
                label="Custom grid size",
                field_type="number",
                default="",
                help_text="Only used when Grid size is Custom.",
                minimum=5,
                maximum=25,
            ),
            GenerationField(
                name="answer_count_min",
                label="Minimum answers",
                field_type="number",
                default="",
                help_text="Optional. Generation fails if fewer answers can be placed.",
                minimum=3,
                maximum=30,
            ),
            GenerationField(
                name="answer_count",
                label="Maximum answers",
                field_type="number",
                default="",
                help_text="Optional. Leave blank to let difficulty choose.",
                minimum=3,
                maximum=30,
            ),
            GenerationField(
                name="clue_style",
                label="Clue style",
                field_type="select",
                default="mixed",
                options=(
                    {"value": "mixed", "label": "Mixed"},
                    {"value": "definition", "label": "Definitions first"},
                    {"value": "clue_tag", "label": "Clue tags first"},
                    {"value": "easier", "label": "Easier"},
                    {"value": "more_cryptic", "label": "More cryptic"},
                ),
            ),
            GenerationField(
                name="more_clues_depth",
                label="More clues depth",
                field_type="select",
                default="multi_step",
                options=(
                    {"value": "none", "label": "None"},
                    {"value": "one_hint", "label": "One hint"},
                    {"value": "multi_step", "label": "Multi-step"},
                ),
            ),
            GenerationField(
                name="check_mode",
                label="Check mode",
                field_type="select",
                default="whole_puzzle",
                options=(
                    {"value": "whole_puzzle", "label": "Whole puzzle only"},
                    {"value": "per_word", "label": "Per-word check"},
                ),
            ),
            GenerationField(
                name="auto_highlight_correct",
                label="Auto-highlight correct words",
                field_type="select",
                default="no",
                options=(
                    {"value": "no", "label": "No"},
                    {"value": "yes", "label": "Yes"},
                ),
            ),
            GenerationField(
                name="reveal_mode",
                label="Reveal mode",
                field_type="select",
                default="word",
                options=(
                    {"value": "word", "label": "Per word"},
                    {"value": "letter", "label": "Letter"},
                    {"value": "whole_puzzle", "label": "Whole puzzle"},
                ),
            ),
            GenerationField(
                name="gimme_mode",
                label="Gimme mode",
                field_type="select",
                default="entries",
                options=(
                    {"value": "entries", "label": "Whole entries"},
                    {"value": "letters", "label": "Individual letters"},
                ),
            ),
            GenerationField(
                name="gimme_count",
                label="Gimme count",
                field_type="number",
                default="",
                help_text="Optional. Number of entries or letters to prefill, depending on Gimme mode.",
                minimum=0,
                maximum=30,
            ),
        ),
    )
)
