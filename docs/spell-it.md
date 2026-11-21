# Spell It!

Spell It is a discovered puzzle module (`spell_it`). Single-word puzzles and
ordered series share the same entry model. Select it in the generation wizard,
or choose Spell It in the manual puzzle builder.

## Sources and masking

Generation uses selected word-bank definitions and preserves display spelling,
including phrases, punctuation and spaces. A bank must have enough distinct
words with definitions; it never repeats a word to fill a series. Archived and
banned source entries follow the standard word-bank filters.

Default hidden percentages are 18/30/45/65/80 for Very Easy through Expert,
applied to eligible alphabetic characters. First and last alphabetic characters
are protected unless disabled. Every entry has at least one blank; one- and
two-letter words hide the last letter. Published masks and shuffled banks are
stored, so reloads do not regenerate them. A supplied seed reproduces generation.

## Builder

Add entries directly or select a word and definition from a manual or automatic
bank. Drag entries or change their position number to reorder. Click individual
letters to hide/reveal them; Regenerate Mask creates another arrangement. The
preview validates the exact mask before saving. Each entry can override
difficulty, hidden percentage, edge protection, bank mode, decoy count, hints and
letter-reveal limit. Additional clues accept one clue per line.

## Playing

Type into blanks or select letter tiles. Capitalization is ignored. Arrow keys,
backspace and delete navigate/edit; Enter checks. Fixed punctuation is not
editable. Exact banks contain the missing letters, including repeated letters;
Decoy adds distractors. Both typing and tile selection consume the same inventory,
and removing/replacing letters returns tiles. Off has no inventory restriction;
Hint-triggered supplies a bank only after requesting it.

The extra-letter count is enabled only for Decoy banks. Distractors use letters
absent from the answer when available; explicit bank choices are preserved when
an entry overrides difficulty.

Check Word distinguishes incomplete, incorrect and correct entries. Series
advance after checking each word. Progress, revealed letters and bank activation
survive reloads. Clear Word preserves consumed reveals; Reset Puzzle clears all
progress and restores hint limits. Letter reveals are limited per entry and
enforced server-side. Hidden answers are not embedded in player payloads.
Admin solutions remain permission-gated and collapsed by default.

## API and print

Standard generation, manual creation, export, progress, reset and printing APIs
support this type with the existing account/token permissions. Plugin endpoints:

- `POST /api/spell-it/editor-preview`: creator-owned entries/options to validated
  public/solution preview; requires `puzzles.create`.
- `GET /api/puzzles/{id}/spell-it/progress`: guesses, entry states, available banks
  and hint limits.
- `POST /api/puzzles/{id}/spell-it/attempts`: `{ "answers": { "0:3": "R" } }`.
- `POST /api/puzzles/{id}/spell-it/hint`: entry index, kind `letter` or `bank`, and
  current answers. Clients cannot fabricate reveal ledgers through progress saves.

Web/PDF prints use the stored mask and printable banks, never the hidden solution.
The plugin owns its play/editor scripts, router, templates and progress merger;
these optional contracts leave existing puzzle modules unchanged. Group solve is
not enabled for this module.
