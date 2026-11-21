from __future__ import annotations

import json
import random
from typing import Any

from app.puzzles import GeneratedPuzzle, GenerationField, PrintLayout, PuzzleType, register_puzzle_type


DIRECTIONS = {
    "n": (0, -1, "s"),
    "e": (1, 0, "w"),
    "s": (0, 1, "n"),
    "w": (-1, 0, "e"),
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


def maze_size(options: dict[str, Any], difficulty: str) -> tuple[int, int, str]:
    preset = str(options.get("maze_size", "")).strip().lower()
    if preset == "small":
        return 10, 10, "small"
    if preset == "medium":
        return 14, 14, "medium"
    if preset == "large":
        return 18, 18, "large"
    if preset == "wide":
        return 20, 12, "wide"
    if preset == "custom":
        width = integer_option(options, "custom_width", 14, 5, 30)
        height = integer_option(options, "custom_height", width, 5, 30)
        return width, height, "custom"
    defaults = {
        "easy": (10, 10, "small"),
        "medium": (14, 14, "medium"),
        "hard": (18, 18, "large"),
    }
    return defaults.get(difficulty, defaults["medium"])


def new_grid(width: int, height: int) -> list[list[dict[str, Any]]]:
    return [
        [
            {"x": x, "y": y, "walls": {"n": True, "e": True, "s": True, "w": True}}
            for x in range(width)
        ]
        for y in range(height)
    ]


def carve_maze(width: int, height: int, rng: random.Random) -> list[list[dict[str, Any]]]:
    grid = new_grid(width, height)
    visited = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        x, y = stack[-1]
        neighbors = []
        for direction, (dx, dy, opposite) in DIRECTIONS.items():
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                neighbors.append((direction, opposite, nx, ny))
        if not neighbors:
            stack.pop()
            continue
        direction, opposite, nx, ny = rng.choice(neighbors)
        grid[y][x]["walls"][direction] = False
        grid[ny][nx]["walls"][opposite] = False
        visited.add((nx, ny))
        stack.append((nx, ny))
    grid[0][0]["walls"]["w"] = False
    grid[height - 1][width - 1]["walls"]["e"] = False
    return grid


def add_loops(grid: list[list[dict[str, Any]]], rng: random.Random, loop_count: int) -> None:
    height = len(grid)
    width = len(grid[0]) if height else 0
    candidates = []
    for y in range(height):
        for x in range(width):
            for direction, (dx, dy, opposite) in DIRECTIONS.items():
                nx, ny = x + dx, y + dy
                if direction not in {"e", "s"}:
                    continue
                if 0 <= nx < width and 0 <= ny < height and grid[y][x]["walls"][direction]:
                    candidates.append((x, y, direction, nx, ny, opposite))
    rng.shuffle(candidates)
    for x, y, direction, nx, ny, opposite in candidates[:loop_count]:
        grid[y][x]["walls"][direction] = False
        grid[ny][nx]["walls"][opposite] = False


def solve_maze(grid: list[list[dict[str, Any]]]) -> list[dict[str, int]]:
    height = len(grid)
    width = len(grid[0]) if height else 0
    target = (width - 1, height - 1)
    queue = [(0, 0)]
    parents: dict[tuple[int, int], tuple[int, int] | None] = {(0, 0): None}
    for x, y in queue:
        if (x, y) == target:
            break
        for direction, (dx, dy, _opposite) in DIRECTIONS.items():
            if grid[y][x]["walls"][direction]:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in parents:
                parents[(nx, ny)] = (x, y)
                queue.append((nx, ny))
    if target not in parents:
        raise ValueError("Maze generation produced an unsolvable layout.")
    path = []
    cursor: tuple[int, int] | None = target
    while cursor is not None:
        x, y = cursor
        path.append({"x": x, "y": y})
        cursor = parents[cursor]
    path.reverse()
    return path


def solution_polyline(path: list[dict[str, int]], cell_size: int) -> str:
    half = cell_size // 2
    return " ".join(f"{point['x'] * cell_size + half},{point['y'] * cell_size + half}" for point in path)


def parse_answer(answer: Any) -> dict[str, Any]:
    if isinstance(answer, str):
        if answer.strip().lower() in {"done", "complete", "completed", "solved", "true", "yes"}:
            return {"completed": True}
        try:
            parsed = json.loads(answer)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed.get("answers", parsed)
    if isinstance(answer, dict):
        return answer.get("answers", answer)
    return {}


def normalize_trace_path(raw_path: Any) -> list[dict[str, int]]:
    if isinstance(raw_path, str):
        try:
            raw_path = json.loads(raw_path)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw_path, list):
        return []
    path = []
    for point in raw_path:
        if not isinstance(point, dict):
            continue
        try:
            path.append({"x": int(point.get("x")), "y": int(point.get("y"))})
        except (TypeError, ValueError):
            continue
    return path


