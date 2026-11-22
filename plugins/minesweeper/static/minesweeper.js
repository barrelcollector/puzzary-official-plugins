(() => {
  const root=document.querySelector('.minesweeper-play'); if(!root)return;
  const width=Number(root.dataset.width),height=Number(root.dataset.height),mineCount=Number(root.dataset.mines);
  const board=root.querySelector('.minesweeper-board'),status=root.querySelector('.minesweeper-status'),flags=root.querySelector('[data-flags]');
  const offline=Boolean(document.body.dataset.offlinePuzzleId),remote=window.PuzzaryGroup||window.PuzzarySolo;
  let tool='reveal',state=JSON.parse(root.dataset.state||'{}'),lastStatus=state.status||'playing',busy=false,gameData={};
  if(offline){
    try{gameData=JSON.parse(document.getElementById('puzzary-offline-verification')?.textContent||'{}').game_data||{};}catch(_error){}
    try{const saved=JSON.parse(document.getElementById('puzzary-offline-progress')?.textContent||'{}');state={answers:saved.answers||{},status:'playing',exploded:''};}catch(_error){}
  }
  const mines=new Set(gameData.mines||[]),openConnected=gameData.open_connected_safe_spaces!==false;
  const cellKey=(x,y)=>`${x},${y}`;
  const neighbors=key=>{const [x,y]=key.split(',').map(Number),out=[];for(let ny=Math.max(0,y-1);ny<Math.min(height,y+2);ny++)for(let nx=Math.max(0,x-1);nx<Math.min(width,x+2);nx++)if(nx!==x||ny!==y)out.push(cellKey(nx,ny));return out;};
  const counts={}; for(let y=0;y<height;y++)for(let x=0;x<width;x++){const key=cellKey(x,y);if(!mines.has(key))counts[key]=String(neighbors(key).filter(item=>mines.has(item)).length);}
  if(offline&&Object.keys(counts).length&&Object.keys(state.answers||{}).filter(key=>key in counts).length===Object.keys(counts).length)state.status='won';
  board.style.setProperty('--minesweeper-columns',width);
  const cells=[];
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){const cell=document.createElement('button');cell.type='button';cell.className='minesweeper-cell';cell.dataset.key=cellKey(x,y);cell.setAttribute('role','gridcell');board.append(cell);cells.push(cell);}
  function label(cell,value){const [x,y]=cell.dataset.key.split(',').map(Number);return `Row ${y+1}, column ${x+1}: ${value==='F'?'flagged':value==='M'?'mine':value!==undefined?value==='0'?'clear':`${value} adjacent mines`:'hidden'}`;}
  function render(next={}){
    state=next; const answers=state.answers||{};
    cells.forEach(cell=>{const value=answers[cell.dataset.key];cell.className='minesweeper-cell';cell.textContent='';
      if(value==='F'){cell.classList.add('is-flagged');cell.textContent='⚑';}else if(value==='M'){cell.classList.add('is-revealed','is-mine');cell.textContent='●';}else if(value!==undefined){cell.classList.add('is-revealed',`near-${value}`);cell.textContent=value==='0'?'':value;}
      if(state.exploded===cell.dataset.key)cell.classList.add('is-exploded');cell.disabled=['won','lost','revealed'].includes(state.status);cell.setAttribute('aria-label',label(cell,value));});
    const used=Object.values(answers).filter(value=>value==='F').length;flags.textContent=Math.max(0,mineCount-used);
    status.textContent=state.status==='won'?'Board cleared. You won!':state.status==='lost'?'A mine exploded. Restart to try again.':state.status==='revealed'?'Solution revealed. Restart to play again.':`${mineCount-used} flag${mineCount-used===1?'':'s'} remaining.`;
    if(lastStatus!=='won'&&state.status==='won'&&!window.PuzzaryGroup)window.PuzzaryCelebrate?.complete();if(lastStatus==='won'&&state.status!=='won')window.PuzzaryCelebrate?.reset();lastStatus=state.status||'playing';
  }
  function revealFrom(answers,start){if(mines.has(start))return false;const pending=[start],seen=new Set();while(pending.length){const key=pending.pop();if(seen.has(key)||mines.has(key)||answers[key]==='F')continue;seen.add(key);answers[key]=counts[key];if(openConnected&&counts[key]==='0')pending.push(...neighbors(key));}return true;}
  async function save(){if(!offline)return;const answers=Object.fromEntries(Object.entries(state.answers||{}).filter(([_key,value])=>value!=='M'));try{await fetch(root.dataset.progressUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers})});}catch(_error){}}
  async function localAction(kind,target=''){
    const answers={...(state.answers||{})};
    if(kind==='reset'){state={answers:{},status:'playing',exploded:''};render(state);await save();return;}
    if(kind==='hint'||kind==='reveal'){status.textContent='Hints and solution reveal need a connection.';return;}
    if(state.status!=='playing')return;
    if(kind==='flag'){if(target in answers&&answers[target]!=='F')return;if(answers[target]==='F')delete answers[target];else if(Object.values(answers).filter(value=>value==='F').length<mineCount)answers[target]='F';}
    else if(kind==='reveal_cell'&&answers[target]!=='F'){
      if(mines.has(target)){state={answers:{...answers,...Object.fromEntries([...mines].map(key=>[key,'M']))},status:'lost',exploded:target};render(state);return;}
      if(target in answers){if(neighbors(target).filter(key=>answers[key]==='F').length===Number(counts[target]))for(const key of neighbors(target))if(!(key in answers)&&!revealFrom(answers,key)){state={answers:{...answers,...Object.fromEntries([...mines].map(item=>[item,'M']))},status:'lost',exploded:key};render(state);return;}}
      else revealFrom(answers,target);
    }
    state={answers,status:Object.keys(counts).every(key=>key in answers)?'won':'playing',exploded:''};render(state);await save();
  }
  async function act(kind,target=''){if(busy)return;busy=true;board.setAttribute('aria-busy','true');try{if(offline)await localAction(kind,target);else await remote?.action(kind,target);}finally{busy=false;board.removeAttribute('aria-busy');}}
  if(!offline)remote?.register({read:()=>({}),apply:render});render(state);
  root.querySelectorAll('[data-tool]').forEach(button=>button.addEventListener('click',()=>{tool=button.dataset.tool;root.querySelectorAll('[data-tool]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));}));
  board.addEventListener('click',event=>{const cell=event.target.closest('.minesweeper-cell');if(cell&&!cell.disabled)act(tool==='flag'?'flag':'reveal_cell',cell.dataset.key);});
  board.addEventListener('contextmenu',event=>{const cell=event.target.closest('.minesweeper-cell');if(!cell||cell.disabled)return;event.preventDefault();act('flag',cell.dataset.key);});
  board.addEventListener('keydown',event=>{const cell=event.target.closest('.minesweeper-cell');if(!cell)return;const [x,y]=cell.dataset.key.split(',').map(Number),moves={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};if(moves[event.key]){event.preventDefault();const [dx,dy]=moves[event.key];cells.find(item=>item.dataset.key===cellKey(x+dx,y+dy))?.focus();}else if(event.key.toLowerCase()==='f'){event.preventDefault();act('flag',cell.dataset.key);}else if(event.key==='Enter'||event.key===' '){event.preventDefault();act('reveal_cell',cell.dataset.key);}});
  root.querySelector('.minesweeper-hint')?.addEventListener('click',()=>act('hint'));root.querySelector('.minesweeper-restart')?.addEventListener('click',()=>act('reset'));document.getElementById('reveal-solution')?.addEventListener('click',()=>act('reveal'));
})();
