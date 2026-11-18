(function () {
  const root = document.querySelector(".maze-play");
  if (!root) return;

  const svg = root.querySelector(".maze-board");
  const trace = root.querySelector(".maze-trace-path");
  const progressUrl = root.dataset.progressUrl;
  const status = document.getElementById("maze-status");
  const completeButton = document.getElementById("maze-complete");
  const clearButton = document.getElementById("maze-clear");
  const width = Number(root.dataset.width || 0);
  const height = Number(root.dataset.height || 0);
  const cellSize = Number(root.dataset.cellSize || 24);
  let grid = [];
  let path = [];
  let drawing = false;
  let celebrationReady = false;
  let pathKey = 'path', localValue = '', legIndex = null;
  let rallyEpoch = null, knownLegs = null;
  let startPoint = {x:0,y:0}, finishPoint = {x:width-1,y:height-1}, canDraw = true;
  const groupLines = document.createElementNS('http://www.w3.org/2000/svg','g');
  const checkpointLayer = document.createElementNS('http://www.w3.org/2000/svg','g');
  const legend = document.createElement('div'); legend.className = 'maze-player-legend';
  const turns = document.createElement('ol'); turns.className = 'maze-turn-order'; turns.setAttribute('aria-label','Rally turn order');
  if (window.PuzzaryGroup) { svg.append(groupLines,checkpointLayer); root.append(legend,turns); completeButton.hidden = true; }

  try {
    grid = JSON.parse(root.dataset.grid || "[]");
  } catch (_error) {
    grid = [];
  }

  try {
    path = JSON.parse(root.dataset.path || "[]");
  } catch (_error) {
    path = [];
  }
  if (!Array.isArray(path) || path.length === 0) path = [{ x: 0, y: 0 }];

  function samePoint(a, b) {
    return Boolean(a && b && a.x === b.x && a.y === b.y);
  }

  function center(point) {
    return `${point.x * cellSize + cellSize / 2},${point.y * cellSize + cellSize / 2}`;
  }

  function isFinish(point) {
    return samePoint(point, finishPoint);
  }

  function setStatus(text) {
    if (status) status.textContent = text;
  }

  function isValidStep(from, to) {
    if (!from || !to) return false;
    if (to.x < 0 || to.y < 0 || to.x >= width || to.y >= height) return false;
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    let direction = "";
    if (dx === 1 && dy === 0) direction = "e";
    if (dx === -1 && dy === 0) direction = "w";
    if (dx === 0 && dy === 1) direction = "s";
    if (dx === 0 && dy === -1) direction = "n";
    if (!direction) return false;
    const cell = grid[from.y] && grid[from.y][from.x];
    return Boolean(cell && cell.walls && cell.walls[direction] === false);
  }

  function renderPath() {
    if (trace) trace.setAttribute("points", path.map(center).join(" "));
    const completed = isFinish(path[path.length - 1]);
    root.dataset.completed = completed ? "true" : "false";
    root.classList.toggle("complete", completed);
    if (completed) {
      setStatus("Solved. The traced path reached Finish.");
      if (!window.PuzzaryGroup && celebrationReady && window.PuzzaryCelebrate) window.PuzzaryCelebrate.complete();
    } else if (path.length > 1) {
      setStatus(`${path.length} cells traced. Keep going to F.`);
    } else {
      setStatus("Drag from S to F. Backtrack over your path to undo.");
    }
  }

  async function savePath(forceCompleted) {
    if (window.PuzzaryGroup) { window.PuzzaryGroup.save(); return; }
    const completed = forceCompleted || isFinish(path[path.length - 1]);
    root.dataset.completed = completed ? "true" : "false";
    root.classList.toggle("complete", completed);
    if (!progressUrl) return;
    try {
      await fetch(progressUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          answers: {
            completed: completed ? "true" : "",
            path: JSON.stringify(path),
          },
        }),
      });
    } catch (_error) {
      setStatus("Progress could not be saved.");
    }
  }

  function cellFromEvent(event) {
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const viewBox = svg.viewBox.baseVal;
    const scaleX = viewBox.width / rect.width;
    const scaleY = viewBox.height / rect.height;
    const x = Math.floor(((event.clientX - rect.left) * scaleX) / cellSize);
    const y = Math.floor(((event.clientY - rect.top) * scaleY) / cellSize);
    if (x < 0 || y < 0 || x >= width || y >= height) return null;
    return { x, y };
  }

  function visit(point) {
    if (!point || !canDraw) return;
    const last = path[path.length - 1];
    if (samePoint(point, last)) return;

    const existingIndex = path.findIndex((item) => samePoint(item, point));
    if (existingIndex >= 0) {
      path = path.slice(0, existingIndex + 1);
      localValue = JSON.stringify(path);
      renderPath();
      if (window.PuzzaryGroup) savePath(false);
      return;
    }

    if (window.PuzzaryGroup && samePoint(last, finishPoint)) return;
    if (!isValidStep(last, point)) {
      setStatus("That move crosses a wall.");
      return;
    }

    path.push(point);
    localValue = JSON.stringify(path);
    renderPath();
    if (window.PuzzaryGroup || isFinish(point)) savePath(isFinish(point));
  }

  if (svg) {
    svg.addEventListener("pointerdown", (event) => {
      if (!canDraw) return;
      event.preventDefault();
      svg.setPointerCapture(event.pointerId);
      drawing = true;
      const point = cellFromEvent(event);
      if (samePoint(point, startPoint)) {
        path = [startPoint]; localValue = '';
        renderPath();
        if (window.PuzzaryGroup) savePath(false);
      } else {
        visit(point);
      }
    });

    svg.addEventListener("pointermove", (event) => {
      if (!drawing) return;
      event.preventDefault();
      visit(cellFromEvent(event));
    });

    svg.addEventListener("pointerup", (event) => {
      drawing = false;
      savePath(false);
      if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    });

    svg.addEventListener("pointercancel", () => {
      drawing = false;
      savePath(false);
    });
  }

  if (completeButton) {
    completeButton.addEventListener("click", () => {
      root.dataset.completed = "true";
      root.classList.add("complete");
      setStatus("Maze marked complete.");
      if (window.PuzzaryCelebrate) window.PuzzaryCelebrate.complete();
      savePath(true);
    });
  }

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      if (!canDraw) return;
      path = [startPoint]; localValue = '';
      renderPath();
      savePath(false);
    });
  }

  renderPath();
  celebrationReady = true;

  function readPath(value) { try { const result = JSON.parse(value || '[]'); return Array.isArray(result) ? result : []; } catch (_) { return []; } }
  function activeLeg(state) {
    const checkpoints = state.maze_group?.checkpoints || [];
    return checkpoints.slice(1).findIndex((finish,index) => !samePoint(readPath(state.answers?.[`leg:${index}`]).at(-1),finish));
  }
  function editableKey(state, data) {
    const mode = state.maze_group?.mode || 'co_op';
    if (mode === 'companions') return `path:${data.user_id}`;
    if (mode === 'rally') {
      const leg = activeLeg(state), players = data.context.participants;
      return leg >= 0 && players[leg%players.length] === data.user_id ? `leg:${leg}` : null;
    }
    return 'path';
  }
  function svgNode(tag,attributes) {
    const node = document.createElementNS('http://www.w3.org/2000/svg',tag);
    for (const [key,value] of Object.entries(attributes)) node.setAttribute(key,value);
    return node;
  }
  window.PuzzaryGroup?.register({
    activePlayer(data) {
      if (data.state.maze_group?.mode !== 'rally') return null;
      const leg = activeLeg(data.state), players = data.context.participants;
      return leg >= 0 ? players[leg%players.length] : null;
    },
    read() { return pathKey && localValue ? {[pathKey]:localValue} : {}; },
    scope(answers,data) { const key = editableKey({...data.state,answers},data); return key && answers[key] ? {[key]:answers[key]} : {}; },
    apply(state,data) {
      const mode = state.maze_group?.mode || 'co_op';
      const nextKey = editableKey(data.state,data);
      if (pathKey !== nextKey || rallyEpoch !== data.puzzle_epoch) drawing = false;
      pathKey = nextKey; canDraw = !!pathKey && !data.closed;
      const checkpoints = state.maze_group?.checkpoints || [];
      legIndex = mode === 'rally' ? activeLeg(data.state) : null;
      startPoint = mode === 'rally' && legIndex >= 0 ? checkpoints[legIndex] : {x:0,y:0};
      finishPoint = mode === 'rally' && legIndex >= 0 ? checkpoints[legIndex+1] : {x:width-1,y:height-1};
      localValue = state.answers?.[pathKey] || '';
      path = readPath(localValue); if (!path.length) path = [startPoint];
      renderPath();
      trace.style.stroke = window.PuzzaryGroup.color(data.user_id);
      const ownOffset = mode === 'companions' ? (data.context.participants.indexOf(data.user_id) % 5 - 2) * .9 : 0;
      trace.setAttribute('transform',`translate(${ownOffset},${ownOffset})`);
      svg.querySelectorAll('.maze-label').forEach(label => { label.style.display = mode === 'rally' ? 'none' : ''; });
      clearButton.disabled = !canDraw;
      groupLines.replaceChildren(); checkpointLayer.replaceChildren(); legend.replaceChildren(); turns.replaceChildren();
      turns.hidden = mode !== 'rally';
      for (const [key,value] of Object.entries(state.answers || {})) {
        if (key === pathKey) continue;
        const owner = mode === 'companions' ? Number(key.split(':')[1]) : mode === 'rally' ? data.context.participants[Number(key.split(':')[1])%data.context.participants.length] : data.host_id;
        const color = window.PuzzaryGroup.color(owner);
        const attributes = {points:readPath(value).map(center).join(' '),fill:'none',stroke:color,'stroke-width':3.5,'stroke-linecap':'round','stroke-linejoin':'round','vector-effect':'non-scaling-stroke',opacity:.8};
        if (mode === 'companions') {
          const offset = (data.context.participants.indexOf(owner) % 5 - 2) * .9;
          attributes.transform = `translate(${offset},${offset})`;
        }
        groupLines.append(svgNode('polyline',attributes));
      }
      if (mode === 'companions') for (const member of data.members.filter(m => m.status === 'active')) {
        const item = document.createElement('span'); item.textContent = member.name; item.style.color = window.PuzzaryGroup.color(member.user_id); legend.append(item);
      }
      if (mode === 'rally') {
        const completedLegs = new Set(checkpoints.slice(1).map((finish,index) => samePoint(readPath(data.state.answers?.[`leg:${index}`]).at(-1),finish) ? index : null).filter(index => index !== null));
        if (rallyEpoch === data.puzzle_epoch && knownLegs && [...completedLegs].some(index => !knownLegs.has(index)) && !data.completed) window.PuzzarySounds?.progress();
        knownLegs = completedLegs;
        for (let index = 0; index < checkpoints.length-1; index++) {
          const player = data.context.participants[index%data.context.participants.length];
          const member = data.members.find(m => m.user_id === player);
          const item = document.createElement('li'); item.dataset.player = player; item.dataset.leg = index;
          item.style.setProperty('--player-color',window.PuzzaryGroup.color(player));
          const name = document.createElement('strong'); name.textContent = member?.name || 'Player';
          const description = document.createElement('span'); description.textContent = `Checkpoints ${index+1} to ${index+2}`;
          const phase = document.createElement('span'); phase.className = 'maze-turn-phase';
          phase.textContent = completedLegs.has(index) ? 'Complete' : index === legIndex ? player === data.user_id ? 'Your turn' : 'Playing now' : index === legIndex + 1 ? 'Up next' : 'Waiting';
          if (index === legIndex) { item.classList.add('current-turn'); item.setAttribute('aria-current','step'); }
          item.classList.toggle('leg-complete',completedLegs.has(index));
          item.append(name,description,phase); turns.append(item);
        }
        checkpoints.forEach((point,index) => {
          const [cx,cy] = center(point).split(',');
          checkpointLayer.append(svgNode('circle',{cx,cy,r:cellSize*.28,fill:'#fff',stroke:'#555','stroke-width':1}));
          const label = svgNode('text',{x:cx,y:Number(cy)+3,'text-anchor':'middle','font-size':10,fill:'#222'}); label.textContent = index+1; checkpointLayer.append(label);
        });
        const owner = legIndex >= 0 ? data.context.participants[legIndex%data.context.participants.length] : null;
        const name = data.members.find(m => m.user_id === owner)?.name || 'Player';
        setStatus(legIndex < 0 ? 'Rally complete.' : `Leg ${legIndex+1}: checkpoint ${legIndex+1} to ${legIndex+2}. ${canDraw ? 'Your turn.' : `${name}'s turn.`}`);
      } else {
        knownLegs = null;
      }
      rallyEpoch = data.puzzle_epoch;
    }
  });
})();
