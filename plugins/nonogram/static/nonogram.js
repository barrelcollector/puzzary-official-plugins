(() => {
  const root=document.querySelector('.nonogram-play'); if(!root)return;
  const cells=[...root.querySelectorAll('button.nonogram-cell')], status=root.querySelector('.nonogram-status'), saved=JSON.parse(root.dataset.answers||'{}'), remote=window.PuzzaryGroup||window.PuzzarySolo;
  let mode='1',brush='',protectedValue=null,dragging=false,timer,saving=false,dirty=false;
  function paint(cell,value,preserve=null){if(!cell||cell.disabled||preserve!==null&&cell.dataset.value===preserve)return;cell.dataset.value=value;cell.textContent=value==='0'?'X':'';cell.classList.remove('incorrect');cell.setAttribute('aria-label',`${cell.dataset.key}: ${value==='1'?'filled':value==='0'?'empty':'unmarked'}`);}
  function answers(){return Object.fromEntries(cells.filter(c=>!c.disabled&&c.dataset.value!=='').map(c=>[c.dataset.key,c.dataset.value]));}
  async function save(){if(window.PuzzaryGroup)return window.PuzzaryGroup.save();dirty=true;if(saving)return;saving=true;while(dirty){dirty=false;try{const r=await fetch(root.dataset.progressUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers:answers()})});if(!r.ok)throw new Error();}catch(_){status.textContent='Progress could not be saved. Make another mark to retry.';break;}}saving=false;}
  function queueSave(){if(window.PuzzaryGroup)return window.PuzzaryGroup.save();clearTimeout(timer);timer=setTimeout(save,200);}
  function apply(state){cells.forEach(cell=>{const value=state.answers?.[cell.dataset.key]||'';if(!cell.disabled&&cell.dataset.value!==value)paint(cell,value);cell.classList.remove('incorrect');});if(state.revealed)status.textContent='Solution revealed.';else if(state.completed){status.textContent='Nonogram complete.';window.PuzzaryCelebrate?.complete();}else if(state.checked)status.textContent='The picture is not complete yet.';}
  remote?.register({read:answers,apply});
  cells.forEach(c=>{if(!c.disabled&&['0','1'].includes(saved[c.dataset.key]))paint(c,saved[c.dataset.key]);});
  root.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{mode=button.dataset.mode;root.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));}));
  root.addEventListener('pointerdown',event=>{const cell=event.target.closest('button.nonogram-cell');if(!cell||cell.disabled||event.button===1)return;event.preventDefault();cell.focus();dragging=true;const chosen=event.button===2?'0':mode;protectedValue=chosen==='1'?'0':chosen==='0'?'1':null;brush=cell.dataset.value===chosen?'':chosen;paint(cell,brush,protectedValue);root.setPointerCapture(event.pointerId);queueSave();});
  root.addEventListener('pointermove',event=>{if(!dragging)return;const cell=document.elementFromPoint(event.clientX,event.clientY)?.closest('button.nonogram-cell');if(cell&&root.contains(cell)){paint(cell,brush,protectedValue);queueSave();}});
  const finish=()=>{if(dragging){dragging=false;queueSave();}};['pointerup','pointercancel','lostpointercapture'].forEach(name=>root.addEventListener(name,finish));
  root.addEventListener('contextmenu',event=>{if(event.target.closest('.nonogram-cell'))event.preventDefault();});
  root.addEventListener('keydown',event=>{const cell=event.target.closest('button.nonogram-cell');if(!cell)return;const[x,y]=cell.dataset.key.split(',').map(Number),moves={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};if(moves[event.key]){event.preventDefault();const[dx,dy]=moves[event.key];cells.find(c=>c.dataset.key===`${x+dx},${y+dy}`)?.focus();}else if([' ','Enter','x','X','Delete','Backspace'].includes(event.key)){event.preventDefault();const value=/x/i.test(event.key)?'0':['Delete','Backspace'].includes(event.key)?'':mode;paint(cell,cell.dataset.value===value?'':value,value==='1'?'0':value==='0'?'1':null);queueSave();}});
  root.querySelector('.nonogram-check')?.addEventListener('click',()=>remote?.action('check'));
  root.querySelector('.nonogram-clear')?.addEventListener('click',()=>{cells.forEach(c=>paint(c,''));status.textContent='Grid cleared.';queueSave();});
  document.getElementById('reveal-solution')?.addEventListener('click',()=>remote?.action('reveal'));
})();
