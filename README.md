# Puzzary official plugins

This repository contains official puzzle packages that can be installed into
Puzzary independently of the core application. Each folder under `plugins/` is
a complete package with its own manifest, Python entrypoint, templates, and
browser assets.

## Available packages

- Cross Equations (`plugins/cross_equations`)
- Crossword (`plugins/crossword`)
- Maze (`plugins/maze`)
- Minesweeper (`plugins/minesweeper`)
- Nonogram (`plugins/nonogram`)
- Spell It (`plugins/spell_it`)
- Sudoku (`plugins/sudoku`)
- Takuzu (`plugins/takuzu`)
- Word Pyramid (`plugins/word_pyramid`)
- Word Search (`plugins/word_search`)

Each package retains the built-in type's stable slug and payload contract, so it
can replace the bundled implementation without invalidating saved puzzles.

## Install

Download a release ZIP and install it with Puzzary's package installer, supplying
the release asset's SHA-256 digest. Restart Puzzary after installing or upgrading
a package. In Docker, packages are persisted under `/data/plugins`.

Packages execute server-side Python and must be treated like application code.
Install only trusted, reviewed releases and pin both the version and digest.

## Package contract

Every package contains `puzzary-plugin.json`. Schema `puzzary.plugin.v1` targets
plugin API version `1`. The entrypoint registers exactly one `PuzzleType` whose
slug matches the manifest. Template folders use the same `puzzle_types/`,
`puzzle_solutions/`, and `puzzle_print/` paths as core.

Run `python scripts/build.py` to validate packages and create release ZIPs in
`dist/`. Builds are deterministic. Every ZIP contains Apache-2.0 `LICENSE` and
`NOTICE` files, and `dist/SHA256SUMS` records all archive digests.

## Compatibility

Official plugin release 0.1.1 targets Puzzary plugin API version 1 and the
Puzzary 0.1.0 public beta line. Each archive can replace the corresponding
bundled fallback without changing saved puzzle slugs or payload contracts.

## License

Puzzary official plugins are licensed under the
[Apache License 2.0](LICENSE). Copyright 2026 Puzzary contributors. See
[NOTICE](NOTICE) for attribution. The license does not grant permission to use
project names or branding beyond describing the origin of the software.

