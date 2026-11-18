(function () {
  const root = document.querySelector(".word-pyramid-play");
  if (!root) return;

  const inputs = Array.from(root.querySelectorAll("input[data-row][data-cell]"));
  const status = document.getElementById("word-pyramid-status");
  const checkButton = document.getElementById("word-pyramid-check");
  const clearButton = document.getElementById("word-pyramid-clear");
  const revealButton = document.getElementById("reveal-solution");
  const rowRevealButtons = Array.from(root.querySelectorAll(".reveal-pyramid-row"));
  const clueButtons = Array.from(root.querySelectorAll(".more-pyramid-clue"));
  const progressUrl = root.dataset.progressUrl;
  const remote = window.PuzzaryGroup || window.PuzzarySolo;
  let saveTimer = null;

  const inputsByRow = new Map();
  inputs.forEach((input) => {
    const rowIndex = Number(input.dataset.row);
    const list = inputsByRow.get(rowIndex) || [];
    list.push(input);
    inputsByRow.set(rowIndex, list);
  });
  inputsByRow.forEach((list) => {
    list.sort((a, b) => Number(a.dataset.cell) - Number(b.dataset.cell));
  });
  function rowAnswer(index) {
    return (inputsByRow.get(index) || [])
      .map((input) => input.value.trim().toUpperCase().replace(/[^A-Z0-9]/g, "") || (remote ? ' ' : ''))
      .join("");
  }

  function currentAnswers() {
    const answers = {};
    inputsByRow.forEach((_list, rowIndex) => {
      if (remote && _list.every(input => input.disabled)) return;
      const value = remote ? rowAnswer(rowIndex).trimEnd() : rowAnswer(rowIndex);
      if (value) answers[String(rowIndex)] = value;
    });
    return answers;
  }

  function saveProgress() {
    if (window.PuzzaryGroup) { window.PuzzaryGroup.save(); return; }
    if (!progressUrl) return;
    window.fetch(progressUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers: currentAnswers() }),
    }).catch(() => {
      if (status) status.textContent = "Progress could not be saved.";
    });
  }

  function queueSave() {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(saveProgress, 250);
  }

  function setStatus(text) {
    if (status) status.textContent = text;
  }

  function rowElement(index) {
    const list = inputsByRow.get(index) || [];
    return list[0] ? list[0].closest(".word-pyramid-row") : null;
  }

  function setRowState(index, state) {
    const row = rowElement(index);
    if (!row) return;
    row.classList.remove("correct", "incorrect");
    if (state) row.classList.add(state);
  }

  function cleanInput(input) {
    if (input.disabled) return;
    input.value = input.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 1);
    setRowState(Number(input.dataset.row), "");
    queueSave();
  }

  function focusRelative(input, direction) {
    const rowInputs = inputsByRow.get(Number(input.dataset.row)) || [];
    const index = rowInputs.indexOf(input);
    const next = rowInputs[index + direction];
    if (next) {
      next.focus();
      next.select();
    }
  }

  function checkPyramid() {
    remote?.action('check');
  }

  inputs.forEach((input) => {
    if (input.disabled) return;
    input.addEventListener("focus", () => input.select());
    input.addEventListener("input", () => {
      cleanInput(input);
      if (input.value) focusRelative(input, 1);
    });
    input.addEventListener("keydown", (event) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (/^[a-zA-Z0-9]$/.test(event.key)) {
        event.preventDefault();
        input.value = event.key;
        cleanInput(input);
        focusRelative(input, 1);
      } else if (event.key === "Backspace" && !input.value) {
        event.preventDefault();
        focusRelative(input, -1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        focusRelative(input, -1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        focusRelative(input, 1);
      }
    });
  });

  if (checkButton) checkButton.addEventListener("click", checkPyramid);

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      inputs.forEach((input) => {
        if (input.disabled) return;
        input.value = "";
        setRowState(Number(input.dataset.row), "");
      });
      setStatus("Pyramid cleared.");
      saveProgress();
    });
  }

  if (revealButton) revealButton.addEventListener("click", () => remote?.action('reveal'));

  rowRevealButtons.forEach((button) => {
    button.addEventListener("click", () => remote?.action('reveal_entry',button.dataset.row));
  });

  clueButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (remote) { remote.action('clue',button.dataset.row); return; }
      const list = button.nextElementSibling;
      if (!list || !list.classList.contains("pyramid-clue-steps")) return;
      const hiddenSteps = Array.from(list.querySelectorAll("small[hidden]"));
      if (!hiddenSteps.length) return;
      list.hidden = false;
      hiddenSteps[0].hidden = false;
      const remaining = hiddenSteps.length - 1;
      button.textContent = remaining ? `More clues (${remaining})` : "No more clues";
      button.disabled = remaining === 0;
    });
  });
  remote?.register({read:currentAnswers,
    scope(answers) { return Object.fromEntries(Object.entries(answers).filter(([key]) => inputsByRow.get(Number(key))?.some(input => !input.disabled))); },
    apply(state) {
      inputsByRow.forEach((list,index) => {
        const value = state.answers[String(index)] || '';
        list.forEach((input,position) => { if (!input.disabled && input.value !== (value[position]?.trim() || '')) input.value = value[position]?.trim() || ''; });
        setRowState(index,state.checked && value ? state.incorrect?.includes(String(index)) ? 'incorrect' : 'correct' : '');
      });
      clueButtons.forEach(button => {
        const list = button.nextElementSibling;
        if (!list) return;
        const count = state.clues?.[button.dataset.row] || 0;
        list.hidden = !count;
        const steps = [...list.querySelectorAll('small')];
        steps.forEach((step,index) => { step.hidden = index >= count; });
        button.disabled = count >= steps.length;
        button.textContent = button.disabled ? 'No more clues' : `More clues (${steps.length-count})`;
      });
      if (state.revealed) setStatus('Solution revealed. Reset the puzzle to start over.');
      else if (state.checked && !(state.incorrect || []).length) { setStatus('Word pyramid complete.'); window.PuzzaryCelebrate?.complete(); }
      else if (state.checked) setStatus('One or more completed rows need another look.');
    }
  });
})();
