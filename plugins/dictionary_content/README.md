# English Dictionary Content

This official content package owns the licensed English dictionary expansion
used by word-based Puzzary modules. It is distributed independently from
Puzzary core so the data, provenance, build tools, and documentation have one
canonical home.

The package contains `english-wordnet-5000-v1`, including its checksummed JSON
batches and complete upstream license notices. Installing the package makes the
pack discoverable through Puzzary's plugin package interface. It never silently
falls back to data bundled in core.

The pack is optional. Existing imported dictionary records continue to work if
the package is missing or disabled; installing it is required to perform a new
verified import or rebuild. See the pack README for import, rebuild, and
verification commands.
