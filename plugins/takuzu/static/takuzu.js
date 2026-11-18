(() => {
  const root=document.querySelector('.takuzu-play');if(!root)return;
  const cells=[...root.querySelectorAll('button.takuzu-cell')],saved=JSON.parse(root.dataset.answers||'{}'),status=root.querySelector('.takuzu-status'),remote=window.PuzzaryGroup||window.PuzzarySolo;
  let mode='cycle',dragging=false,brush='',timer,saving=false,dirty=false;
  function paint(cell,value){if(!cell||cell.disabled)return;cell.dataset.value=value;cell.textContent=value;cell.classList.remove('incorrect');const[x,y]=cell.dataset.key.split(',').map(Number);cell.setAttribute('aria-label',`Row ${y+1}, column ${x+1}: ${value||'blank'}`);}
  cells.forEach(c=>{if(['0','1'].includes(saved[c.dataset.key]))paint(c,saved[c.dataset.key]);});
  function answers(){return Object.fromEntries(cells.filter(c=>!c.disabled&&c.dataset.value!=='').map(c=>[c.dataset.key,c.dataset.value]));}
  async function save(){if(window.PuzzaryGroup)return window.PuzzaryGroup.save();dirty=true;if(saving)return;saving=true;while(dirty){dirty=false;try{const r=await fetch(root.dataset.progressUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers:answers()})});if(!r.ok)throw new Error();}catch(_){status.textContent='Progress could not be saved. Make another mark to retry.';break;}}saving=false;}
  function queueSave(){if(window.PuzzaryGroup)return window.PuzzaryGroup.save();clearTimeout(timer);timer=setTimeout(save,200);}
  function apply(state){cells.forEach(c=>{const value=state.answers?.[c.dataset.key]||'';if(!c.disabled&&c.dataset.value!==value)paint(c,value);c.classList.remove('incorrect');});if(state.revealed)status.textContent='Solution revealed.';else if(state.completed){status.textContent='Takuzu complete.';window.PuzzaryCelebrate?.complete();}else if(state.checked)status.textContent='The grid is not complete and valid yet.';}
  remote?.register({read:answers,apply});
  root.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{mode=button.dataset.mode;root.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));}));
  root.addEventListener('pointerdown',event=>{const cell=event.target.closest('button.takuzu-cell');if(!cell||cell.disabled||event.button!==0)return;event.preventDefault();cell.focus();dragging=true;brush=mode==='cycle'?(cell.dataset.value===''?'0':cell.dataset.value==='0'?'1':''):mode;paint(cell,brush);root.setPointerCapture(event.pointerId);queueSave();});
  root.addEventListener('pointermove',event=>{if(!dragging)return;const cell=document.elementFromPoint(event.clientX,event.clientY)?.closest('button.takuzu-cell');if(cell&&root.contains(cell)){paint(cell,brush);queueSave();}});
  const finish=()=>{if(dragging){dragging=false;queueSave();}};['pointerup','pointercancel','lostpointercapture'].forEach(name=>root.addEventListener(name,finish));
  root.addEventListener('keydown',event=>{const cell=event.target.closest('button.takuzu-cell');if(!cell||event.altKey||event.ctrlKey||event.metaKey)return;const[x,y]=cell.dataset.key.split(',').map(Number),moves={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};if(moves[event.key]){event.preventDefault();const[dx,dy]=moves[event.key];cells.find(c=>c.dataset.key===`${x+dx},${y+dy}`)?.focus();}else if(['0','1',' ','Enter','Delete','Backspace'].includes(event.key)){event.preventDefault();const value=['0','1'].includes(event.key)?event.key:['Delete','Backspace'].includes(event.key)?'':mode==='cycle'?(cell.dataset.value===''?'0':cell.dataset.value==='0'?'1':''):mode;paint(cell,value);queueSave();}});
  root.querySelector('.takuzu-check')?.addEventListener('click',()=>remote?.action('check'));
  root.querySelector('.takuzu-clear')?.addEventListener('click',()=>{cells.forEach(c=>paint(c,''));status.textContent='Grid cleared.';queueSave();});
  root.querySelector('.takuzu-hint')?.addEventListener('click',()=>remote?.action('hint'));
  document.getElementById('reveal-solution')?.addEventListener('click',()=>remote?.action('reveal'));
})();
