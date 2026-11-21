"""Definition-based spelling reconstruction, with persistent masks and private answers."""
import json
import math
import random
import re
from collections import Counter
from types import SimpleNamespace
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from app.activity_events import record_progress_transition, record_puzzle_event
from app.database import get_db
from app.models import Puzzle, PuzzleAttempt, User
from app.permissions import can_view, register_route_permission, require
from app.puzzles import GeneratedPuzzle, GenerationField, PrintLayout, PuzzleType, register_puzzle_type

router = APIRouter()
register_route_permission("spell_it_preview", "puzzles.create")

DIFFICULTIES = {"very_easy": 18, "easy": 30, "medium": 45, "hard": 65, "expert": 80}
BANK_MODES = ("default", "off", "exact", "decoy", "hint_triggered")


def integer(value, default, low, high, label):
    if value in (None, ""):
        return default
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be a whole number")
    if isinstance(value, bool) or isinstance(value, float) and value != result:
        raise ValueError(f"{label} must be a whole number")
    if not low <= result <= high:
        raise ValueError(f"{label} must be between {low} and {high}")
    return result


def yes(value):
    if value in (True, "true", "yes", "1", 1): return True
    if value in (False, "false", "no", "0", 0): return False
    raise ValueError("Preserve first/last must be yes or no")


def settings(options, difficulty="easy"):
    difficulty = str(options.get("difficulty") or difficulty)
    if difficulty not in DIFFICULTIES:
        raise ValueError("Choose a supported Spell It difficulty")
    mode = str(options.get("letter_bank") or "default")
    if mode not in BANK_MODES:
        raise ValueError("Unsupported letter bank mode")
    if mode == "default": mode = "exact" if difficulty in ("very_easy", "easy") else "off"
    return {"difficulty": difficulty, "mask_percent": integer(options.get("mask_percent"), DIFFICULTIES[difficulty], 1, 100, "Hidden percentage"), "preserve_edges": yes(options.get("preserve_edges", "yes")), "letter_bank": mode, "decoy_count": integer(options.get("decoy_count"), 3, 0, 20, "Decoy count"), "hint_limit": integer(options.get("hint_limit"), 1, 0, 20, "Letter hint limit")}


def build_source(word_entries, difficulty, excluded_tag_ids=None):
    result, seen = [], set()
    excluded = excluded_tag_ids or set()
    for item in word_entries or []:
        word, definition = item.get("word"), item.get("definition")
        if word is None: continue
        if definition is None:
            definition = next((d for d in word.definitions if d.archived_at is None and not excluded & {t.id for t in d.tags}), None)
        clue = str(definition.definition if definition else word.clue).strip()
        answer = str(word.display_text or word.word).strip().upper()
        key = (answer, getattr(definition, "id", None))
        if not clue or key in seen: continue
        seen.add(key)
        result.append({"answer": answer, "definition": clue, "definition_id": getattr(definition, "id", None), "properties": item.get("properties", {})})
    return result


def build_entry(item, defaults, rng, index):
    if not isinstance(item, dict): raise ValueError("Each entry must be an object")
    answer = str(item.get("answer", item.get("word", ""))).strip().upper()
    definition = str(item.get("definition", item.get("clue", ""))).strip()
    if not answer or len(answer) > 80 or not definition or len(definition) > 10000:
        raise ValueError("Each entry needs an answer (up to 80 characters) and definition")
    if any(ord(ch) < 32 for ch in answer) or any(ch.isalpha() and not 'A' <= ch <= 'Z' for ch in answer):
        raise ValueError("Answers support English letters, digits, spaces and punctuation")
    letters = [i for i, char in enumerate(answer) if 'A' <= char <= 'Z']
    if not letters: raise ValueError("Each answer needs at least one letter")
    config = settings({**defaults, **{key: item[key] for key in (*defaults.keys(), "difficulty") if item.get(key) not in (None, "")}}, defaults["difficulty"])
    # A per-entry difficulty override uses its own percentage unless explicitly overridden.
    if item.get("difficulty") and item.get("mask_percent") in (None, ""):
        config["mask_percent"] = DIFFICULTIES[config["difficulty"]]
    if item.get("difficulty") and item.get("letter_bank") in (None, "") and defaults.get('_bank_is_default', True):
        config["letter_bank"] = "exact" if config["difficulty"] in ("very_easy", "easy") else "off"
    eligible = letters[1:-1] if config["preserve_edges"] and len(letters) > 2 else letters[-1:] if config["preserve_edges"] else letters
    if "hidden" in item:
        hidden = item["hidden"]
        if not isinstance(hidden, list) or not hidden or any(type(p) is not int or p not in letters for p in hidden) or len(set(hidden)) != len(hidden):
            raise ValueError("Mask positions must be unique letter indexes with at least one blank")
        hidden = sorted(hidden)
    else:
        count = min(len(eligible), max(1, math.floor(len(eligible) * config["mask_percent"] / 100 + .5)))
        hidden = sorted(rng.sample(eligible, count))
    bank = [answer[p] for p in hidden]
    if config["letter_bank"] == "decoy":
        distractors = ''.join(ch for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if ch not in answer) or "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        bank.extend(rng.choice(distractors) for _ in range(config["decoy_count"]))
    rng.shuffle(bank)
    hints = item.get("hints", [])
    if isinstance(hints, str): hints = [line.strip() for line in hints.splitlines() if line.strip()]
    if not isinstance(hints, list) or len(hints) > 20 or any(not isinstance(h, str) or len(h) > 1000 for h in hints):
        raise ValueError("Hints must be up to 20 short strings")
    return {"index": index, "answer": answer, "definition": definition, "hidden": hidden, "bank": bank, "settings": config, "hints": hints, "definition_id": item.get("definition_id"), "properties": item.get("properties", {})}


