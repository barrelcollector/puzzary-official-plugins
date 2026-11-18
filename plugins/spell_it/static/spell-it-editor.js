window.PuzzaryManualEditors = window.PuzzaryManualEditors || {};
window.PuzzaryManualEditors.spell_it = (form, parts) => {
  const source = form.querySelector('[name="manual_entries"]');
  if (!source) return;
  source.closest('label').classList.add('builder-source-hidden');
  let entries;
  try { entries = JSON.parse(source.value); } catch (_) { entries = []; }
  if (!Array.isArray(entries)) entries = [];
  let dragIndex = null, version = 0, previewTimer, validatedVersion = -1, submitting = false;
  const status = document.createElement('p'); status.setAttribute('role', 'status'); parts.toolbar.append(status);
  const create = (tag, text) => { const el = document.createElement(tag); if (text) el.textContent = text; return el; };
  const iconButton = (icon, name, action) => { const b = create('button'); b.type = 'button'; b.title = name; b.setAttribute('aria-label', name); b.className = 'ghost-button spell-icon'; const image = create('img'); image.src = `/static/icons/${icon}.svg`; image.alt = ''; b.append(image); b.addEventListener('click', action); return b; };
  const add = iconButton('plus', 'Add Word', () => { entries.push({answer:'', definition:''}); render(); }); parts.toolbar.append(add);
  const bankLabel = create('label', 'Word bank'), bankSelect = create('select'); bankSelect.add(new Option('Choose a bank', '')); bankLabel.append(bankSelect); parts.toolbar.append(bankLabel);
  const wordLabel = create('label', 'Word and definition'), wordSelect = create('select'); wordSelect.add(new Option('Choose a word', '')); wordLabel.append(wordSelect); parts.toolbar.append(wordLabel);
  bankSelect.setAttribute('aria-label', 'Word bank'); wordSelect.setAttribute('aria-label', 'Word and definition');
  let selections = [];
  const addBank = iconButton('plus', 'Add Selected Word', () => {
    const selection = selections[Number(wordSelect.value)]; if (!selection) return;
    entries.push({...selection, properties:{source_bank:bankSelect.selectedOptions[0].dataset.slug}}); render();
  }); addBank.disabled = true; parts.toolbar.append(addBank);
  fetch('/api/word-banks?limit=500').then(r => { if (!r.ok) throw Error('Word banks are unavailable for this account.'); return r.json(); }).then(data => {
    data.items.forEach(bank => { const option = new Option(bank.name, bank.id); option.dataset.slug = bank.slug; bankSelect.add(option); });
  }).catch(error => { status.textContent = error.message; });
  bankSelect.addEventListener('change', async () => {
    wordSelect.replaceChildren(new Option('Choose a word', '')); selections = []; addBank.disabled = true;
    if (!bankSelect.value) return;
    const id = bankSelect.value;
    try {
      const result = await fetch(`/api/word-banks/${id}/export`); if (!result.ok) throw Error('Word bank could not be loaded.');
      const bank = await result.json(); if (bankSelect.value !== id) return;
      (bank.entries || []).forEach(link => {
        const definitions = link.definitions || [];
        const selected = definitions[link.selected_definition || 0];
        (selected ? [selected] : definitions).filter(d => d.definition).forEach(d => {
          const item = {answer:link.display_text || link.word, definition:d.definition};
          const option = new Option(`${item.answer} - ${item.definition.slice(0,70)}`, selections.length); selections.push(item); wordSelect.add(option);
        });
      });
    } catch (error) { status.textContent = error.message; }
  });
  wordSelect.addEventListener('change', () => { addBank.disabled = wordSelect.value === ''; });
  function sync() {
    const bankMode = form.querySelector('[name="manual_letter_bank"]')?.value || 'default';
    entries.forEach((entry,index) => {
      const count = parts.canvas.querySelector(`[data-entry="${index}"] [data-field="decoy_count"]`);
      if (count) count.disabled = (entry.letter_bank || bankMode) !== 'decoy';
    });
    source.value = JSON.stringify(entries); version += 1; clearTimeout(previewTimer); previewTimer = setTimeout(preview, 260);
  }
  function options() {
    const result = {entries, _difficulty:form.querySelector('[name="difficulty"]')?.value || 'easy'};
    form.querySelectorAll('[name^="manual_"]').forEach(el => { const key = el.name.slice(7); if (key !== 'entries' && !el.disabled && el.value !== '') result[key] = el.value; });
    return result;
  }
  async function preview() {
    const requestVersion = version;
    try {
      const response = await fetch('/api/spell-it/editor-preview', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(options())});
      const data = await response.json(); if (requestVersion !== version) return;
      if (!response.ok) throw Error(data.detail || 'Preview unavailable');
      data.solution_payload.entries.forEach((entry, index) => {
        entries[index].hidden = entry.hidden;
        drawMask(parts.canvas.querySelector(`[data-entry="${index}"] .spell-editor-mask`), index);
        const bank = parts.canvas.querySelector(`[data-entry="${index}"] .spell-editor-bank`); bank.textContent = entry.settings.letter_bank === 'off' ? '' : entry.bank.join(' ');
      });
      source.value = JSON.stringify(entries); validatedVersion = requestVersion; status.textContent = `${entries.length} valid ${entries.length === 1 ? 'word' : 'words'}.`;
    } catch (error) { if (requestVersion === version) status.textContent = error.message; }
  }
  function drawMask(container, index) {
    if (!container) return;
    container.replaceChildren();
    const entry = entries[index], answer = String(entry.answer || '').toUpperCase();
    for (let p = 0; p < answer.length; p++) {
      const char = answer[p];
      if (!/[A-Z]/.test(char)) { const fixed = create('span', char === ' ' ? '\u00a0' : char); fixed.className = `spell-slot ${char === ' ' ? 'space' : 'given'}`; container.append(fixed); continue; }
      const masked = (entry.hidden || []).includes(p), b = create('button', masked ? '_' : char); b.type = 'button'; b.className = 'spell-slot';
      b.title = `${masked ? 'Reveal' : 'Hide'} ${char} at position ${p + 1}`; b.setAttribute('aria-label', b.title); b.setAttribute('aria-pressed', String(masked));
      b.addEventListener('click', () => { entry.hidden = masked ? entry.hidden.filter(value => value !== p) : [...(entry.hidden || []), p].sort((a,b) => a-b); drawMask(container,index); sync(); }); container.append(b);
    }
  }
  function render() {
    parts.canvas.replaceChildren();
    entries.forEach((entry, index) => {
      const article = create('article'); article.className = 'spell-editor-entry'; article.dataset.entry = index; article.draggable = true;
      const head = create('div'); head.className = 'action-row';
      const handle = create('span'); const image = create('img'); image.src = '/static/icons/ellipsis-vertical.svg'; image.alt = ''; handle.append(image); handle.title = 'Drag to reorder'; handle.className = 'spell-drag'; head.append(handle, create('h3', `Word ${index + 1}`));
      const position = create('input'); position.type = 'number'; position.min = 1; position.max = entries.length; position.value = index + 1; position.className = 'spell-position'; position.setAttribute('aria-label', `Position of word ${index + 1}`);
      position.addEventListener('change', () => {
        const next = Math.max(0, Math.min(entries.length - 1, Number(position.value) - 1)), previous = entries.indexOf(entry);
        if (!Number.isInteger(next) || previous < 0 || next === previous) return;
        entries.splice(next, 0, entries.splice(previous, 1)[0]); render();
      }); head.append(position, iconButton('x', `Remove word ${index + 1}`, () => { entries.splice(index,1); render(); })); article.append(head);
      function field(name, label, type='text') {
        const l = create('label', label), input = create(type === 'textarea' ? 'textarea' : 'input'); if (type !== 'textarea') input.type = type; else input.rows = 2;
        input.value = Array.isArray(entry[name]) ? entry[name].join('\n') : entry[name] ?? ''; input.dataset.field = name; if (type === 'number') { input.min = name === 'mask_percent' ? 1 : 0; input.max = name === 'mask_percent' ? 100 : 20; }
        input.addEventListener('input', () => { entry[name] = input.value; if (name === 'answer' || name === 'mask_percent') { delete entry.hidden; drawMask(article.querySelector('.spell-editor-mask'),index); } sync(); }); l.append(input); return l;
      }
      article.append(field('answer','Answer'), field('definition','Definition','textarea'));
      const mask = create('div'); mask.className = 'spell-editor-mask spell-slots'; article.append(mask); drawMask(mask,index);
      const regenerate = create('button', 'Regenerate Mask'); regenerate.type = 'button'; regenerate.className = 'ghost-button'; regenerate.addEventListener('click', () => { delete entry.hidden; form.querySelector('[name="manual_seed"]').value = String(Date.now()); sync(); }); article.append(regenerate);
      const details = create('details'); details.append(create('summary','Word Options'));
      for (const [name,label,values] of [
        ['difficulty','Difficulty',['','very_easy','easy','medium','hard','expert']], ['letter_bank','Letter bank',['','default','off','exact','decoy','hint_triggered']], ['preserve_edges','Protect first/last',['','yes','no']]
      ]) { const l=create('label',label), select=create('select'); values.forEach(value => select.add(new Option(value ? value.replaceAll('_',' ') : 'Puzzle default',value))); select.value=entry[name] || ''; select.addEventListener('change',()=> { entry[name]=select.value; delete entry.hidden; sync(); }); l.append(select); details.append(l); }
      details.append(field('mask_percent','Hidden letters (%)','number'),field('decoy_count','Extra letters (Decoy bank)','number'),field('hint_limit','Letter hint limit','number'),field('hints','More clues','textarea'));
      article.append(details); const bank=create('p'); bank.className='spell-editor-bank'; bank.setAttribute('aria-label','Preview letter bank'); article.append(bank);
      article.addEventListener('dragstart', event => { if (event.target.closest('input,textarea,select,button')) { event.preventDefault(); return; } dragIndex=index; event.dataTransfer.effectAllowed='move'; event.dataTransfer.setData('text/plain',String(index)); });
      article.addEventListener('dragover', event => event.preventDefault()); article.addEventListener('drop',event => { event.preventDefault(); if (dragIndex !== null && dragIndex !== index) { entries.splice(index,0,entries.splice(dragIndex,1)[0]); dragIndex=null; render(); } }); parts.canvas.append(article);
    }); sync();
  }
  form.querySelectorAll('[name^="manual_"]').forEach(control => { if(control !== source) control.addEventListener('change',()=> { entries.forEach(entry=>delete entry.hidden); sync(); }); });
  form.addEventListener('submit', async event => {
    if (validatedVersion === version) { source.value = JSON.stringify(entries); return; }
    event.preventDefault(); if (submitting) return;
    submitting = true; clearTimeout(previewTimer);
    try { await preview(); if (validatedVersion === version) form.requestSubmit(event.submitter); }
    finally { submitting = false; }
  });
  render();
};
