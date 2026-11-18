window.PuzzaryManualEditors = window.PuzzaryManualEditors || {};
const takuzuEditorStyle = document.createElement('style');
takuzuEditorStyle.textContent = '.level-editor[data-level-editor="takuzu"]{grid-template-columns:minmax(120px,160px) minmax(0,1fr);min-width:0;} .level-editor[data-level-editor="takuzu"] .level-canvas{min-width:0;} .level-editor[data-level-editor="takuzu"] .level-properties{display:none;} @media(max-width:700px){.level-editor[data-level-editor="takuzu"]{grid-template-columns:1fr;}}';
document.head.append(takuzuEditorStyle);
window.PuzzaryManualEditors.takuzu = (form,parts) => {
  const source = form.querySelector('[name="manual_solution_grid"]');
  if (!source) return;
  source.closest('label')?.classList.add('builder-source-hidden');
  let grid;
  try { grid = JSON.parse(source.value); } catch (_) { grid = null; }
  if (!Array.isArray(grid) || ![4,6,8,10].includes(grid.length)) grid = [[0,0,1,1],[0,1,0,1],[1,0,1,0],[1,1,0,0]];
  let mode = 1, drawing = false;
  const size = document.createElement('select');
  [4,6,8,10].forEach(n => size.add(new Option(`${n}x${n}`,String(n)))); size.value = grid.length;
  const label = document.createElement('label'); label.textContent = 'Grid size'; label.append(size); parts.toolbar.append(label);
  const status = document.createElement('p'); status.setAttribute('role','status'); parts.canvas.append(status);
  const button = (text,action,title=text) => { const b=document.createElement('button'); b.type='button'; b.className='ghost-button'; b.textContent=text; b.title=title; b.addEventListener('click',action); parts.toolbar.append(b); return b; };
  button('Resize',() => { const n=Number(size.value); grid=Array.from({length:n},(_,y) => Array.from({length:n},(_,x) => grid[y]?.[x] || 0)); draw(); });
  const zero=button('0',() => { mode=0; updateMode(); },'Paint zero');
  const one=button('1',() => { mode=1; updateMode(); },'Paint one');
  function updateMode() { zero.setAttribute('aria-pressed',String(mode === 0)); one.setAttribute('aria-pressed',String(mode === 1)); }
  button('Invert',() => { grid=grid.map(row => row.map(v => 1-v)); draw(); });
  function sync() {
    source.value=JSON.stringify(grid);
    const n=grid.length, columns=Array.from({length:n},(_,x) => grid.map(row => row[x]));
    const lines=[...grid,...columns];
    const invalid=lines.some(line => line.reduce((a,b) => a+b,0) !== n/2 || line.some((v,i) => i<n-2 && v===line[i+1] && v===line[i+2]));
    const duplicates=new Set(grid.map(row => row.join(''))).size!==n || new Set(columns.map(row => row.join(''))).size!==n;
    status.textContent=invalid || duplicates ? 'Solution has rule violations.' : 'Valid Takuzu solution.';
  }
  function paint(cell) { if(!cell) return; const [x,y]=cell.dataset.key.split(',').map(Number); grid[y][x]=mode; cell.textContent=mode; sync(); }
  function draw() {
    parts.canvas.replaceChildren(status);
    const board=document.createElement('div'); board.style.cssText=`display:grid;grid-template-columns:repeat(${grid.length},minmax(0,1fr));width:100%;max-width:520px;border:2px solid #222;touch-action:none;`;
    grid.forEach((row,y) => row.forEach((v,x) => {
      const cell=document.createElement('button'); cell.type='button'; cell.dataset.key=`${x},${y}`; cell.textContent=v;
      cell.setAttribute('aria-label',`Row ${y+1}, column ${x+1}`);
      cell.style.cssText='aspect-ratio:1;padding:0;min-width:0;border:1px solid #777;border-radius:0;background:white;color:#111;font-size:20px;';
      cell.addEventListener('click',e => { if(e.detail===0) { mode=grid[y][x] ? 0 : 1; updateMode(); paint(cell); } }); board.append(cell);
    }));
    board.addEventListener('pointerdown',e => { const c=e.target.closest('[data-key]'); if(!c) return; e.preventDefault(); drawing=true; board.setPointerCapture(e.pointerId); paint(c); });
    board.addEventListener('pointermove',e => { const c=document.elementFromPoint(e.clientX,e.clientY)?.closest('[data-key]'); if(drawing && c && board.contains(c)) paint(c); });
    ['pointerup','pointercancel','lostpointercapture'].forEach(name => board.addEventListener(name,() => {drawing=false;}));
    parts.canvas.append(board); sync();
  }
  updateMode(); draw();
};