def public_entry(entry):
    return {"index": entry["index"], "definition": entry["definition"], "slots": [None if i in entry["hidden"] else ch for i, ch in enumerate(entry["answer"])], "hidden": entry["hidden"], "settings": entry["settings"], "hints": entry["hints"], "bank": entry["bank"] if entry["settings"]["letter_bank"] in ("exact", "decoy") else []}


def assemble(items, options, difficulty, theme, seed):
    config = settings(options, difficulty)
    config['_bank_is_default'] = options.get('letter_bank') in (None, '', 'default')
    if not isinstance(items, list) or not 1 <= len(items) <= 30: raise ValueError("Spell It needs 1 to 30 entries")
    rng = random.Random(str(seed))
    entries = [build_entry(item, config, rng, i) for i, item in enumerate(items)]
    public = {"kind": "spell_it", "entries": [public_entry(entry) for entry in entries], "settings": {"mode": "single" if len(entries) == 1 else "series"}}
    return GeneratedPuzzle(title="Spell It!" if not theme else f"{theme.replace('_', ' ').title()} Spell It!", prompt="Complete each spelling from its definition.", print_payload=public, play_payload=public, solution_payload={"kind": "spell_it", "entries": entries}, hints=[], metadata={"generator": "spell_it.v1", "seed": str(seed), "entry_count": len(entries)})


def generate(theme, difficulty, source=None, seed=None, generation_options=None):
    options = generation_options or {}
    difficulty = str(options.get("spelling_difficulty") or difficulty)
    count = 1 if options.get("mode", "single") == "single" else integer(options.get("entry_count"), 5, 2, 30, "Series length")
    if options.get("mode", "single") not in ("single", "series"): raise ValueError("Choose single word or series")
    candidates = list(source or [])
    rng = random.Random(str(seed))
    rng.shuffle(candidates)
    # Do not silently repeat the same spelling to reach a requested series length.
    unique = {}
    for candidate in candidates: unique.setdefault(candidate["answer"], candidate)
    if len(unique) < count: raise ValueError(f"Spell It needs {count} distinct words with definitions in the selected banks")
    return assemble(list(unique.values())[:count], options, difficulty, theme, seed)


def manual(options):
    raw = options.get("entries", [])
    try: items = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, RecursionError): raise ValueError("Entries must be valid JSON")
    difficulty = options.get("spelling_difficulty") or options.get("_difficulty", "easy")
    if difficulty == "manual": difficulty = "easy"
    return assemble(items, options, str(difficulty), str(options.get("_theme", "")), options.get("seed", "manual-spell-it"))


def ledger(answers, entry):
    raw = str(answers.get(f"hint:{entry['index']}", ""))
    return list(dict.fromkeys(int(p) for p in raw.split(',') if p.isdigit() and int(p) in entry["hidden"]))[:entry["settings"]["hint_limit"]]


