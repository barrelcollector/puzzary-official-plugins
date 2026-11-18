(function () {
  const grid = document.querySelector(".word-grid.interactive");
  if (!grid) return;

  const wordList = document.getElementById("word-list");
  const status = document.getElementById("word-search-status");
  const penaltyStatus = document.getElementById("word-search-penalty");
  const checkButton = document.getElementById("word-search-check");
  const clearGuessesButton = document.getElementById("word-search-clear-guesses");
  const revealButton = document.getElementById("reveal-solution");
  const words = new Set((grid.dataset.words || "").split(",").map((word) => word.trim().toUpperCase()).filter(Boolean));
  const found = new Set((grid.dataset.foundWords || "").split(",").map((word) => word.trim().toUpperCase()).filter(Boolean));
  const progressUrl = grid.dataset.progressUrl;
  const autoConfirm = grid.dataset.autoConfirm !== "false";
  const penaltyMode = grid.dataset.penaltyMode || "none";
  const penaltyScope = grid.dataset.penaltyScope || "individual";
  const attemptLimit = Number(grid.dataset.attemptLimit || 3);
  const minimumSelectionLength = Math.min(2, ...Array.from(words, word => word.length));
  const remote = window.PuzzaryGroup || window.PuzzarySolo;
  const cells = Array.from(grid.querySelectorAll("button[data-letter]"));
  const cellsByCoord = new Map(cells.map((cell) => [`${cell.dataset.x},${cell.dataset.y}`, cell]));
  cells.forEach(cell => { cell.dataset.key = `${cell.dataset.x},${cell.dataset.y}`; });
  let placements = [];
  let dragging = false;
  let activePointerId = null;
  let startCell = null;
  let lastCell = null;
  let keyboardStartCell = null;
  let selected = [];
  let guesses = [];
  let rejectedGuesses = [];
  let celebrationReady = false;
  let suppressCelebration = false;
  let soundedFound = new Set(found);
  let penaltyLocked = false;
  let initialPenalty = {};

  try {
    initialPenalty = JSON.parse(grid.dataset.initialPenalty || "{}");
  } catch (_error) {
    initialPenalty = {};
  }

  function renderPenalty(state = {}) {
    const penalty = state.current_penalty || state.penalty || initialPenalty || {};
    const feedback = state.last_selection_feedback || "";
    penaltyLocked = Boolean(penalty.locked);
    grid.classList.toggle("penalty-locked", penaltyLocked);
    cells.forEach(cell => cell.setAttribute("aria-disabled", penaltyLocked ? "true" : "false"));
    if (!penaltyStatus) return;
    const parts = [];
    if (penaltyMode === "mistake_counter") parts.push(`Mistakes: ${Number(penalty.mistakes || 0)}`);
    if (penaltyMode === "score_deduction") parts.push(`Score: ${Number(penalty.score ?? 100)} (-${Number(penalty.score_deduction || 0)})`);
    if (penaltyMode === "time_penalty") parts.push(`Time penalty: ${Number(penalty.time_penalty_seconds || 0)} seconds`);
    if (penaltyMode === "limited_attempts") parts.push(`Incorrect attempts remaining: ${Number(penalty.attempts_remaining ?? attemptLimit)}`);
    if (parts.length && window.PuzzaryGroup) parts.push(penaltyScope === "group" ? "shared by group" : "your count");
    if (feedback) parts.push(feedback);
    penaltyStatus.textContent = parts.join(". ");
    penaltyStatus.classList.toggle("is-hidden", parts.length === 0);
  }

  try {
    placements = JSON.parse(grid.dataset.placements || "[]");
  } catch (_error) {
    placements = [];
  }

  const placementsByWord = new Map(
    placements.map((placement) => [String(placement.word || "").toUpperCase(), placement])
  );

  function syncFoundWords() {
    const newFind = [...found].some(word => !soundedFound.has(word));
    soundedFound = new Set(found);
    if (newFind && celebrationReady && !suppressCelebration && found.size < words.size) {
      window.PuzzarySounds?.progress();
    }
    wordList.querySelectorAll("[data-word]").forEach((item) => {
      item.classList.toggle("found", found.has(item.dataset.word.toUpperCase()));
    });
    if (status) {
      status.textContent = found.size === words.size
        ? "All words found."
        : `${found.size} of ${words.size} words found.`;
    }
    if (!suppressCelebration && celebrationReady && found.size === words.size && window.PuzzaryCelebrate) {
      window.PuzzaryCelebrate.complete();
    }
  }

  function confirmWord(word) {
    if (!word || !words.has(word)) return;
    found.add(word);
    markStoredWord(word);
    syncFoundWords();
    saveProgress();
  }

  function saveProgress() {
    if (window.PuzzaryGroup) { window.PuzzaryGroup.save(); return; }
    if (window.PuzzarySolo) { window.PuzzarySolo.action('patch'); return; }
    if (!progressUrl) return;
    window.fetch(progressUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ found_words: Array.from(found).sort() }),
    }).catch(() => {
      if (status) status.textContent = "Progress could not be saved.";
    });
  }

  function cellsForPlacement(placement) {
    if (!placement || !placement.start || !placement.direction || !placement.word) return [];
    const [x, y] = placement.start;
    const [dx, dy] = placement.direction;
    const line = [];
    for (let i = 0; i < placement.word.length; i += 1) {
      const cell = cellsByCoord.get(`${x + dx * i},${y + dy * i}`);
      if (cell) line.push(cell);
    }
    return line;
  }

  function coordsForPlacement(placement) {
    return cellsForPlacement(placement).map((cell) => `${cell.dataset.x},${cell.dataset.y}`);
  }

  function sameCoordSet(first, second) {
    if (first.length !== second.length) return false;
    const firstSet = new Set(first);
    if (firstSet.size !== second.length) return false;
    return second.every((coord) => firstSet.has(coord));
  }

  function markStoredWord(word) {
    const placement = placementsByWord.get(word);
    cellsForPlacement(placement).forEach((cell) => cell.classList.add("found-cell"));
  }

  function markGimmeCells() {
    cells.filter((cell) => cell.dataset.gimme === "true")
      .forEach((cell) => cell.classList.add("found-cell"));
  }

  function revealSolution() {
    words.forEach((word) => {
      found.add(word);
      markStoredWord(word);
    });
    suppressCelebration = true;
    syncFoundWords();
    suppressCelebration = false;
    if (status) status.textContent = "Solution revealed. Reset the puzzle to start over.";
  }

  function clearSelected() {
    selected.forEach((cell) => cell.classList.remove("selected"));
    selected = [];
  }

  function addCell(cell) {
    if (!cell || selected.includes(cell)) return;
    selected.push(cell);
    cell.classList.add("selected");
  }

  function cellFromPoint(event) {
    const target = document.elementFromPoint(event.clientX, event.clientY);
    return target ? target.closest(".word-grid.interactive button[data-letter]") : null;
  }

  function lineCells(fromCell, toCell) {
    if (!fromCell || !toCell) return [];
    const x1 = Number(fromCell.dataset.x);
    const y1 = Number(fromCell.dataset.y);
    const x2 = Number(toCell.dataset.x);
    const y2 = Number(toCell.dataset.y);
    const dx = Math.sign(x2 - x1);
    const dy = Math.sign(y2 - y1);
    const xDistance = Math.abs(x2 - x1);
    const yDistance = Math.abs(y2 - y1);

    if (!(xDistance === 0 || yDistance === 0 || xDistance === yDistance)) {
      return [fromCell, toCell];
    }

    const length = Math.max(xDistance, yDistance) + 1;
    const line = [];
    for (let i = 0; i < length; i += 1) {
      const cell = cellsByCoord.get(`${x1 + dx * i},${y1 + dy * i}`);
      if (cell) line.push(cell);
    }
    return line;
  }

  function previewSelection(toCell) {
    selected.forEach((cell) => cell.classList.remove("selected"));
    selected = lineCells(startCell, toCell);
    selected.forEach((cell) => cell.classList.add("selected"));
  }

  function selectedWord() {
    return selected.map((cell) => cell.dataset.letter).join("").toUpperCase();
  }

  function selectionKey(cellsToKey) {
    return cellsToKey.map((cell) => `${cell.dataset.x},${cell.dataset.y}`).join("|");
  }

  function sameGuess(first, second) {
    return first.key === second.key || (remote && groupKey(first) === groupKey(second));
  }

  function clearGuesses() {
    guesses = [];
    rejectedGuesses = [];
    clearSelected();
    cells.forEach((cell) => cell.classList.remove("candidate-cell", "miss"));
    syncFoundWords();
    if (remote) saveProgress();
  }

  function addGuess() {
    if (!selected.length) return;
    const key = selectionKey(selected);
    const candidate = {key, cells:selected};
    const existing = guesses.find((guess) => sameGuess(guess, candidate));
    if (existing) {
      existing.cells.forEach((cell) => cell.classList.remove("candidate-cell", "miss"));
      guesses = guesses.filter((guess) => guess !== existing);
      clearSelected();
      if (status) status.textContent = "Selection removed.";
      if (remote) saveProgress();
      return;
    }
    const rejected = rejectedGuesses.find((guess) => sameGuess(guess, candidate));
    if (rejected) {
      rejected.cells.forEach((cell) => cell.classList.remove("selected", "miss"));
      rejectedGuesses = rejectedGuesses.filter((guess) => guess !== rejected);
      clearSelected();
      if (status) status.textContent = "Incorrect selection removed.";
      if (remote) saveProgress();
      return;
    }
    const forward = selectedWord();
    const reverse = forward.split("").reverse().join("");
    const guess = {
      key,
      forward,
      reverse,
      cells: selected.slice(),
    };
    guesses.push(guess);
    guess.cells.forEach((cell) => {
      cell.classList.remove("selected", "miss");
      cell.classList.add("candidate-cell");
    });
    selected = [];
    if (status) status.textContent = `${guesses.length} selection${guesses.length === 1 ? "" : "s"} ready to check.`;
    if (remote) saveProgress();
  }

  function checkGuesses() {
    if (remote) { remote.action('check'); return; }
    if (!guesses.length) {
      if (status) status.textContent = "Make one or more selections first.";
      return;
    }
    let correct = 0;
    const matchedGuessKeys = new Set();
    const newlyCompletedWords = [];
    const singleSelectionWords = new Set();
    const incompleteWords = [];

    guesses.forEach((guess) => {
      const match = words.has(guess.forward) ? guess.forward : words.has(guess.reverse) ? guess.reverse : "";
      if (match) {
        found.add(match);
        newlyCompletedWords.push(match);
        singleSelectionWords.add(match);
        matchedGuessKeys.add(guess.key);
        correct += 1;
      }
    });

    words.forEach((word) => {
      if (found.has(word)) return;
      const placementCoords = coordsForPlacement(placementsByWord.get(word));
      if (!placementCoords.length) return;
      const coveringGuesses = guesses.filter((guess) => (
        guess.cells.some((cell) => placementCoords.includes(`${cell.dataset.x},${cell.dataset.y}`))
      ));
      if (!coveringGuesses.length) return;
      const guessCoords = coveringGuesses.flatMap((guess) => (
        guess.cells.map((cell) => `${cell.dataset.x},${cell.dataset.y}`)
      ));
      if (sameCoordSet(guessCoords, placementCoords)) {
        found.add(word);
        newlyCompletedWords.push(word);
        correct += 1;
        coveringGuesses.forEach((guess) => matchedGuessKeys.add(guess.key));
      } else if (guessCoords.some((coord) => placementCoords.includes(coord))) {
        incompleteWords.push(word);
      }
    });

    guesses.forEach((guess) => {
      guess.cells.forEach((cell) => cell.classList.remove("candidate-cell", "selected", "miss"));
      if (matchedGuessKeys.has(guess.key)) {
        guess.cells.forEach((cell) => cell.classList.add("found-cell"));
      } else {
        guess.cells.forEach((cell) => {
          if (!cell.classList.contains("found-cell")) cell.classList.add("miss");
        });
      }
    });
    newlyCompletedWords.forEach(markStoredWord);
    const wrongCount = guesses.filter((guess) => !matchedGuessKeys.has(guess.key)).length;
    rejectedGuesses = guesses.filter((guess) => !matchedGuessKeys.has(guess.key));
    guesses = [];
    syncFoundWords();
    saveProgress();
    if (status) {
      const remaining = Array.from(words).filter((word) => !found.has(word));
      const parts = [];
      if (correct) {
        parts.push(`${correct} word${correct === 1 ? "" : "s"} completed`);
        const multipart = newlyCompletedWords.filter((word) => !singleSelectionWords.has(word));
        if (multipart.length) parts.push(`${multipart.join(", ")} completed from multiple selections`);
      }
      if (wrongCount) parts.push(`${wrongCount} selection${wrongCount === 1 ? "" : "s"} did not complete a word`);
      if (incompleteWords.length) parts.push(`Incomplete: ${Array.from(new Set(incompleteWords)).join(", ")}`);
      parts.push(remaining.length ? `Remaining: ${remaining.join(", ")}` : "All words found");
      status.textContent = `${parts.join(". ")}.`;
    }
  }

  function finishSelection() {
    if (!selected.length) return;
    if (penaltyLocked) {
      clearSelected();
      if (status) status.textContent = "No incorrect-selection attempts remain.";
      return;
    }
    if (selected.length < minimumSelectionLength) {
      clearSelected();
      if (status) status.textContent = "Selection was too short and was ignored without a penalty.";
      return;
    }
    if (!autoConfirm || remote) {
      addGuess();
      return;
    }
    const forward = selectedWord();
    const reverse = forward.split("").reverse().join("");
    const match = words.has(forward) ? forward : words.has(reverse) ? reverse : "";

    if (match) {
      selected.forEach((cell) => {
        cell.classList.remove("selected");
        cell.classList.add("found-cell");
      });
      selected = [];
      confirmWord(match);
      return;
    }

    selected.forEach((cell) => {
      cell.classList.remove("selected");
      cell.classList.add("miss");
    });
    const missed = selected.slice();
    selected = [];
    window.setTimeout(() => {
      missed.forEach((cell) => cell.classList.remove("miss"));
    }, 350);
  }

  grid.addEventListener("pointerdown", (event) => {
    const cell = event.target.closest("button[data-letter]");
    if (!cell) return;
    event.preventDefault();
    keyboardStartCell = null;
    dragging = true;
    activePointerId = event.pointerId;
    startCell = cell;
    lastCell = cell;
    grid.setPointerCapture(event.pointerId);
    clearSelected();
    addCell(cell);
  });

  grid.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    event.preventDefault();
    const cell = cellFromPoint(event);
    if (!cell || cell === lastCell) return;
    lastCell = cell;
    previewSelection(cell);
  });

  grid.addEventListener("pointerup", (event) => {
    if (activePointerId !== null && event.pointerId !== activePointerId) return;
    event.preventDefault();
    dragging = false;
    activePointerId = null;
    if (grid.hasPointerCapture(event.pointerId)) {
      grid.releasePointerCapture(event.pointerId);
    }
    if (lastCell) {
      previewSelection(lastCell);
    }
    startCell = null;
    lastCell = null;
    finishSelection();
  });

  grid.addEventListener("pointercancel", (event) => {
    dragging = false;
    activePointerId = null;
    startCell = null;
    lastCell = null;
    if (grid.hasPointerCapture(event.pointerId)) {
      grid.releasePointerCapture(event.pointerId);
    }
    clearSelected();
  });

  grid.addEventListener("keydown", (event) => {
    const cell = event.target.closest("button[data-letter]");
    if (!cell) return;
    if (event.key === "Escape" && keyboardStartCell) {
      event.preventDefault();
      keyboardStartCell = null;
      startCell = null;
      clearSelected();
      if (status) status.textContent = "Selection canceled.";
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    if (!keyboardStartCell) {
      clearSelected();
      keyboardStartCell = cell;
      startCell = cell;
      addCell(cell);
      if (status) status.textContent = "Choose the other end of the selection.";
      return;
    }
    startCell = keyboardStartCell;
    previewSelection(cell);
    keyboardStartCell = null;
    startCell = null;
    lastCell = null;
    finishSelection();
  });

  found.forEach(markStoredWord);
  markGimmeCells();
  syncFoundWords();
  renderPenalty({penalty: initialPenalty});
  celebrationReady = true;

  if (checkButton) checkButton.addEventListener("click", checkGuesses);
  if (clearGuessesButton) clearGuessesButton.addEventListener("click", clearGuesses);

  if (revealButton) {
    revealButton.addEventListener("click", () => remote ? remote.action('reveal') : revealSolution());
  }
  function groupKey(guess) {
    const first = guess.cells[0], last = guess.cells.at(-1);
    const ends = [`${first.dataset.x},${first.dataset.y}`,`${last.dataset.x},${last.dataset.y}`].sort();
    return `guess:${ends[0]}:${ends[1]}`;
  }
  remote?.register({
    read() { return Object.fromEntries([...guesses.map(guess => [groupKey(guess),'pending']),...rejectedGuesses.map(guess => [groupKey(guess),'wrong'])]); },
    apply(state) {
      found.clear(); (state.found_words || []).forEach(word => found.add(word));
      cells.forEach(cell => cell.classList.remove('found-cell','candidate-cell','miss'));
      guesses = []; rejectedGuesses = [];
      for (const [key,value] of Object.entries(state.answers || {})) {
        const [,first,last] = key.split(':');
        const line = lineCells(cellsByCoord.get(first),cellsByCoord.get(last));
        if (!line.length) continue;
        const forward = line.map(cell => cell.dataset.letter).join('').toUpperCase();
        const guess = {key:selectionKey(line),cells:line,forward,reverse:[...forward].reverse().join('')};
        if (value === 'wrong') rejectedGuesses.push(guess); else guesses.push(guess);
        line.forEach(cell => cell.classList.add(value === 'wrong' ? 'miss' : 'candidate-cell'));
      }
      (state.confirmed_selections || []).forEach(key => {
        const [,first,last] = key.split(':');
        lineCells(cellsByCoord.get(first),cellsByCoord.get(last)).forEach(cell => cell.classList.add('found-cell'));
      });
      found.forEach(markStoredWord);
      markGimmeCells();
      syncFoundWords();
      if (status && (guesses.length || rejectedGuesses.length)) status.textContent = `${found.size} of ${words.size} words found. ${guesses.length} selections ready to check. ${rejectedGuesses.length} incorrect selections.`;
      renderPenalty(state);
    }
  });
})();