def trace_is_valid(path: list[dict[str, int]], solution_payload: dict, start: dict | None = None) -> bool:
    grid = solution_payload.get("grid", [])
    height = len(grid)
    width = len(grid[0]) if height else 0
    if not path:
        return False
    if path[0] != (start or {"x": 0, "y": 0}):
        return False
    seen = set()
    previous = None
    for point in path:
        x, y = point["x"], point["y"]
        if not (0 <= x < width and 0 <= y < height):
            return False
        key = (x, y)
        if key in seen:
            return False
        seen.add(key)
        if previous is not None:
            px, py = previous
            dx, dy = x - px, y - py
            direction = None
            for name, (step_x, step_y, _opposite) in DIRECTIONS.items():
                if (dx, dy) == (step_x, step_y):
                    direction = name
                    break
            if direction is None or grid[py][px]["walls"].get(direction):
                return False
        previous = key
    return True


def trace_is_complete(path: list[dict[str, int]], solution_payload: dict) -> bool:
    grid = solution_payload.get("grid", [])
    height = len(grid)
    width = len(grid[0]) if height else 0
    return bool(path and trace_is_valid(path, solution_payload) and path[-1] == {"x": width - 1, "y": height - 1})


def check_answer(answer: str, solution_payload: dict) -> tuple[bool, int, int]:
    payload = parse_answer(answer)
    path = normalize_trace_path(payload.get("path", []))
    completed = trace_is_complete(path, solution_payload)
    return completed, 1, 1 if completed else 0


def normalize_progress(payload: Any, solution_payload: dict) -> dict:
    raw_answers = getattr(payload, "answers", {}) if payload is not None else {}
    path = normalize_trace_path(raw_answers.get("path", []))
    if path and not trace_is_valid(path, solution_payload):
        path = []
    completed = trace_is_complete(path, solution_payload)
    return {
        "answers": {
            "completed": "true" if completed else "",
            "path": json.dumps(path, separators=(",", ":")) if path else "",
        }
    }


def count_progress(progress_payload: dict, _solution_payload: dict) -> tuple[int, int]:
    config = progress_payload.get('maze_group', {})
    answers = progress_payload.get('answers', {})
    if config.get('mode') == 'companions':
        players = progress_payload.get('_participants', [])
        return sum(trace_is_complete(normalize_trace_path(answers.get(f'path:{p}', '')), _solution_payload) for p in players), len(players)
    if config.get('mode') == 'rally':
        checkpoints = config['checkpoints']
        return sum(segment_complete(normalize_trace_path(answers.get(f'leg:{i}', '')), _solution_payload, checkpoints[i], checkpoints[i + 1]) for i in range(len(checkpoints) - 1)), len(checkpoints) - 1
    if config:
        return int(trace_is_complete(normalize_trace_path(answers.get('path', '')), _solution_payload)), 1
    answers = progress_payload.get("answers", {}) if isinstance(progress_payload, dict) else {}
    completed = str(answers.get("completed", "")).lower() in {"true", "yes", "1", "done", "complete", "solved"}
    return (1 if completed else 0), 1


def segment_complete(path, solution, start, finish):
    return bool(path and trace_is_valid(path, solution, start) and path[-1] == finish)