def normalize_progress(payload, solution):
    supplied = getattr(payload, "answers", {}) if payload is not None else {}
    supplied = supplied if isinstance(supplied, dict) else {}
    answers = {}
    for entry in solution.get("entries", []):
        i = entry["index"]
        hinted = ledger(supplied, entry)
        if hinted: answers[f"hint:{i}"] = ','.join(map(str, hinted))
        if entry["settings"]["letter_bank"] == "hint_triggered" and supplied.get(f"bank:{i}") == "1": answers[f"bank:{i}"] = "1"
        inventory = Counter(entry['bank']) if entry['settings']['letter_bank'] in ('exact', 'decoy') or answers.get(f'bank:{i}') == '1' else None
        for position in sorted(entry["hidden"], key=lambda p: p not in hinted):
            key = f"{i}:{position}"
            value = entry["answer"][position] if position in hinted else str(supplied.get(key, "")).upper()
            if re.fullmatch('[A-Z]', value) and (inventory is None or inventory[value] > 0):
                answers[key] = value
                if inventory is not None: inventory[value] -= 1
    return {"answers": answers}


def merge_progress(payload, solution, saved):
    incoming = {k: v for k, v in (getattr(payload, "answers", {}) or {}).items() if not k.startswith(('hint:', 'bank:'))}
    incoming.update({k: v for k, v in saved.get("answers", {}).items() if k.startswith(('hint:', 'bank:'))})
    return normalize_progress(SimpleNamespace(answers=incoming), solution)


def state(entry, answers):
    value = ''.join(str(answers.get(f"{entry['index']}:{p}", "")) if p in entry["hidden"] else char for p, char in enumerate(entry["answer"]))
    if any(not answers.get(f"{entry['index']}:{p}") for p in entry["hidden"]): return "incomplete"
    return "correct" if value == entry["answer"] else "incorrect"


def count_progress(progress, solution):
    entries = solution.get("entries", [])
    return sum(state(e, progress.get("answers", {})) == "correct" for e in entries), len(entries)


def check_answer(answer, solution):
    try: value = json.loads(answer)
    except (ValueError, TypeError): value = [answer]
    entries = solution.get("entries", [])
    if isinstance(value, dict):
        supplied = value.get("answers", value)
        if not isinstance(supplied, dict): return False, len(entries), 0
        progress = merge_progress(SimpleNamespace(answers=supplied), solution, {})
        matched, expected = count_progress(progress, solution)
        return matched == expected and expected > 0, expected, matched
    if not isinstance(value, list): value = [value]
    matched = sum(isinstance(v, str) and v.strip().upper() == e["answer"] for v, e in zip(value, entries))
    return matched == len(entries) and len(value) == len(entries) and bool(entries), len(entries), matched


def preview(print_payload, play_payload, metadata):
    # Uses the generic library fallback; no hidden answer in preview metadata.
    return {"kind": "fallback", "label": "Spell It!", "icon": "Aa", "meta": f"{len(play_payload.get('entries', []))} entries"}


def collaboration(progress, action, solution):
    from copy import deepcopy
    result = deepcopy(progress)
    answers = dict(result.get('answers', {}))
    entries = solution['entries']
    editable = {f"{e['index']}:{p}" for e in entries for p in e['hidden'] if p not in ledger(answers, e)}
    kind = action['kind']
    if kind == 'patch':
        for key, value in action.get('changes', {}).items():
            if key not in editable or not re.fullmatch('[A-Z]?', value):
                raise ValueError('Letter is fixed or invalid')
            if value: answers[key] = value
            else: answers.pop(key, None)
        normalized = normalize_progress(SimpleNamespace(answers=answers), solution)['answers']
        if normalized != answers: raise ValueError('No remaining letter tile for that spelling')
    elif kind == 'hint':
        target = action.get('target') or str(next((i for i, entry in enumerate(entries) if state(entry, answers) != 'correct'), 0))
        bank = target.startswith('bank:')
        try: index = int(target.split(':')[-1])
        except ValueError: raise ValueError('Invalid entry')
        if not 0 <= index < len(entries): raise ValueError('Entry not found')
        entry = entries[index]
        if bank:
            if entry['settings']['letter_bank'] != 'hint_triggered': raise ValueError('No hint-triggered bank')
            answers[f'bank:{index}'] = '1'
        else:
            used = ledger(answers, entry)
            if len(used) >= entry['settings']['hint_limit']: raise ValueError('No letter hints remain')
            position = next((p for p in entry['hidden'] if p not in used and answers.get(f'{index}:{p}') != entry['answer'][p]), None)
            if position is None: raise ValueError('All missing letters are correct')
            answers[f'hint:{index}'] = ','.join(map(str, [*used, position]))
            answers[f'{index}:{position}'] = entry['answer'][position]
    elif kind != 'check':
        raise ValueError('Unsupported action')
    result['answers'] = normalize_progress(SimpleNamespace(answers=answers), solution)['answers']
    if kind == 'check': result['checked'] = True
    result['states'] = [state(e, result['answers']) for e in entries]
    result['letter_banks'] = [e['bank'] if e['settings']['letter_bank'] in ('exact', 'decoy') or result['answers'].get(f"bank:{e['index']}") == '1' else [] for e in entries]
    result['hints_remaining'] = [max(0, e['settings']['hint_limit'] - len(ledger(result['answers'], e))) for e in entries]
    return result


