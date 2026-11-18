(() => {
  const root = document.querySelector('.spell-it-play');
  if (!root) return;
  const entries = JSON.parse(root.querySelector('.spell-data').textContent).entries;
  const stage = root.querySelector('.spell-stage'), nav = root.querySelector('.spell-navigation'), status = root.querySelector('.spell-status');
  let current = 0, answers = {}, states = entries.map(() => 'incomplete'), banks = entries.map(e => e.bank), remaining = entries.map(e => e.settings.hint_limit);
  let timer, busy = false, chain = Promise.resolve(), revision = 0, savedRevision = 0, ready = false, focusedPosition = null;
  const completed = new Set();
  const element = (tag, text, cls) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; };
  const button = (text, action) => { const b = element('button', text, 'ghost-button'); b.type = 'button'; b.addEventListener('click', event => Promise.resolve(action(event)).catch(error => message(error.message))); return b; };
  const key = position => `${current}:${position}`;
  const hinted = () => String(answers[`hint:${current}`] || '').split(',').filter(Boolean).map(Number);
  function message(text) { status.textContent = text; }
  function available(letter, replace = null) {
    const e = entries[current];
    if (!banks[current].length) return true;
    const used = e.hidden.filter(p => p !== replace && answers[key(p)] === letter).length;
    return used < banks[current].filter(ch => ch === letter).length;
  }
  function bankDraw(container) {
    container.replaceChildren();
    const used = {};
    entries[current].hidden.forEach(p => { const ch = answers[key(p)]; if (ch) used[ch] = (used[ch] || 0) + 1; });
    banks[current].forEach((letter, index) => {
      const taken = (used[letter] || 0) > 0;
      if (taken) used[letter] -= 1;
      const tile = button(letter, () => {
        const input = stage.querySelector(`input[data-position="${focusedPosition}"]:not([readonly])`) || stage.querySelector('input[data-position]:not([readonly]):placeholder-shown') || stage.querySelector('input[data-position]:not([readonly])');
        if (!input) return;
        if (edit(Number(input.dataset.position), letter)) focusNext(Number(input.dataset.position), 1);
      });
      tile.disabled = taken; tile.classList.add('spell-bank-tile'); tile.dataset.tile = String(index);
      tile.setAttribute('aria-label', `${letter}, tile ${index + 1}${taken ? ', used' : ''}`);
      container.append(tile);
    });
  }
  function focusNext(position, direction) {
    const inputs = [...stage.querySelectorAll('input[data-position]:not([readonly])')];
    const index = inputs.findIndex(el => Number(el.dataset.position) === position);
    const target = inputs[index + direction];
    if (target) { target.focus(); target.select(); }
  }
  function edit(position, value) {
    value = value.toUpperCase().replace(/[^A-Z]/g, '').slice(-1);
    const input = stage.querySelector(`[data-position="${position}"]`);
    if (value && !available(value, position)) { input.value = answers[key(position)] || ''; message('That letter has no remaining tile.'); return false; }
    if (value) answers[key(position)] = value; else delete answers[key(position)];
    states[current] = 'incomplete'; revision += 1;
    input.value = value;
    const container = stage.querySelector('.spell-letter-bank'); if (container) bankDraw(container);
    message(''); navigation();
    clearTimeout(timer); timer = setTimeout(() => save().catch(() => {}), 180);
    return true;
  }
  function navigation() {
    nav.replaceChildren();
    entries.forEach((entry, index) => {
      const b = button(String(index + 1), async () => { if (busy || !ready) return; await save(); current = index; focusedPosition = null; draw(); });
      b.classList.toggle('correct', states[index] === 'correct'); b.setAttribute('aria-label', `Word ${index + 1}${states[index] === 'correct' ? ', completed' : ''}`);
      b.setAttribute('aria-current', index === current ? 'step' : 'false');
      b.disabled = !ready || busy || index > 0 && states[index - 1] !== 'correct' && states[index] !== 'correct'; nav.append(b);
    });
  }
  function draw() {
    const entry = entries[current]; stage.replaceChildren(); navigation();
    stage.append(element('h2', `Word ${current + 1} of ${entries.length}`), element('p', entry.definition, 'spell-definition'));
    const slots = element('div', undefined, 'spell-slots'); slots.setAttribute('role', 'group'); slots.setAttribute('aria-label', 'Spelling');
    entry.slots.forEach((slot, position) => {
      if (slot !== null) {
        const given = element('span', slot === ' ' ? '\u00a0' : slot, `spell-slot ${slot === ' ' ? 'space' : 'given'}`);
        given.setAttribute('aria-label', slot === ' ' ? 'Space' : `Position ${position + 1}: ${slot}`); slots.append(given); return;
      }
      const input = element('input', undefined, 'spell-slot blank'); input.type = 'text'; input.maxLength = 1; input.autocomplete = 'off'; input.inputMode = 'text'; input.placeholder = ' ';
      input.dataset.position = position; input.dataset.key = key(position); input.value = answers[key(position)] || ''; input.readOnly = hinted().includes(position);
      input.setAttribute('aria-label', `Word ${current + 1}, letter ${position + 1}${input.readOnly ? ', revealed' : ''}`);
      input.addEventListener('focus', () => { focusedPosition = position; input.select(); });
      input.addEventListener('input', () => { if (!input.readOnly && edit(position, input.value) && input.value) focusNext(position, 1); });
      input.addEventListener('keydown', event => {
        if (event.ctrlKey || event.metaKey || event.altKey || input.readOnly) return;
        if (/^[A-Za-z]$/.test(event.key)) { event.preventDefault(); if (edit(position, event.key)) focusNext(position, 1); }
        else if (event.key === 'Backspace') { event.preventDefault(); if (input.value) edit(position, ''); else focusNext(position, -1); }
        else if (event.key === 'Delete') { event.preventDefault(); edit(position, ''); }
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); focusNext(position, event.key === 'ArrowLeft' ? -1 : 1); }
        else if (event.key === 'Enter') { event.preventDefault(); check(); }
      }); slots.append(input);
    }); stage.append(slots);
    const bank = element('div', undefined, 'spell-letter-bank'); bank.setAttribute('role', 'group'); bank.setAttribute('aria-label', 'Available letters'); stage.append(bank); bankDraw(bank);
    const actions = element('div', undefined, 'action-row');
    actions.append(button('Check Word', check), button('Clear Word', async () => {
      if (busy || !ready) return;
      entry.hidden.forEach(p => { if (!hinted().includes(p)) delete answers[key(p)]; }); revision += 1; states[current] = 'incomplete'; draw(); await save(); message('Word cleared.');
    }));
    const hint = button(`Reveal Letter (${remaining[current]})`, () => reveal('letter')); hint.disabled = !remaining[current]; actions.append(hint);
    if (entry.settings.letter_bank === 'hint_triggered' && !banks[current].length) actions.append(button('Show Letter Bank', () => reveal('bank')));
    if (current < entries.length - 1) { const next = button('Next Word', async () => { if (states[current] !== 'correct' || busy) return; await save(); current += 1; focusedPosition = null; draw(); }); next.disabled = states[current] !== 'correct'; actions.append(next); }
    if (entry.hints.length) { const details = element('details'); details.append(element('summary', 'More Clues')); entry.hints.forEach(h => details.append(element('p', h))); stage.append(details); }
    stage.append(actions);
    stage.querySelectorAll('button,input').forEach(el => { if (busy || !ready) el.disabled = true; });
  }
  function save() {
    clearTimeout(timer);
    if (window.PuzzaryGroup) { window.PuzzaryGroup.save(); return Promise.resolve(); }
    const snapshot = {...answers}, version = revision;
    chain = chain.catch(() => {}).then(async () => {
      const response = await fetch(root.dataset.progressUrl, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({answers:snapshot})});
      if (!response.ok) throw new Error('Progress could not be saved.');
      const result = await response.json(); if (revision === version) { answers = result.answers; savedRevision = version; }
    });
    return chain.catch(error => { message(error.message); throw error; });
  }
  async function request(kind, payload) {
    if (window.PuzzaryGroup) return window.PuzzaryGroup.action(kind === 'attempts' ? 'check' : 'hint',payload.kind === 'bank' ? `bank:${current}` : String(current));
    if (busy || !ready) return;
    busy = true; draw();
    try {
      await save();
      const result = await fetch(`${root.dataset.api}/${kind}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({answers, ...payload})});
      const data = await result.json(); if (!result.ok) throw new Error(data.detail || 'Request failed.');
      answers = data.answers; states = data.states; banks = data.letter_banks; remaining = data.hints_remaining;
      if (kind === 'attempts') {
        const s = states[current]; message(s === 'correct' ? 'Correct.' : s === 'incomplete' ? 'Complete the missing letters first.' : 'Not quite. Try another spelling.');
        if (s === 'correct' && !completed.has(current)) { completed.add(current); if (!data.completed) window.PuzzarySounds?.progress(); }
        if (data.completed) { message('Spell It complete.'); window.PuzzaryCelebrate?.complete(); }
      } else message(payload.kind === 'bank' ? 'Letter bank opened.' : 'One letter revealed.');
    } catch (error) { message(error.message); }
    finally { busy = false; draw(); }
  }
  function check() { return request('attempts', {}); }
  function reveal(kind) { return request('hint', {entry:current, kind}); }
  const resetForm = document.querySelector('form[action$="/reset"]');
  let resetting = false;
  resetForm?.addEventListener('submit', async event => {
    if (resetting) return;
    event.preventDefault();
    if (busy) { message('Wait for the current check or hint before resetting.'); return; }
    clearTimeout(timer); busy = true; ready = false; draw();
    const submitter = event.submitter;
    await chain.catch(() => {});
    // Leave the original submission algorithm before dispatching another submit.
    resetting = true; setTimeout(() => resetForm.requestSubmit(submitter), 0);
  });
  window.addEventListener('pagehide', () => {
    if (window.PuzzaryGroup) return;
    if (!ready || savedRevision === revision) return;
    clearTimeout(timer);
    fetch(root.dataset.progressUrl, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({answers}), keepalive:true}).catch(() => {});
  });
  draw();
  if (window.PuzzaryGroup) {
    window.PuzzaryGroup.register({
      read() { return Object.fromEntries(Object.entries(answers).filter(([key]) => !key.startsWith('hint:') && !key.startsWith('bank:') && !String(answers[`hint:${key.split(':')[0]}`] || '').split(',').includes(key.split(':')[1]))); },
      scope(values) { return Object.fromEntries(Object.entries(values).filter(([key]) => !key.startsWith('hint:') && !key.startsWith('bank:') && !String(values[`hint:${key.split(':')[0]}`] || '').split(',').includes(key.split(':')[1]))); },
      apply(data) {
        const focused = stage.querySelector('input:focus')?.dataset.position;
        answers = {...data.answers};
        states = data.states || entries.map(() => 'incomplete');
        banks = data.letter_banks || entries.map(e => e.bank);
        remaining = data.hints_remaining || entries.map(e => e.settings.hint_limit);
        ready = true;
        // Keep input nodes stable during shared edits so typing and cursor gestures continue.
        const slots = [...stage.querySelectorAll('input[data-position]')];
        if (!slots.length || slots.some(input => input.readOnly !== hinted().includes(Number(input.dataset.position)))) {
          draw();
          if (focused !== undefined) stage.querySelector(`[data-position="${focused}"]`)?.focus();
        } else {
          slots.forEach(input => { const value = answers[key(input.dataset.position)] || ''; if (input.value !== value) input.value = value; input.disabled = false; });
          navigation();
          bankDraw(stage.querySelector('.spell-letter-bank'));
          // Hint availability and the next-word button depend on shared completion.
          const actions = stage.querySelector('.action-row');
          actions.querySelectorAll('button').forEach(b => { b.disabled = false; });
          const hint = [...actions.querySelectorAll('button')].find(b => b.textContent.startsWith('Reveal Letter'));
          if (hint) { hint.textContent = `Reveal Letter (${remaining[current]})`; hint.disabled = !remaining[current]; }
          const next = [...actions.querySelectorAll('button')].find(b => b.textContent === 'Next Word');
          if (next) next.disabled = states[current] !== 'correct';
          const bankButton = [...actions.querySelectorAll('button')].find(b => b.textContent === 'Show Letter Bank');
          if (bankButton) bankButton.hidden = banks[current].length > 0;
        }
        if (data.checked) message(states[current] === 'correct' ? 'Correct.' : states[current] === 'incorrect' ? 'Not quite. Try another spelling.' : 'Complete the missing letters first.');
      }
    });
    return;
  }
  fetch(`${root.dataset.api}/progress`).then(async response => { if (!response.ok) throw new Error('Progress could not be loaded.'); return response.json(); }).then(data => {
    answers = data.answers; states = data.states; banks = data.letter_banks; remaining = data.hints_remaining;
    states.forEach((s, i) => { if (s === 'correct') completed.add(i); });
    const unfinished = states.findIndex(s => s !== 'correct'); current = unfinished < 0 ? entries.length - 1 : unfinished; ready = true; draw();
    if (unfinished < 0) message('Spell It complete.');
  }).catch(error => message(error.message));
})();
