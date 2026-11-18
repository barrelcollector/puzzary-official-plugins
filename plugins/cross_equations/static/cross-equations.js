(function () {
  const root=document.querySelector('.cross-equations-play'); if(!root)return;
  const inputs=[...root.querySelectorAll('.number-cell input[data-key]')], status=document.getElementById('cross-equations-status');
  const remote=window.PuzzaryGroup||window.PuzzarySolo, progressUrl=root.dataset.progressUrl, valueMax=Number(root.dataset.valueMax||9), gridSize=Math.max(3,Number(root.dataset.gridSize||3)), maxCoord=(gridSize-1)*2;
  let saveTimer=null;
  function answers(){return Object.fromEntries(inputs.filter(i=>!i.disabled&&/^-?\d+$/.test(i.value.trim())).map(i=>[i.dataset.key,i.value.trim()]));}
  function save(){if(window.PuzzaryGroup)return window.PuzzaryGroup.save();fetch(progressUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers:answers()})}).catch(()=>status.textContent='Progress could not be saved.');}
  function queueSave(){if(window.PuzzaryGroup)return window.PuzzaryGroup.save();clearTimeout(saveTimer);saveTimer=setTimeout(save,250);}
  function apply(state){inputs.forEach(i=>{if(!i.disabled)i.value=state.answers?.[i.dataset.key]||'';i.closest('.number-cell').classList.toggle('correct',!!state.revealed);i.closest('.number-cell').classList.remove('incorrect');});if(state.revealed)status.textContent='Solution revealed. Reset the puzzle to start over.';else if(state.completed){status.textContent='Cross Equations complete.';window.PuzzaryCelebrate?.complete();}else if(state.checked)status.textContent='The equations are not all satisfied yet.';}
  remote?.register({read:answers,apply});
  const at=key=>inputs.find(i=>i.dataset.key===key);
  function move(input,dx,dy){let[x,y]=input.dataset.key.split(',').map(Number);do{x+=dx*2;y+=dy*2;const next=at(`${x},${y}`);if(next&&!next.disabled){next.focus();next.select();return;}}while(x>=0&&x<=maxCoord&&y>=0&&y<=maxCoord);}
  function set(input,value){if(input.disabled)return;let text=String(value).replace(/[^0-9-]/g,'');if(text.includes('-'))text=`${text.startsWith('-')?'-':''}${text.replace(/-/g,'')}`;if(/^-?\d+$/.test(text)){const n=Number(text);if(n>valueMax)text=String(valueMax);if(n< -valueMax*valueMax)text=String(-valueMax*valueMax);}input.value=text.slice(0,4);input.closest('.number-cell').classList.remove('correct','incorrect');queueSave();}
  inputs.forEach(input=>{input.addEventListener('input',()=>set(input,input.value));input.addEventListener('keydown',event=>{if(event.altKey||event.ctrlKey||event.metaKey)return;if(event.key==='Enter'){event.preventDefault();move(input,1,0);}else if(event.key==='Backspace'&&!input.value){event.preventDefault();move(input,-1,0);}else if(event.key==='ArrowRight'){event.preventDefault();move(input,1,0);}else if(event.key==='ArrowLeft'){event.preventDefault();move(input,-1,0);}else if(event.key==='ArrowDown'){event.preventDefault();move(input,0,1);}else if(event.key==='ArrowUp'){event.preventDefault();move(input,0,-1);}});});
  document.getElementById('cross-equations-check')?.addEventListener('click',()=>remote?.action('check'));
  document.getElementById('cross-equations-clear')?.addEventListener('click',()=>{inputs.forEach(i=>{if(!i.disabled)i.value='';i.closest('.number-cell').classList.remove('correct','incorrect');});status.textContent='Grid cleared.';save();});
  document.getElementById('reveal-solution')?.addEventListener('click',()=>remote?.action('reveal'));
})();