def core():
    from app import main
    return main


async def request_body(request, limit=64000):
    raw = await request.body()
    if len(raw) > limit:
        raise HTTPException(413, "Request too large")
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError):
        raise HTTPException(422, "Invalid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(422, "Expected a JSON object")
    return payload


def request_context(puzzle_id, request, db):
    user = core().require_api_user(request, db)
    require(user, "puzzles.play")
    puzzle = db.get(Puzzle, puzzle_id)
    if not puzzle or puzzle.puzzle_type != "spell_it":
        raise HTTPException(404, "Spell It puzzle not found")
    if not core().is_puzzle_type_enabled(db, "spell_it"):
        raise HTTPException(400, "Spell It is disabled")
    if not can_view(user, puzzle, play=True):
        raise HTTPException(403, "Puzzle access denied")
    if not getattr(user, "is_guest_link", False):
        db.scalar(select(User).where(User.id == user.id).with_for_update())
    progress = core().progress_record_for_user(db, puzzle, user, create=True)
    return user, puzzle, progress


def progress_response(puzzle, progress):
    answers = (progress.progress_payload or {}).get("answers", {})
    entries = puzzle.solution_payload["entries"]
    return {
        "answers": answers,
        "states": [state(entry, answers) for entry in entries],
        "letter_banks": [
            entry["bank"]
            if entry["settings"]["letter_bank"] in ("exact", "decoy")
            or answers.get(f"bank:{entry['index']}") == "1"
            else []
            for entry in entries
        ],
        "hints_remaining": [
            max(0, entry["settings"]["hint_limit"] - len(ledger(answers, entry)))
            for entry in entries
        ],
    }


@router.post("/api/spell-it/editor-preview", name="spell_it_preview")
async def editor_preview(request: Request, db=Depends(get_db)):
    core().require_api_user(request, db)
    if not core().is_puzzle_type_enabled(db, "spell_it"):
        raise HTTPException(400, "Spell It is disabled")
    payload = await request_body(request, 512000)
    try:
        built = manual(payload)
    except (ValueError, TypeError) as error:
        raise HTTPException(422, str(error))
    return {"play_payload": built.play_payload, "solution_payload": built.solution_payload}


@router.get("/api/puzzles/{puzzle_id}/spell-it/progress")
def read_spell_progress(puzzle_id: str, request: Request, db=Depends(get_db)):
    _, puzzle, progress = request_context(puzzle_id, request, db)
    return progress_response(puzzle, progress)


@router.post("/api/puzzles/{puzzle_id}/spell-it/attempts")
async def check_spell_entry(puzzle_id: str, request: Request, db=Depends(get_db)):
    payload = await request_body(request)
    user, puzzle, progress = request_context(puzzle_id, request, db)
    answers = payload.get("answers", {})
    if not isinstance(answers, dict):
        raise HTTPException(422, "Answers must be an object")
    before = dict(progress.progress_payload or {})
    progress.progress_payload = merge_progress(SimpleNamespace(answers=answers), puzzle.solution_payload, before)
    matched, expected = count_progress(progress.progress_payload, puzzle.solution_payload)
    if not getattr(user, "is_guest_link", False):
        db.add(PuzzleAttempt(
            puzzle_id=puzzle.id,
            user_id=user.id,
            answer=json.dumps(progress.progress_payload["answers"]),
            is_correct=matched == expected,
        ))
        record_puzzle_event(db, puzzle.id, user.id, "attempt", {
            "is_correct": matched == expected,
            "matched_count": matched,
            "expected_count": expected,
        })
        record_progress_transition(db, puzzle, user.id, core().get_puzzle_type(puzzle.puzzle_type), before, progress.progress_payload)
    db.commit()
    return {
        **progress_response(puzzle, progress),
        "completed": matched == expected,
        "matched_count": matched,
        "expected_count": expected,
    }


@router.post("/api/puzzles/{puzzle_id}/spell-it/hint")
async def spell_hint(puzzle_id: str, request: Request, db=Depends(get_db)):
    payload = await request_body(request)
    user, puzzle, progress = request_context(puzzle_id, request, db)
    index = payload.get("entry", 0)
    entries = puzzle.solution_payload["entries"]
    if type(index) is not int or not 0 <= index < len(entries):
        raise HTTPException(422, "Invalid entry")
    entry = entries[index]
    supplied = payload.get("answers", {})
    if not isinstance(supplied, dict):
        raise HTTPException(422, "Answers must be an object")
    normalized = merge_progress(SimpleNamespace(answers=supplied), puzzle.solution_payload, progress.progress_payload or {})
    answers = normalized["answers"]
    if payload.get("kind") == "bank":
        if entry["settings"]["letter_bank"] != "hint_triggered":
            raise HTTPException(400, "This entry has no hint-triggered bank")
        answers[f"bank:{index}"] = "1"
    else:
        used = ledger(answers, entry)
        if len(used) >= entry["settings"]["hint_limit"]:
            raise HTTPException(400, "No letter hints remain")
        positions = [
            position for position in entry["hidden"]
            if position not in used and answers.get(f"{index}:{position}") != entry["answer"][position]
        ]
        if not positions:
            raise HTTPException(400, "All missing letters are already correct")
        position = random.SystemRandom().choice(positions)
        answers[f"hint:{index}"] = ",".join(map(str, [*used, position]))
        answers[f"{index}:{position}"] = entry["answer"][position]
    progress.progress_payload = normalize_progress(SimpleNamespace(answers=answers), puzzle.solution_payload)
    if not getattr(user, "is_guest_link", False):
        record_puzzle_event(db, puzzle.id, user.id, "hint", {
            "target": f"entry:{index}:{payload.get('kind') or 'letter'}",
        })
    db.commit()
    return progress_response(puzzle, progress)


FIELDS = (
    GenerationField("spelling_difficulty", "Spelling difficulty", "select", "", options=({"value": "", "label": "Use puzzle difficulty"}, *tuple({"value": k, "label": k.replace('_', ' ').title()} for k in DIFFICULTIES))),
    GenerationField("mask_percent", "Hidden letters (%)", "number", "", minimum=1, maximum=100),
    GenerationField("preserve_edges", "Protect first and last letters", "select", "yes", options=({"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"})),
    GenerationField("letter_bank", "Letter bank", "select", "default", options=tuple({"value": k, "label": k.replace('_', ' ').title()} for k in BANK_MODES)),
    GenerationField("decoy_count", "Extra letters (Decoy bank)", "number", 3, minimum=0, maximum=20, enabled_when=(("letter_bank", "decoy"),)),
    GenerationField("hint_limit", "Letter hints per entry", "number", 1, minimum=0, maximum=20),
)
register_puzzle_type(PuzzleType(
    slug="spell_it", label="Spell It!", generator=generate, source_builder=build_source,
    answer_checker=check_answer, progress_normalizer=normalize_progress,
    progress_counter=count_progress, progress_merger=merge_progress,
    collaboration=collaboration, collaboration_value_limit=80,
    description="Reconstruct missing letters from definitions.",
    source_requirements=("word_bank",), theme_mode="word_bank",
    word_bank_required_fields=("word", "definition"),
    generation_fields=(
        GenerationField("mode", "Mode", "select", "single", options=({"value": "single", "label": "Single word"}, {"value": "series", "label": "Word series"})),
        GenerationField("entry_count", "Series length", "number", 5, minimum=2, maximum=30), *FIELDS,
    ),
    manual_editor_fields=(
        GenerationField("entries", "Entries", "textarea", '[{"answer":"ASTRONOMER","definition":"A person who studies stars and celestial objects."}]', required=True),
        *FIELDS, GenerationField("seed", "Mask seed", default="manual-spell-it"),
    ),
    manual_builder=manual, manual_editor_script="/plugins/spell_it/static/spell-it-editor.js?v=2",
    play_script="/plugins/spell_it/static/spell-it.js?v=2", router=router, preview_builder=preview,
    private_metadata_keys=("manual_editor_options",), supports_solution_reveal=False,
    print_layout=PrintLayout(slug="spell_it", sheet_class="print-layout-spell-it", instructions="Fill the missing letters."),
))
