(() => {
  const root=document.querySelector('.minesweeper-play'); if(!root)return;
  const width=Number(root.dataset.width),height=Number(root.dataset.height),mineCount=Number(root.dataset.mines);
  const board=root.querySelector('.minesweeper-board'),status=root.querySelector('.minesweeper-status'),flags=root.querySelector('[data-flags]');
  const remote=window.PuzzaryGroup||window.PuzzarySolo;
  let tool='reveal',state=JSON.parse(root.dataset.state||'{}'),lastStatus=state.status||'playing',busy=false;
  board.style.setProperty('--minesweeper-columns',width);
  const cells=[];
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const cell=document.createElement('button'); cell.type='button'; cell.className='minesweeper-cell';
    cell.dataset.key=`${x},${y}`; cell.setAttribute('role','gridcell'); board.append(cell); cells.push(cell);
  }
  function label(cell,value){const [x,y]=cell.dataset.key.split(',').map(Number);return `Row ${y+1}, column ${x+1}: ${value==='F'?'flagged':value==='M'?'mine':value!==undefined?value==='0'?'clear':`${value} adjacent mines`:'hidden'}`;}
  function render(next={}){
    state=next; const answers=state.answers||{};
    cells.forEach(cell=>{const value=answers[cell.dataset.key];cell.className='minesweeper-cell';cell.textContent='';
      if(value==='F'){cell.classList.add('is-flagged');cell.textContent='⚑';}
      else if(value==='M'){cell.classList.add('is-revealed','is-mine');cell.textContent='●';}
      else if(value!==undefined){cell.classList.add('is-revealed',`near-${value}`);cell.textContent=value==='0'?'':value;}
      if(state.exploded===cell.dataset.key)cell.classList.add('is-exploded');
      cell.disabled=['won','lost','revealed'].includes(state.status);cell.setAttribute('aria-label',label(cell,value));
    });
    const used=Object.values(answers).filter(value=>value==='F').length;flags.textContent=Math.max(0,mineCount-used);
    status.textContent=state.status==='won'?'Board cleared. You won!':state.status==='lost'?'A mine exploded. Restart to try again.':state.status==='revealed'?'Solution revealed. Restart to play again.':`${mineCount-used} flag${mineCount-used===1?'':'s'} remaining.`;
    if(lastStatus!=='won'&&state.status==='won'&&!window.PuzzaryGroup)window.PuzzaryCelebrate?.complete();
    if(lastStatus==='won'&&state.status!=='won')window.PuzzaryCelebrate?.reset(); lastStatus=state.status||'playing';
  }
  async function act(kind,target=''){if(busy)return;busy=true;board.setAttribute('aria-busy','true');try{await remote?.action(kind,target);}finally{busy=false;board.removeAttribute('aria-busy');}}
  remote?.register({read:()=>({}),apply:render}); render(state);
  root.querySelectorAll('[data-tool]').forEach(button=>button.addEventListener('click',()=>{tool=button.dataset.tool;root.querySelectorAll('[data-tool]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));}));
  board.addEventListener('click',event=>{const cell=event.target.closest('.minesweeper-cell');if(cell&&!cell.disabled)act(tool==='flag'?'flag':'reveal_cell',cell.dataset.key);});
  board.addEventListener('contextmenu',event=>{const cell=event.target.closest('.minesweeper-cell');if(!cell||cell.disabled)return;event.preventDefault();act('flag',cell.dataset.key);});
  board.addEventListener('keydown',event=>{const cell=event.target.closest('.minesweeper-cell');if(!cell)return;const [x,y]=cell.dataset.key.split(',').map(Number),moves={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
    if(moves[event.key]){event.preventDefault();const [dx,dy]=moves[event.key];cells.find(item=>item.dataset.key===`${x+dx},${y+dy}`)?.focus();}
    else if(event.key.toLowerCase()==='f'){event.preventDefault();act('flag',cell.dataset.key);}
    else if(event.key==='Enter'||event.key===' '){event.preventDefault();act('reveal_cell',cell.dataset.key);}
  });
  root.querySelector('.minesweeper-hint')?.addEventListener('click',()=>act('hint'));
  root.querySelector('.minesweeper-restart')?.addEventListener('click',()=>act('reset'));
  document.getElementById('reveal-solution')?.addEventListener('click',()=>act('reveal'));
})();
