window.PuzzaryManualEditors = window.PuzzaryManualEditors || {};
const nonogramEditorStyle = document.createElement('style');
nonogramEditorStyle.textContent = '.level-editor[data-level-editor="nonogram"] {grid-template-columns:minmax(120px,160px) minmax(0,1fr);min-width:0;} .level-editor[data-level-editor="nonogram"] .level-canvas {min-width:0;} .level-editor[data-level-editor="nonogram"] .level-properties {display:none;} @media(max-width:700px){.level-editor[data-level-editor="nonogram"]{grid-template-columns:1fr;}}';
document.head.append(nonogramEditorStyle);
window.PuzzaryManualEditors.nonogram = (form, parts) => {
  const source = form.querySelector('[name="manual_solution_grid"]');
  if (!source) return;
  source.closest('label')?.classList.add('builder-source-hidden');
  let picture;
  try { picture = JSON.parse(source.value); } catch (_) { picture = null; }
  if (!Array.isArray(picture) || picture.length < 5 || picture.length > 15) picture = Array.from({length:10}, () => Array(10).fill(0));
  let mode = 1, drawing = false, brush = 1;
  const size = document.createElement('input');
  size.type = 'number'; size.min = 5; size.max = 15; size.value = picture.length;
  const label = document.createElement('label'); label.textContent = 'Grid size'; label.append(size);
  parts.toolbar.append(label);
  const makeButton = (text, action) => {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = text; b.className = 'ghost-button'; b.addEventListener('click', action); parts.toolbar.append(b); return b;
  };
  makeButton('Resize', () => {
    const n = Math.max(5, Math.min(15, Number(size.value) || 10));
    picture = Array.from({length:n}, (_,y) => Array.from({length:n}, (_,x) => picture[y]?.[x] || 0));
    draw();
  });
  const fill = makeButton('Fill', () => { mode = 1; updateMode(); });
  const erase = makeButton('Erase', () => { mode = 0; updateMode(); });
  function updateMode() { fill.setAttribute('aria-pressed', mode === 1); erase.setAttribute('aria-pressed', mode === 0); }
  makeButton('Clear', () => { picture = picture.map(row => row.map(() => 0)); draw(); });
  function sync() { source.value = JSON.stringify(picture); }
  function paint(cell) {
    if (!cell) return;
    const [x,y] = cell.dataset.key.split(',').map(Number);
    picture[y][x] = brush;
    cell.style.background = brush ? '#222' : '#fff'; sync();
  }
  function draw() {
    parts.canvas.replaceChildren();
    const grid = document.createElement('div');
    grid.style.cssText = `display:grid;grid-template-columns:repeat(${picture.length},minmax(0,1fr));width:100%;max-width:600px;border:2px solid #222;touch-action:none;`;
    for (let y=0; y<picture.length; y++) for (let x=0; x<picture.length; x++) {
      const cell = document.createElement('button'); cell.type='button'; cell.dataset.key=`${x},${y}`;
      cell.setAttribute('aria-label',`Row ${y+1}, column ${x+1}`);
      cell.style.cssText=`aspect-ratio:1;padding:0;min-width:0;border:1px solid #777;border-radius:0;background:${picture[y][x] ? '#222' : '#fff'};`;
      cell.addEventListener('click', e => { if (e.detail === 0) { brush = picture[y][x] ? 0 : 1; paint(cell); } });
      grid.append(cell);
    }
    grid.addEventListener('pointerdown', e => { const c=e.target.closest('[data-key]'); if(!c) return; e.preventDefault(); drawing=true; brush=mode; grid.setPointerCapture(e.pointerId); paint(c); });
    grid.addEventListener('pointermove', e => { const c=document.elementFromPoint(e.clientX,e.clientY)?.closest('[data-key]'); if(drawing && c && grid.contains(c)) paint(c); });
    ['pointerup','pointercancel','lostpointercapture'].forEach(event => grid.addEventListener(event, () => {drawing=false;}));
    parts.canvas.append(grid); sync();
  }
  updateMode(); draw();
};
