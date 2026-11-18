(function () {
  const root = document.querySelector('.sudoku-play');
  if (!root) return;
  const inputs = [...root.querySelectorAll('.sudoku-cell input[data-key]')];
  const status = document.getElementById('sudoku-status');
  const progressUrl = root.dataset.progressUrl;
  const size = Number(root.dataset.size || 9);
  const boxRows = Number(root.dataset.boxRows || 3), boxCols = Number(root.dataset.boxCols || 3);
  const remote = window.PuzzaryGroup || window.PuzzarySolo;
  let saveTimer = null;
  const parse = (value, fallback) => { try { return JSON.parse(value || ''); } catch (_) { return fallback; } };
  const progressive = parse(root.dataset.progressive, {});
  const progressiveEnabled = Boolean(progressive.enabled);
  const unitList = document.getElementById('sudoku-unit-list');
  const unitSummary = document.getElementById('sudoku-progressive-summary');
  let completedUnits = new Set(parse(root.dataset.progressiveCompleted, []));
  let unitAuthors = parse(root.dataset.progressiveAuthors, {});
  let activeUnit = '';
  let progressReady = false;
  const ruleUnits = [];
  const progressiveUnits = [];

  function cellsWhere(predicate) {
    return inputs.filter(input => { const [x,y] = input.dataset.key.split(',').map(Number); return predicate(x,y); });
  }
  for (let n = 0; n < size; n++) {
    ruleUnits.push(cellsWhere((_x,y) => y === n));
    ruleUnits.push(cellsWhere((x,_y) => x === n));
  }
  if (progressive.units?.includes('row')) for (let n = 0; n < size; n++) {
    progressiveUnits.push({id:`row:${n+1}`,label:`Row ${n+1}`,keys:cellsWhere((_x,y) => y === n).map(input => input.dataset.key)});
  }
  if (progressive.units?.includes('column')) for (let n = 0; n < size; n++) {
    progressiveUnits.push({id:`column:${n+1}`,label:`Column ${n+1}`,keys:cellsWhere((x,_y) => x === n).map(input => input.dataset.key)});
  }
  let boxNumber = 0;
  for (let y = 0; y < size; y += boxRows) for (let x = 0; x < size; x += boxCols) {
    boxNumber += 1;
    const cells = cellsWhere((cx,cy) => cx >= x && cx < x+boxCols && cy >= y && cy < y+boxRows);
    ruleUnits.push(cells);
    if (progressive.units?.includes('box')) progressiveUnits.push({id:`box:${boxNumber}`,label:`Box ${boxNumber}`,keys:cells.map(input => input.dataset.key)});
  }

  const unitNodes = new Map();
  if (unitList) progressiveUnits.forEach(unit => {
    const item = document.createElement('span');
    item.className = 'sudoku-unit'; item.dataset.unit = unit.id; item.setAttribute('role','listitem');
    unitList.append(item); unitNodes.set(unit.id,item);
  });
  function answers() { return Object.fromEntries(inputs.filter(i => !i.disabled && i.value.trim()).map(i => [i.dataset.key,i.value.trim()])); }
  function conflicts() {
    const bad = new Set();
    ruleUnits.forEach(unit => {
      const seen = new Map();
      unit.forEach(input => { const value=input.value.trim(); if (!value) return; if (seen.has(value)) { bad.add(input.dataset.key); bad.add(seen.get(value)); } else seen.set(value,input.dataset.key); });
    });
    return bad;
  }
  function unitById(id) { return progressiveUnits.find(unit => unit.id === id); }
  function nextActive(state = {}) {
    if (progressive.order === 'sequence') return state.progressive_active || (progressive.sequence || []).find(id => !completedUnits.has(id)) || '';
    if (activeUnit && !completedUnits.has(activeUnit)) return activeUnit;
    return progressiveUnits.find(unit => !completedUnits.has(unit.id))?.id || '';
  }
  function renderProgress(state = {}, snapshot = null, initial = false) {
    if (!progressiveEnabled) return [];
    const previous = new Set(completedUnits);
    completedUnits = new Set(state.progressive_completed || []);
    unitAuthors = state.progressive_authors || {};
    activeUnit = nextActive(state);
    const active = unitById(activeUnit);
    const lockedKeys = new Set(progressive.lock_completed ? progressiveUnits.filter(unit => completedUnits.has(unit.id)).flatMap(unit => unit.keys) : []);
    inputs.forEach(input => {
      const cell = input.closest('.sudoku-cell');
      const completedHere = progressiveUnits.some(unit => completedUnits.has(unit.id) && unit.keys.includes(input.dataset.key));
      cell.classList.toggle('progressive-complete', Boolean(progressive.mark_completed && completedHere));
      cell.classList.toggle('progressive-active', Boolean(active?.keys.includes(input.dataset.key)));
      if (!input.disabled) input.readOnly = lockedKeys.has(input.dataset.key);
    });
    progressiveUnits.forEach(unit => {
      const item = unitNodes.get(unit.id); if (!item) return;
      const done = completedUnits.has(unit.id), current = unit.id === activeUnit && !done;
      const author = snapshot?.members?.find(member => member.user_id === unitAuthors[unit.id]);
      item.classList.toggle('complete',done); item.classList.toggle('active',current);
      item.toggleAttribute('aria-current',current);
      item.textContent = `${unit.label} — ${done ? `complete${author ? ` by ${author.name}` : ''}` : current ? 'active' : 'incomplete'}`;
      if (done && unitAuthors[unit.id] !== undefined && remote?.color) item.style.setProperty('--unit-color',remote.color(unitAuthors[unit.id]));
      else item.style.removeProperty('--unit-color');
    });
    if (unitSummary) unitSummary.textContent = `${completedUnits.size} of ${progressiveUnits.length} units complete${active ? `. ${active.label} is active.` : '.'}`;
    const newlyCompleted = [...completedUnits].filter(id => !previous.has(id));
    if (progressReady && newlyCompleted.length && !state.completed) window.PuzzarySounds?.progress();
    if (!initial) progressReady = true;
    return newlyCompleted.map(id => unitById(id)?.label).filter(Boolean);
  }
  async function save() {
    if (window.PuzzaryGroup) { window.PuzzaryGroup.save(); return; }
    if (progressiveEnabled) { await remote?.action('patch'); return; }
    fetch(progressUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers:answers()})}).catch(() => { status.textContent='Progress could not be saved.'; });
  }
  function queueSave() {
    if (window.PuzzaryGroup) return window.PuzzaryGroup.save();
    clearTimeout(saveTimer); saveTimer=setTimeout(save,progressiveEnabled ? 180 : 250);
  }
  function apply(state, snapshot) {
    inputs.forEach(input => {
      if (!input.disabled) input.value = state.answers?.[input.dataset.key] || '';
      input.closest('.sudoku-cell').classList.remove('correct','incorrect');
      if (state.revealed) input.closest('.sudoku-cell').classList.add('correct');
    });
    const newlyCompleted = renderProgress(state,snapshot);
    const bad=conflicts(); inputs.forEach(input => input.closest('.sudoku-cell').classList.toggle('incorrect',bad.has(input.dataset.key)));
    if (state.revealed) status.textContent='Solution revealed. Reset the puzzle to start over.';
    else if (state.completed) { status.textContent='Sudoku complete.'; window.PuzzaryCelebrate?.complete(); }
    else if (newlyCompleted.length) status.textContent=`${newlyCompleted.join(', ')} complete. ${completedUnits.size} of ${progressiveUnits.length} units finished.`;
    else if (state.checked) status.textContent=bad.size ? 'Resolve the highlighted row, column, or box conflicts.' : 'No rule conflicts found. Complete every cell to finish.';
  }
  remote?.register({read:answers,apply});
  renderProgress({progressive_completed:[...completedUnits],progressive_authors:unitAuthors},null,true);
  progressReady = true;
  function at(x,y) { return inputs.find(input => input.dataset.key === `${x},${y}`); }
  function move(input,dx,dy) { let [x,y]=input.dataset.key.split(',').map(Number); do { x+=dx;y+=dy; const next=at(x,y); if(next&&!next.disabled&&!next.readOnly){next.focus();next.select();return;} } while(x>=0&&x<size&&y>=0&&y<size); }
  function set(input,value) { if(input.disabled||input.readOnly)return; input.value=String(value).replace(new RegExp(`[^1-${size}]`,'g'),'').slice(0,1); input.closest('.sudoku-cell').classList.remove('correct','incorrect'); queueSave(); }
  inputs.forEach(input => {
    input.addEventListener('focus',() => { if (progressiveEnabled && progressive.order !== 'sequence') { activeUnit = progressiveUnits.find(unit => !completedUnits.has(unit.id) && unit.keys.includes(input.dataset.key))?.id || activeUnit; renderProgress({progressive_completed:[...completedUnits],progressive_authors:unitAuthors},null,true); } });
    input.addEventListener('input',()=>{set(input,input.value);if(input.value)move(input,1,0);});
    input.addEventListener('keydown',event=>{ if(event.altKey||event.ctrlKey||event.metaKey)return; if(new RegExp(`^[1-${size}]$`).test(event.key)){event.preventDefault();set(input,event.key);if(!input.readOnly)move(input,1,0);} else if(event.key==='Backspace'){event.preventDefault();if(input.value)set(input,'');else move(input,-1,0);} else if(event.key==='Delete'||event.key==='0'){event.preventDefault();set(input,'');} else if(event.key==='ArrowRight'){event.preventDefault();move(input,1,0);} else if(event.key==='ArrowLeft'){event.preventDefault();move(input,-1,0);} else if(event.key==='ArrowDown'){event.preventDefault();move(input,0,1);} else if(event.key==='ArrowUp'){event.preventDefault();move(input,0,-1);} });
  });
  document.getElementById('sudoku-check')?.addEventListener('click',()=>root.dataset.checkMode==='none' ? status.textContent='Checking is off for this puzzle.' : remote?.action('check'));
  document.getElementById('sudoku-check-units')?.addEventListener('click',()=>remote?.action('progressive_check'));
  document.getElementById('sudoku-clear')?.addEventListener('click',()=>{inputs.forEach(i=>{if(!i.disabled&&!i.readOnly)i.value='';i.closest('.sudoku-cell').classList.remove('correct','incorrect');});status.textContent='Grid cleared.';save();});
  document.getElementById('reveal-solution')?.addEventListener('click',()=>remote?.action('reveal'));
})();
