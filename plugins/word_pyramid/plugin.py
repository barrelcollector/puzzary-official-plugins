from __future__ import annotations

import random
from collections import Counter
from typing import Any

from app.clues import word_clue_tiers
from app.content import words_for_theme
from app.puzzles import GeneratedPuzzle, GenerationField, PrintLayout, PuzzleType, register_puzzle_type
from app.group_actions import row_collaboration


GUARANTEED_CHAINS = [
    ["TIP", "PINT", "POINT", "PISTON", "OPTIONS", "STOOPING"],
    ["AN", "RAN", "EARN", "ANGER", "ORANGE"],
    ["TO", "TOP", "PLOT", "PILOT", "PISTOL"],
    ["IN", "TIN", "TINE", "INERT", "INTER"],
    ["AS", "SAY", "STAY", "TASTY"],
]

FALLBACK_CLUES = {
    "AN": ["A form of the indefinite article.", "Comes before a vowel sound."],
    "RAN": ["Moved quickly on foot.", "Operated or managed something."],
    "EARN": ["Receive through work or effort.", "Gain as a result of action."],
    "ANGER": ["A strong feeling of displeasure.", "Irritation with more heat behind it."],
    "ORANGE": ["A citrus fruit or a color.", "Between red and yellow."],
    "TO": ["A direction word.", "Points toward a destination."],
    "TOP": ["The highest part.", "A lid or upper surface."],
    "PLOT": ["A storyline or plan.", "A small piece of land."],
    "PILOT": ["One who flies an aircraft.", "A test episode or trial run."],
    "PISTOL": ["A small handheld firearm.", "A word that grows from PILOT by one letter."],
    "IN": ["Inside or within.", "The opposite of out."],
    "TIN": ["A silvery metal.", "A small metal container."],
    "TINE": ["A prong on a fork or antler.", "A pointed projection."],
    "INERT": ["Not moving or chemically inactive.", "Lacking power to move."],
    "INTER": ["To bury.", "Place in a grave."],
    "AS": ["Used for comparison.", "In the role of."],
    "SAY": ["Speak or express.", "Offer an opinion."],
    "STAY": ["Remain in place.", "Delay leaving."],
    "TASTY": ["Having a pleasant flavor.", "Good to eat."],
    "TIP": ["A small piece of advice.", "Also the pointed end of something."],
    "PINT": ["A liquid measure equal to two cups.", "Common size for milk, cream, or a pub pour."],
    "POINT": ["A sharp end, exact location, or main idea.", "A dot on a map or score marker."],
    "PISTON": ["A moving engine part inside a cylinder.", "It slides back and forth to transfer force."],
    "OPTIONS": ["Available choices.", "Menu items or possible actions."],
    "STOOPING": ["Bending the body forward and down.", "Lowering posture to reach something."],
}


def normalize_word(value: str) -> str:
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def word_clues(word: Any, definition: Any) -> list[str]:
    definitions = [definition] if definition is not None else None
    clues = word_clue_tiers(word, definitions)
    notes = getattr(word, "properties", {}) or {}
    if isinstance(notes, dict):
        note = str(notes.get("notes", "") or "").strip()
        if note and note not in clues:
            clues.append(note)
    return clues


def build_source(word_entries: Any, difficulty: str, excluded_tag_ids: set[int] | None = None) -> list[dict] | None:
    entries = []
    seen = set()
    for entry in word_entries or []:
        word = entry.get("word") if isinstance(entry, dict) else None
        if word is None:
            continue
        normalized = normalize_word(getattr(word, "word", ""))
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        definition = entry.get("definition") if isinstance(entry, dict) else None
        clues = word_clues(word, definition)
        if not clues:
            continue
        entries.append(
            {
                "word": normalized,
                "display": str(getattr(word, "display_text", "") or normalized),
                "clues": clues,
                "definition_id": getattr(definition, "id", None) if definition is not None else None,
            }
        )
    return entries or None