def setup_collaboration(state, options, solution):
    from copy import deepcopy
    if set(options) - {'maze_mode', 'rally_legs'}: raise ValueError('Unknown maze group option')
    previous = state.get('maze_group', {})
    mode = options.get('maze_mode', previous.get('mode', 'co_op'))
    if mode not in ('co_op', 'companions', 'rally'): raise ValueError('Unknown maze mode')
    try: requested = int(options.get('rally_legs', previous.get('rally_legs', 4)))
    except (TypeError, ValueError): raise ValueError('Rally legs must be a number')
    if not 2 <= requested <= 50: raise ValueError('Rally needs 2 to 50 legs')
    if previous.get('mode') == mode and previous.get('rally_legs') == requested: return deepcopy(state)
    result = deepcopy(state)
    result['answers'] = {}
    config = {'mode': mode, 'rally_legs': requested}
    if mode == 'rally':
        route = solve_maze(solution['grid'])
        legs = min(requested, len(route) - 1)
        config['checkpoints'] = [route[i * (len(route) - 1) // legs] for i in range(legs + 1)]
    result['maze_group'] = config
    return result


def collaboration(state, action, solution):
    from copy import deepcopy
    result = deepcopy(state)
    if not result.get('maze_group'): result = setup_collaboration(result, {}, solution)
    config = result['maze_group']
    answers = dict(result.get('answers', {}))
    actor = action['_actor']
    participants = action['participants']
    mode = config['mode']
    start = {'x': 0, 'y': 0}
    finish = solution.get('end') or {'x': len(solution['grid'][0]) - 1, 'y': len(solution['grid']) - 1}
    key = f'path:{actor}' if mode == 'companions' else 'path'
    if mode == 'rally':
        checkpoints = config['checkpoints']
        index = next((i for i in range(len(checkpoints) - 1) if not segment_complete(normalize_trace_path(answers.get(f'leg:{i}', '')), solution, checkpoints[i], checkpoints[i + 1])), None)
        if index is None:
            if action['kind'] == 'check': return result
            raise ValueError('Rally is already complete')
        if participants[index % len(participants)] != actor: raise ValueError('Wait for your Rally leg')
        key = f'leg:{index}'
        start, finish = checkpoints[index:index + 2]
    kind = action['kind']
    if kind == 'patch':
        if set(action.get('changes', {})) - {key}: raise ValueError('You can only edit your active path')
        if key in action.get('changes', {}):
            value = action['changes'][key]
            if not value: answers.pop(key, None)
            else:
                try: raw = json.loads(value)
                except (ValueError, TypeError): raise ValueError('Invalid path JSON')
                path = normalize_trace_path(raw)
                if not isinstance(raw, list) or path != raw or not trace_is_valid(path, solution, start):
                    raise ValueError('Path must start at your checkpoint and cannot cross walls or itself')
                if finish in path[:-1]: raise ValueError('Stop at the next checkpoint')
                answers[key] = json.dumps(path, separators=(',', ':'))
    elif kind in ('hint', 'reveal'):
        # Follow the shortest continuation from the current endpoint, without crossing the trace.
        path = normalize_trace_path(answers.get(key, '')) or [start]
        excluded = {(p['x'], p['y']) for p in path[:-1]}
        queue = [(path[-1], [])]
        seen = set(excluded)
        extension = None
        for point, tail in queue:
            coordinate = (point['x'], point['y'])
            if coordinate in seen: continue
            seen.add(coordinate)
            if point == finish: extension = tail; break
            for direction, (dx, dy, _) in DIRECTIONS.items():
                x, y = point['x'] + dx, point['y'] + dy
                if 0 <= y < len(solution['grid']) and 0 <= x < len(solution['grid'][0]) and not solution['grid'][point['y']][point['x']]['walls'][direction]:
                    next_point = {'x': x, 'y': y}
                    queue.append((next_point, [*tail, next_point]))
        if extension is None: raise ValueError('Backtrack out of this dead end before requesting a hint')
        path += extension[:1] if kind == 'hint' else extension
        answers[key] = json.dumps(path, separators=(',', ':'))
    elif kind != 'check': raise ValueError('Unsupported action')
    result['answers'] = answers
    return result


def build_preview(print_payload: dict, play_payload: dict, _metadata: dict) -> dict:
    payload = print_payload if isinstance(print_payload, dict) else play_payload
    settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
    return {
        "kind": "maze",
        "width": int(settings.get("width", 10)),
        "height": int(settings.get("height", 10)),
        "meta": f"{settings.get('width', 10)}x{settings.get('height', 10)} maze",
    }


def generate(
    theme: str,
    difficulty: str,
    _source_data: Any = None,
    seed: str | None = None,
    _generation_options: dict[str, Any] | None = None,
) -> GeneratedPuzzle:
    generation_options = _generation_options or {}
    width, height, size_label = maze_size(generation_options, difficulty)
    generation_seed = seed or f"maze:{difficulty}:{width}x{height}"
    rng = random.Random(generation_seed)
    grid = carve_maze(width, height, rng)
    loop_default = {"easy": 2, "medium": 1, "hard": 0}.get(difficulty, 1)
    loop_count = integer_option(generation_options, "loop_count", loop_default, 0, max(0, (width * height) // 6))
    if bool_option(generation_options, "allow_loops", loop_count > 0):
        add_loops(grid, rng, loop_count)
    path = solve_maze(grid)
    cell_size = 28 if max(width, height) <= 14 else 22 if max(width, height) <= 22 else 18
    settings = {
        "width": width,
        "height": height,
        "size": size_label,
        "cell_size": cell_size,
        "allow_loops": loop_count > 0,
        "loop_count": loop_count,
    }
    payload = {
        "kind": "maze",
        "grid": grid,
        "settings": settings,
        "start": {"x": 0, "y": 0},
        "end": {"x": width - 1, "y": height - 1},
    }
    solution_payload = payload | {
        "path": path,
        "path_length": len(path),
        "solution_polyline": solution_polyline(path, cell_size),
    }
    title_prefix = theme.replace("_", " ").replace("-", " ").title().strip()
    title = f"{title_prefix} Maze" if title_prefix else "Maze"
    return GeneratedPuzzle(
        title=title,
        prompt="Draw a path from Start to Finish without crossing any walls.",
        print_payload=payload,
        play_payload=payload,
        solution_payload=solution_payload,
        hints=[
            "Start at the opening on the left.",
            "Finish at the opening on the right.",
            f"The solution path uses {len(path)} cells.",
        ],
        metadata={
            "generator": "local.maze.v1",
            "seed": generation_seed,
            "path_length": len(path),
            "generation_options": settings,
        },
    )


def build_manual_puzzle(options: dict[str, Any]) -> GeneratedPuzzle:
    if str(options.get("maze_walls") or "").strip():
        return build_manual_wall_puzzle(options)
    theme = str(options.get("_theme") or "").strip()
    difficulty = str(options.get("_difficulty") or "medium").strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"
    generated = generate(theme, difficulty, None, str(options.get("seed") or "") or None, options)
    return GeneratedPuzzle(
        title="Manual Maze",
        prompt=generated.prompt,
        print_payload=generated.print_payload,
        play_payload=generated.play_payload,
        solution_payload=generated.solution_payload,
        hints=generated.hints,
        metadata={
            **generated.metadata,
            "generator": "manual.maze.v1",
            "manual": True,
        },
    )


def parse_manual_maze(value: Any) -> tuple[int, int, list[list[dict[str, Any]]]]:
    try:
        payload = json.loads(str(value or ""))
    except json.JSONDecodeError as error:
        raise ValueError("Maze canvas data must be valid JSON.") from error
    width = integer_option(payload, "width", 10, 5, 30)
    height = integer_option(payload, "height", 10, 5, 30)
    grid = new_grid(width, height)
    raw_cells = payload.get("cells", {}) if isinstance(payload, dict) else {}
    if isinstance(raw_cells, dict):
        for key, walls in raw_cells.items():
            try:
                x_text, y_text = str(key).split(",", 1)
                x, y = int(x_text), int(y_text)
            except ValueError:
                continue
            if 0 <= x < width and 0 <= y < height and isinstance(walls, dict):
                grid[y][x]["walls"] = {
                    direction: bool(walls.get(direction, True))
                    for direction in DIRECTIONS
                }
    for y in range(height):
        for x in range(width):
            grid[y][x]["walls"]["n"] = True if y == 0 else grid[y][x]["walls"]["n"]
            grid[y][x]["walls"]["w"] = True if x == 0 else grid[y][x]["walls"]["w"]
            if x + 1 < width:
                grid[y][x + 1]["walls"]["w"] = grid[y][x]["walls"]["e"]
            if y + 1 < height:
                grid[y + 1][x]["walls"]["n"] = grid[y][x]["walls"]["s"]
    grid[0][0]["walls"]["w"] = False
    grid[height - 1][width - 1]["walls"]["e"] = False
    return width, height, grid


def build_manual_wall_puzzle(options: dict[str, Any]) -> GeneratedPuzzle:
    width, height, grid = parse_manual_maze(options.get("maze_walls", ""))
    path = solve_maze(grid)
    cell_size = 28 if max(width, height) <= 14 else 22 if max(width, height) <= 22 else 18
    settings = {
        "width": width,
        "height": height,
        "size": "manual",
        "cell_size": cell_size,
        "allow_loops": True,
        "loop_count": 0,
    }
    payload = {
        "kind": "maze",
        "grid": grid,
        "settings": settings,
        "start": {"x": 0, "y": 0},
        "end": {"x": width - 1, "y": height - 1},
    }
    return GeneratedPuzzle(
        title="Manual Maze",
        prompt="Draw a path from Start to Finish without crossing any walls.",
        print_payload=payload,
        play_payload=payload,
        solution_payload=payload | {
            "path": path,
            "path_length": len(path),
            "solution_polyline": solution_polyline(path, cell_size),
        },
        hints=[
            "Start at the opening on the left.",
            "Finish at the opening on the right.",
            f"The solution path uses {len(path)} cells.",
        ],
        metadata={
            "generator": "manual.maze.canvas.v1",
            "manual": True,
            "path_length": len(path),
            "generation_options": settings,
        },
    )


register_puzzle_type(
    PuzzleType(
        slug="maze",
        label="Maze",
        generator=generate,
        source_builder=build_source,
        answer_checker=check_answer,
        progress_normalizer=normalize_progress,
        progress_counter=count_progress,
        collaboration=collaboration,
        collaboration_setup=setup_collaboration,
        collaboration_value_limit=32768,
        collaboration_fields=(
            GenerationField('maze_mode', 'Maze mode', 'select', 'co_op', options=(
                {'value': 'co_op', 'label': 'Co-op'}, {'value': 'companions', 'label': 'Companions'}, {'value': 'rally', 'label': 'Rally'})),
            GenerationField('rally_legs', 'Rally legs', 'number', 4, minimum=2, maximum=50),
        ),
        preview_builder=build_preview,
        description="A printable maze with a start, finish, and admin-visible solution path.",
        play_script="/plugins/maze/static/maze.js?v=5",
        **({"supports_offline": True, "offline_progress_fields": ("answers",), "offline_validation": "local_rules", "offline_notes": "Path completion can be checked from the public maze layout; the server confirms it after sync."} if "supports_offline" in PuzzleType.__dataclass_fields__ else {}),
        supports_print=True,
        supports_web_play=True,
        theme_mode="none",
        print_layout=PrintLayout(
            slug="maze",
            sheet_class="print-layout-maze",
            instructions="Draw a path from Start to Finish without crossing any walls.",
            notes=("Admin solution view overlays the solved path.",),
            max_width_px=760,
        ),
        manual_builder=build_manual_puzzle,
        manual_editor_fields=(
            GenerationField(
                name="maze_walls",
                label="Canvas maze walls",
                field_type="textarea",
                default="",
                help_text="Managed by the visual editor.",
            ),
            GenerationField(
                name="maze_size",
                label="Maze size",
                field_type="select",
                default="medium",
                options=(
                    {"value": "", "label": "Difficulty default"},
                    {"value": "small", "label": "Small 10x10"},
                    {"value": "medium", "label": "Medium 14x14"},
                    {"value": "large", "label": "Large 18x18"},
                    {"value": "wide", "label": "Wide 20x12"},
                    {"value": "custom", "label": "Custom"},
                ),
            ),
            GenerationField(
                name="custom_width",
                label="Custom width",
                field_type="number",
                default="",
                help_text="Only used for Custom.",
                minimum=5,
                maximum=30,
            ),
            GenerationField(
                name="custom_height",
                label="Custom height",
                field_type="number",
                default="",
                help_text="Only used for Custom.",
                minimum=5,
                maximum=30,
            ),
            GenerationField(
                name="allow_loops",
                label="Allow loops",
                field_type="select",
                default="difficulty",
                options=(
                    {"value": "difficulty", "label": "Difficulty default"},
                    {"value": "yes", "label": "Yes"},
                    {"value": "no", "label": "No"},
                ),
            ),
            GenerationField(
                name="loop_count",
                label="Loop count",
                field_type="number",
                default="",
                help_text="Optional. Extra openings make alternate paths.",
                minimum=0,
                maximum=150,
            ),
            GenerationField(
                name="seed",
                label="Seed",
                field_type="text",
                default="",
                help_text="Optional. Reuse to recreate the same maze.",
            ),
        ),
        generation_fields=(
            GenerationField(
                name="maze_size",
                label="Maze size",
                field_type="select",
                default="",
                options=(
                    {"value": "", "label": "Difficulty default"},
                    {"value": "small", "label": "Small 10x10"},
                    {"value": "medium", "label": "Medium 14x14"},
                    {"value": "large", "label": "Large 18x18"},
                    {"value": "wide", "label": "Wide 20x12"},
                    {"value": "custom", "label": "Custom"},
                ),
            ),
            GenerationField(
                name="custom_width",
                label="Custom width",
                field_type="number",
                default="",
                help_text="Only used for Custom.",
                minimum=5,
                maximum=30,
            ),
            GenerationField(
                name="custom_height",
                label="Custom height",
                field_type="number",
                default="",
                help_text="Only used for Custom.",
                minimum=5,
                maximum=30,
            ),
            GenerationField(
                name="allow_loops",
                label="Allow loops",
                field_type="select",
                default="difficulty",
                options=(
                    {"value": "difficulty", "label": "Difficulty default"},
                    {"value": "yes", "label": "Yes"},
                    {"value": "no", "label": "No"},
                ),
            ),
            GenerationField(
                name="loop_count",
                label="Loop count",
                field_type="number",
                default="",
                help_text="Optional. Extra openings make alternate paths.",
                minimum=0,
                maximum=150,
            ),
        ),
    )
)
