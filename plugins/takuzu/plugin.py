"""Seeded Takuzu generation and uniqueness proofs using OR-Tools CP-SAT."""
import json
import random
import time
import uuid

from ortools.sat.python import cp_model

from app.puzzles import GeneratedPuzzle, GenerationField, PrintLayout, PuzzleType, register_puzzle_type


def whole_number(value, label):
    try:
        result = int(value)
    except (ValueError,TypeError,OverflowError):
        raise ValueError(f"{label} must be a whole number.")
    if type(value) is bool or (isinstance(value,float) and value != result):
        raise ValueError(f"{label} must be a whole number.")
    return result


def validate_grid(grid):
    if not isinstance(grid, list) or len(grid) not in (4, 6, 8, 10):
        raise ValueError("Takuzu size must be even, from 4 to 10.")
    n = len(grid)
    if any(not isinstance(row, list) or len(row) != n or any(type(v) is not int or v not in (0, 1) for v in row) for row in grid):
        raise ValueError("The solution must be a square grid of 0 and 1.")
    lines = grid + [[grid[y][x] for y in range(n)] for x in range(n)]
    if any(sum(line) != n // 2 or any(line[i] == line[i+1] == line[i+2] for i in range(n-2)) for line in lines):
        raise ValueError("Each line needs equal 0s and 1s and no three identical consecutive digits.")
    if len(set(map(tuple, grid))) != n or len(set(map(tuple, lines[n:]))) != n:
        raise ValueError("Rows must be distinct, and columns must be distinct.")


def model_for(n, givens=None, exclude=None):
    model = cp_model.CpModel()
    cells = [[model.new_bool_var(f"c{x}_{y}") for x in range(n)] for y in range(n)]
    codes = [[], []]
    for axis in range(2):
        for i in range(n):
            line = cells[i] if axis == 0 else [cells[y][i] for y in range(n)]
            model.add(sum(line) == n // 2)
            for k in range(n-2):
                model.add(sum(line[k:k+3]) >= 1)
                model.add(sum(line[k:k+3]) <= 2)
            code = model.new_int_var(0,2**n-1,f"line{axis}_{i}")
            model.add(code == sum(cell * 2**j for j,cell in enumerate(line)))
            codes[axis].append(code)
        model.add_all_different(codes[axis])
    for key,value in (givens or {}).items():
        x,y = map(int,key.split(','))
        model.add(cells[y][x] == int(value))
    if exclude is not None:
        model.add_bool_or([cells[y][x].Not() if exclude[y][x] else cells[y][x] for y in range(n) for x in range(n)])
    return model,cells


def solved_grid(n, rng):
    model,cells = model_for(n)
    coordinates = [(x,y) for y in range(n) for x in range(n)]
    rng.shuffle(coordinates)
    for x,y in coordinates:
        model.add_decision_strategy([cells[y][x]],cp_model.CHOOSE_FIRST,
                                   cp_model.SELECT_MIN_VALUE if rng.randrange(2) else cp_model.SELECT_MAX_VALUE)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.search_branching = cp_model.FIXED_SEARCH
    solver.parameters.max_time_in_seconds = 3
    solver.parameters.max_deterministic_time = 0.5
    if solver.solve(model) not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        raise ValueError("Could not generate a Takuzu in time. Try another seed or a smaller grid.")
    return [[solver.value(cell) for cell in row] for row in cells]


def unique_givens(grid, rng, initial):
    n = len(grid)
    coordinates = [(x,y) for y in range(n) for x in range(n)]
    rng.shuffle(coordinates)
    givens = {f'{x},{y}':str(grid[y][x]) for x,y in coordinates[:initial]}
    model,cells = model_for(n,givens,exclude=grid)
    deadline = time.monotonic()+10
    while time.monotonic() < deadline:
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.max_time_in_seconds = min(2,max(0.01,deadline-time.monotonic()))
        result = solver.solve(model)
        if result == cp_model.INFEASIBLE:
            return givens
        if result not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            break
        differences = [(x,y) for x,y in coordinates if solver.value(cells[y][x]) != grid[y][x]]
        x,y = rng.choice(differences)
        givens[f'{x},{y}'] = str(grid[y][x])
        model.add(cells[y][x] == grid[y][x])
    raise ValueError("Could not prove a unique Takuzu in time. Try more starter cells or a smaller grid.")


def answers_from(value, solution):
    if isinstance(value,str):
        try: value = json.loads(value)
        except ValueError: return {}
    if not isinstance(value,dict): return {}
    value = value.get('answers',value)
    if not isinstance(value,dict): return {}
    n = len(solution.get('grid',[]))
    valid = {f'{x},{y}' for y in range(n) for x in range(n)}
    return {key:str(v) for key,v in value.items() if key in valid and type(v) in (str,int) and str(v) in ('0','1')}


def normalize_progress(payload, solution):
    answers = answers_from(getattr(payload,'answers',{}) if payload is not None else {},solution)
    return {'answers':{k:v for k,v in answers.items() if k not in solution.get('givens',{})}}


def count_progress(progress, solution):
    answers = {**answers_from(progress,solution),**solution.get('givens',{})}
    grid = solution.get('grid',[])
    total = len(grid)**2
    complete = total > 0 and all(answers.get(f'{x},{y}') == str(v) for y,row in enumerate(grid) for x,v in enumerate(row))
    filled = sum(1 for y,row in enumerate(grid) for x,_v in enumerate(row) if answers.get(f'{x},{y}') in ('0','1'))
    return (total if complete else min(filled,max(0,total-1))),total


def check_answer(answer, solution):
    matched,total = count_progress(answer,solution)
    return total > 0 and matched == total,total,matched


def make_puzzle(grid, difficulty, seed, options):
    validate_grid(grid)
    n = len(grid)
    raw = options.get('given_count')
    initial = whole_number(raw,'Starter cells') if raw is not None and raw != '' else round(n*n*{'easy':0.5,'medium':0.35,'hard':0.2}.get(difficulty,0.35))
    if not 0 <= initial < n*n: raise ValueError("Starter cells must be between 0 and the cell count minus one.")
    givens = unique_givens(grid,random.Random(seed),initial)
    auto = str(options.get('auto_confirm_lines','yes')).lower() in ('yes','true','1','on')
    payload = {'kind':'takuzu','size':n,'givens':givens,'settings':{'grid_size':n,'auto_confirm_lines':auto,'uniqueness_verified':True}}
    return GeneratedPuzzle(title=f'{n}x{n} Takuzu',
        prompt='Fill every cell with 0 or 1. Each row and column needs equal numbers of each digit, no three identical digits together, and no duplicate rows or columns.',
        print_payload=payload,play_payload=payload,solution_payload={'grid':grid,'givens':givens},
        hints=['Two equal digits together force the next digit to be different.',
               'Equal digits separated by one blank force the middle digit to be different.',
               'When a line has half its cells filled with one digit, its remaining blanks must contain the other.',
               'Compare nearly complete lines: two rows, or two columns, cannot be identical.'],
        metadata={'generator':'local.takuzu.v1','seed':seed,'uniqueness_verified':True,'givens':len(givens),'generation_options':{**options,'grid_size':n}})


def generate(theme, difficulty, source_data=None, seed=None, generation_options=None):
    options = generation_options or {}
    n = whole_number(options.get('grid_size') or 6,'Grid size')
    if n not in (4,6,8,10): raise ValueError("Takuzu size must be even, from 4 to 10.")
    seed = seed or uuid.uuid4().hex
    return make_puzzle(solved_grid(n,random.Random(seed)),difficulty,seed,options)


def build_manual(options):
    try: grid = json.loads(options.get('solution_grid','')) if isinstance(options.get('solution_grid',''),str) else options['solution_grid']
    except (ValueError,KeyError): raise ValueError("Solution grid must be JSON rows of 0 and 1.")
    return make_puzzle(grid,'custom',str(options.get('seed') or uuid.uuid4().hex),options)


starter_field = GenerationField('given_count','Starter cells','number','',minimum=0,maximum=99,
    help_text='Leave blank for difficulty defaults. Additional cells may be added to guarantee one solution.')
confirm_field = GenerationField('auto_confirm_lines','Auto-confirm completed lines','select','yes',options=(
    {'value':'yes','label':'On'},{'value':'no','label':'Off'}))

from app.group_actions import cell_collaboration

register_puzzle_type(PuzzleType(slug='takuzu',label='Takuzu / Binairo',description='Balanced binary logic grids with distinct rows and columns.',
    collaboration=cell_collaboration(normalize_progress),
    generator=generate,source_builder=lambda *_:{},answer_checker=check_answer,progress_normalizer=normalize_progress,
    progress_counter=count_progress,theme_mode='none',print_layout=PrintLayout(slug='takuzu',sheet_class='print-layout-takuzu'),
    play_script='/plugins/takuzu/static/takuzu.js?v=6',
    **({'supports_offline':True,'offline_progress_fields':('answers',),'offline_validation':'local_rules','offline_notes':'Completed grids can be checked against Takuzu rules offline; the server confirms completion after sync.'} if 'supports_offline' in PuzzleType.__dataclass_fields__ else {}),
    generation_fields=(GenerationField('grid_size','Grid size','select','6',options=tuple({'value':str(n),'label':f'{n}x{n}'} for n in (4,6,8,10))),starter_field,confirm_field),
    manual_builder=build_manual,manual_editor_script='/plugins/takuzu/static/takuzu-editor.js?v=1',
    manual_editor_fields=(GenerationField('solution_grid','Solution grid','textarea',required=True,help_text='A valid, even square grid of 0 and 1, from 4x4 to 10x10.'),starter_field,confirm_field)))