def fallback_source(theme: str, difficulty: str) -> list[dict]:
    guaranteed = [word for chain in GUARANTEED_CHAINS for word in chain]
    themed = [word for word in words_for_theme(theme, difficulty) if normalize_word(word) in FALLBACK_CLUES]
    words = []
    for word in themed + guaranteed:
        normalized = normalize_word(word)
        if normalized and normalized not in words:
            words.append(normalized)
    return [
        {
            "word": normalize_word(word),
            "display": str(word).title(),
            "clues": FALLBACK_CLUES[normalize_word(word)],
            "definition_id": None,
        }
        for word in words
    ]


def extends_by_one_letter(previous: str, candidate: str) -> bool:
    if len(candidate) != len(previous) + 1:
        return False
    previous_counts = Counter(previous)
    candidate_counts = Counter(candidate)
    return all(candidate_counts[letter] >= count for letter, count in previous_counts.items())


def integer_option(options: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(options.get(key, "")).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def choose_chain(
    source_data: list[dict],
    difficulty: str,
    rng: random.Random,
    target_count: int | None = None,
    starting_length: int | None = None,
    strict_chain: bool = True,
) -> list[dict]:
    target_count = target_count or {"easy": 4, "medium": 5, "hard": 6}.get(difficulty, 4)
    max_chain_pool = 300
    candidates_by_length: dict[int, list[dict]] = {}
    for entry in source_data:
        word = normalize_word(entry.get("word", ""))
        if len(word) < 2:
            continue
        item = {**entry, "word": word}
        candidates_by_length.setdefault(len(word), []).append(item)

    for options in candidates_by_length.values():
        rng.shuffle(options)

    chains: list[list[dict]] = []

    def extend(chain: list[dict]) -> None:
        if len(chains) >= max_chain_pool:
            return
        if len(chain) == target_count:
            chains.append(chain)
            return
        previous = chain[-1]["word"]
        if strict_chain:
            next_options = [
                entry
                for entry in candidates_by_length.get(len(previous) + 1, [])
                if extends_by_one_letter(previous, entry["word"])
            ]
        else:
            next_options = list(candidates_by_length.get(len(previous) + 1, []))
        rng.shuffle(next_options)
        for entry in next_options:
            extend([*chain, entry])
            if len(chains) >= max_chain_pool:
                return

    starts = [
        entry
        for length, options in candidates_by_length.items()
        for entry in options
        if starting_length is None or length == starting_length
    ]
    if not starts and starting_length is not None:
        starts = [entry for options in candidates_by_length.values() for entry in options]
    rng.shuffle(starts)
    for entry in starts:
        extend([entry])
        if len(chains) >= max_chain_pool:
            break
    if chains:
        return rng.choice(chains)

    best_chains: list[list[dict]] = []

    def collect_best(chain: list[dict]) -> None:
        nonlocal best_chains
        if best_chains and len(best_chains) >= max_chain_pool:
            return
        if not best_chains or len(chain) > len(best_chains[0]):
            best_chains = [chain]
        elif len(chain) == len(best_chains[0]):
            best_chains.append(chain)
        previous = chain[-1]["word"]
        next_entries = list(candidates_by_length.get(len(previous) + 1, []))
        rng.shuffle(next_entries)
        for entry in next_entries:
            if not strict_chain or extends_by_one_letter(previous, entry["word"]):
                collect_best([*chain, entry])
            if best_chains and len(best_chains) >= max_chain_pool:
                return

    for entry in starts:
        collect_best([entry])
    best_chains = [chain for chain in best_chains if len(chain) >= 3]
    if best_chains:
        return rng.choice(best_chains)
    raise ValueError("Word pyramid generation needs at least three words where each row adds one letter to the previous row.")


def gimme_count_for_difficulty(difficulty: str, row_count: int) -> int:
    requested = {"easy": 1, "medium": 1, "hard": 0}.get(difficulty, 0)
    return min(requested, max(0, row_count - 1))


def check_answer(answer: str, solution_payload: dict) -> tuple[bool, int, int]:
    rows = solution_payload.get("rows", [])
    expected = [str(row["answer"]).upper() for row in rows]
    supplied = [
        normalize_word(part)
        for part in answer.replace("\n", ",").replace(";", ",").split(",")
        if normalize_word(part)
    ]
    if len(supplied) <= 1 and "," not in answer and "\n" not in answer and ";" not in answer:
        supplied = [normalize_word(part) for part in answer.split() if normalize_word(part)]
    supplied_index = 0
    matched = 0
    is_correct = True
    for index, row in enumerate(rows):
        if row.get("gimme"):
            matched += 1
            continue
        value = supplied[supplied_index] if supplied_index < len(supplied) else ""
        supplied_index += 1
        if value == expected[index]:
            matched += 1
        else:
            is_correct = False
    if supplied_index < len(supplied):
        is_correct = False
    return is_correct, len(expected), matched


def normalize_progress(payload: Any, solution_payload: dict) -> dict:
    answers = getattr(payload, "answers", {}) if payload is not None else {}
    if not isinstance(answers, dict):
        answers = {}
    expected_rows = solution_payload.get("rows", [])
    normalized = {}
    for index, row in enumerate(expected_rows):
        if row.get("gimme"):
            normalized[str(index)] = str(row.get("answer", "")).upper()
            continue
        value = normalize_word(answers.get(str(index), ""))
        if value:
            normalized[str(index)] = value[: len(str(row.get("answer", "")))]
    return {"answers": normalized}


def offline_solution_state(solution_payload: dict) -> dict:
    return {"answers": {
        str(index): str(row.get("answer", "")).upper()
        for index, row in enumerate(solution_payload.get("rows", []))
        if not row.get("gimme")
    }}


def count_progress(progress_payload: dict, solution_payload: dict) -> tuple[int, int]:
    answers = progress_payload.get("answers", {})
    if not isinstance(answers, dict):
        answers = {}
    rows = solution_payload.get("rows", [])
    correct = 0
    filled = 0
    for index, row in enumerate(rows):
        value = normalize_word(answers.get(str(index), ""))
        if row.get("gimme") or value == str(row.get("answer", "")).upper():
            correct += 1
        if row.get("gimme") or len(value) == len(str(row.get("answer", ""))):
            filled += 1
    total = len(rows)
    return (total if total > 0 and correct == total else min(filled, max(0, total - 1))), total


def build_preview(print_payload: dict, play_payload: dict, metadata: dict) -> dict:
    payload = print_payload if isinstance(print_payload, dict) else play_payload
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    return {
        "kind": "word_pyramid",
        "rows": [
            {
                "length": int(row.get("length", 0)),
                "number": row.get("number"),
                "clue": str(row.get("clue", ""))[:70],
                "gimme": bool(row.get("gimme")),
                "given": str(row.get("given", "")) if row.get("gimme") else "",
            }
            for row in rows[:6]
            if isinstance(row, dict)
        ],
        "meta": f"{len(rows)} rows",
    }


def parse_manual_rows(value: Any) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for line in str(value or "").splitlines():
        parts = [part.strip() for part in line.split("|")]
        answer = normalize_word(parts[0] if parts else "")
        if not answer:
            continue
        if answer in seen:
            raise ValueError(f"Duplicate word pyramid row: {answer}")
        seen.add(answer)
        clues = [part for part in parts[1:] if part]
        if not clues:
            clues = FALLBACK_CLUES.get(answer, [])
        if not clues:
            raise ValueError(f"Word pyramid answer '{answer}' needs at least one clue or definition.")
        rows.append({"word": answer, "clues": clues, "definition_id": None})
    if len(rows) < 3:
        raise ValueError("Manual word pyramid builder needs at least 3 rows.")
    for index in range(1, len(rows)):
        previous = rows[index - 1]["word"]
        current = rows[index]["word"]
        if len(current) != len(previous) + 1:
            raise ValueError("Each word pyramid row must be exactly one letter longer than the row above it.")
    return rows


def build_manual_puzzle(options: dict[str, Any]) -> GeneratedPuzzle:
    rows_source = parse_manual_rows(options.get("rows", ""))
    chain_rule = str(options.get("chain_rule", "strict_anagram_plus_one")).strip().lower()
    if chain_rule not in {"strict_anagram_plus_one", "loose_clue_ladder"}:
        chain_rule = "strict_anagram_plus_one"
    if chain_rule == "strict_anagram_plus_one":
        for index in range(1, len(rows_source)):
            if not extends_by_one_letter(rows_source[index - 1]["word"], rows_source[index]["word"]):
                raise ValueError("Strict word pyramid rows must use every prior letter plus one new letter.")
    clue_placement = str(options.get("clue_placement", "inline")).strip().lower()
    if clue_placement not in {"inline", "numbered_below"}:
        clue_placement = "inline"
    print_layout = str(options.get("print_layout", "alternating")).strip().lower()
    if print_layout not in {"alternating", "pyramid_clues_below"}:
        print_layout = "alternating"
    if print_layout == "pyramid_clues_below":
        clue_placement = "numbered_below"
    gimme_count = integer_option(options, "gimme_count", 0, 0, max(0, len(rows_source) - 1))
    rows = []
    solution_rows = []
    for index, entry in enumerate(rows_source):
        answer = entry["word"]
        clues = entry.get("clues") or []
        if not clues:
            raise ValueError(f"Word pyramid answer '{answer}' needs at least one clue or definition.")
        row = {
            "index": index,
            "number": index + 1,
            "length": len(answer),
            "clue": clues[0],
            "clues": clues,
            "definition_id": entry.get("definition_id"),
            "gimme": index < gimme_count,
        }
        if row["gimme"]:
            row["given"] = answer
        rows.append(row)
        solution_rows.append({**row, "answer": answer})
    prompt = (
        "Fill each row. Every answer is an anagram of the row above it plus one new letter."
        if chain_rule == "strict_anagram_plus_one"
        else "Fill each row. Every answer is one letter longer than the row above it."
    )
    settings = {
        "row_count": len(rows),
        "starting_word_length": rows[0]["length"],
        "clue_placement": clue_placement,
        "chain_rule": chain_rule,
        "print_layout": print_layout,
    }
    payload = {"kind": "word_pyramid", "rows": rows, "settings": settings}
    return GeneratedPuzzle(
        title="Manual Word Pyramid",
        prompt=prompt,
        print_payload=payload,
        play_payload=payload,
        solution_payload={"rows": solution_rows, "settings": settings},
        hints=[
            f"The pyramid has {len(rows)} rows.",
            "Each answer is one letter longer than the row above it.",
            f"The shortest answer has {rows[0]['length']} letters.",
        ],
        metadata={
            "generator": "manual.word_pyramid.v1",
            "manual": True,
            "row_count": len(rows),
            "gimmes": {"mode": "starting_rows", "count": gimme_count},
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
    source = source_data if source_data is not None else fallback_source(theme, difficulty)
    generation_seed = seed or f"word_pyramid:{theme}:{difficulty}:{','.join(str(item.get('word', '')) for item in source)}"
    rng = random.Random(generation_seed)
    target_row_count = integer_option(generation_options, "row_count", {"easy": 4, "medium": 5, "hard": 6}.get(difficulty, 4), 3, 10)
    starting_word_length = integer_option(generation_options, "starting_word_length", 0, 0, 12)
    starting_word_length = starting_word_length or None
    chain_rule = str(generation_options.get("chain_rule", "strict_anagram_plus_one")).strip().lower()
    if chain_rule not in {"strict_anagram_plus_one", "loose_clue_ladder"}:
        chain_rule = "strict_anagram_plus_one"
    strict_chain = chain_rule == "strict_anagram_plus_one"
    clue_placement = str(generation_options.get("clue_placement", "inline")).strip().lower()
    if clue_placement not in {"inline", "numbered_below"}:
        clue_placement = "inline"
    print_layout = str(generation_options.get("print_layout", "alternating")).strip().lower()
    if print_layout not in {"alternating", "pyramid_clues_below"}:
        print_layout = "alternating"
    if print_layout == "pyramid_clues_below":
        clue_placement = "numbered_below"
    try:
        chain = choose_chain(source, difficulty, rng, target_row_count, starting_word_length, strict_chain)
    except ValueError:
        if source_data is None:
            raise
        chain = choose_chain([*source, *fallback_source(theme, difficulty)], difficulty, rng, target_row_count, starting_word_length, strict_chain)

    rows = []
    solution_rows = []
    default_gimme_count = gimme_count_for_difficulty(difficulty, len(chain))
    gimme_count = integer_option(generation_options, "gimme_count", default_gimme_count, 0, max(0, len(chain) - 1))
    for index, entry in enumerate(chain):
        answer = normalize_word(entry.get("word", ""))
        clues = [str(clue).strip() for clue in entry.get("clues", []) if str(clue).strip()]
        if not clues:
            raise ValueError(f"Word pyramid answer '{answer}' needs at least one clue or definition.")
        primary = clues[0]
        is_gimme = index < gimme_count
        row = {
            "index": index,
            "number": index + 1,
            "length": len(answer),
            "clue": primary,
            "clues": clues,
            "definition_id": entry.get("definition_id"),
            "gimme": is_gimme,
        }
        if is_gimme:
            row["given"] = answer
        rows.append(row)
        solution_rows.append({**row, "answer": answer})

    prompt = (
        "Fill each row. Every answer is an anagram of the row above it plus one new letter."
        if strict_chain
        else "Fill each row. Every answer is one letter longer than the row above it."
    )
    settings = {
        "row_count": len(rows),
        "starting_word_length": rows[0]["length"] if rows else starting_word_length,
        "clue_placement": clue_placement,
        "chain_rule": chain_rule,
        "print_layout": print_layout,
    }
    play_payload = {"kind": "word_pyramid", "rows": rows, "settings": settings}
    print_payload = {"kind": "word_pyramid", "rows": rows, "settings": settings}
    solution_payload = {"rows": solution_rows, "settings": settings}
    return GeneratedPuzzle(
        title=f"{theme.replace('_', ' ').title()} Word Pyramid",
        prompt=prompt,
        print_payload=print_payload,
        play_payload=play_payload,
        solution_payload=solution_payload,
        hints=[
            f"The pyramid has {len(rows)} rows.",
            "Each answer uses every letter from the row above, plus one new letter.",
            f"The shortest answer has {rows[0]['length']} letters.",
        ],
        metadata={
            "generator": "local.word_pyramid.v1",
            "seed": generation_seed,
            "row_count": len(rows),
            "gimmes": {"mode": "starting_rows", "count": gimme_count},
            "generation_options": settings | {"gimme_count": gimme_count},
        },
    )


register_puzzle_type(
    PuzzleType(
        slug="word_pyramid",
        label="Word pyramid",
        generator=generate,
        source_builder=build_source,
        answer_checker=check_answer,
        progress_normalizer=normalize_progress,
        progress_counter=count_progress,
        collaboration=row_collaboration(),
        collaboration_value_limit=80,
        preview_builder=build_preview,
        description="A clue-driven chain where each answer grows by one letter.",
        play_script="/plugins/word_pyramid/static/word-pyramid.js?v=5",
        **({"supports_offline": True, "offline_progress_fields": ("answers",), "offline_validation": "solution_hash", "offline_solution_state": offline_solution_state, "offline_notes": "Row entries and whole-puzzle checking work offline; extra clues require a connection."} if "offline_solution_state" in PuzzleType.__dataclass_fields__ else {}),
        supports_print=True,
        supports_web_play=True,
        source_requirements=("word_bank", "definitions"),
        print_layout=PrintLayout(
            slug="word_pyramid",
            sheet_class="print-layout-word-pyramid",
            instructions="Fill the pyramid from top to bottom.",
            notes=("Rows can print alternating with clues or as a pyramid with numbered clues below.",),
        ),
        supports_gimmes=True,
        gimme_modes=("starting_rows",),
        manual_builder=build_manual_puzzle,
        manual_editor_fields=(
            GenerationField(
                name="rows",
                label="Rows and clues",
                field_type="textarea",
                required=True,
                help_text="One row per line: ANSWER | primary clue | optional extra clue. Each row must be one letter longer.",
                default="TIP | A small piece of advice.\nPINT | A liquid measure equal to two cups.\nPOINT | A sharp end, exact location, or main idea.\nPISTON | A moving engine part inside a cylinder.",
            ),
            GenerationField(
                name="clue_placement",
                label="Clue placement",
                field_type="select",
                default="numbered_below",
                options=(
                    {"value": "inline", "label": "Between rows"},
                    {"value": "numbered_below", "label": "Numbered below"},
                ),
            ),
            GenerationField(
                name="gimme_count",
                label="Gimme rows",
                field_type="number",
                default="0",
                help_text="Number of starting rows to prefill.",
                minimum=0,
                maximum=10,
            ),
            GenerationField(
                name="chain_rule",
                label="Chain rule",
                field_type="select",
                default="strict_anagram_plus_one",
                options=(
                    {"value": "strict_anagram_plus_one", "label": "Anagram plus one"},
                    {"value": "loose_clue_ladder", "label": "Loose clue ladder"},
                ),
            ),
            GenerationField(
                name="print_layout",
                label="Print layout",
                field_type="select",
                default="pyramid_clues_below",
                options=(
                    {"value": "alternating", "label": "Alternating rows and clues"},
                    {"value": "pyramid_clues_below", "label": "Pyramid with clues below"},
                ),
            ),
        ),
        generation_fields=(
            GenerationField(
                name="row_count",
                label="Row count",
                field_type="number",
                default="",
                help_text="Optional. Leave blank to let difficulty choose.",
                minimum=3,
                maximum=10,
            ),
            GenerationField(
                name="starting_word_length",
                label="Starting word length",
                field_type="number",
                default="",
                help_text="Optional. Leave blank to let the generator choose.",
                minimum=2,
                maximum=12,
            ),
            GenerationField(
                name="clue_placement",
                label="Clue placement",
                field_type="select",
                default="inline",
                options=(
                    {"value": "inline", "label": "Between rows"},
                    {"value": "numbered_below", "label": "Numbered below"},
                ),
            ),
            GenerationField(
                name="gimme_count",
                label="Gimme rows",
                field_type="number",
                default="",
                help_text="Optional. Number of starting rows to prefill.",
                minimum=0,
                maximum=10,
            ),
            GenerationField(
                name="chain_rule",
                label="Chain rule",
                field_type="select",
                default="strict_anagram_plus_one",
                options=(
                    {"value": "strict_anagram_plus_one", "label": "Anagram plus one"},
                    {"value": "loose_clue_ladder", "label": "Loose clue ladder"},
                ),
            ),
            GenerationField(
                name="print_layout",
                label="Print layout",
                field_type="select",
                default="alternating",
                options=(
                    {"value": "alternating", "label": "Alternating rows and clues"},
                    {"value": "pyramid_clues_below", "label": "Pyramid with clues below"},
                ),
            ),
        ),
    )
)
