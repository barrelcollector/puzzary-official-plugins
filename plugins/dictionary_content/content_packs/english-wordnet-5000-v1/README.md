# English Dictionary Expansion

This pack expands the existing Puzzary library toward 5,000 distinct normalized
English words. It includes up to three useful senses per headword, parts of
speech, sense-specific topic tags, examples where available, and progressive
clues. See `manifest.json` for exact counts, provenance, and batch checksums.

## Attribution and License

Definitions, examples, synonym relationships and semantic categories are adapted
from **Princeton WordNet 3.0**, Copyright 2006 Princeton University. The complete
WordNet license and disclaimer are included in `licenses/WordNet-LICENSE.txt`
and each imported definition's `properties.license_notice`. This project is not
endorsed by Princeton University.

Common-word selection and frequency values use **wordfreq 3.1.1**, by **Robyn
Speer**, Copyright 2022. Retain its complete attribution and upstream notices in
`licenses/wordfreq-NOTICE.md`. Its data is licensed under **CC BY-SA 4.0**;
its code has a separate Apache 2.0 license. The selection, ranking, generated
hints and topic arrangement in this pack are distributed under CC BY-SA 4.0,
with WordNet material retaining its original license. See the bundled licenses.
These data terms do not relicense the application code or existing user content.

Changes: selection of common alphabetic headwords, automated content screening,
selection of distinct senses and parts of speech, context masking, semantic topic
mapping, spelling hints, and Puzzary JSON formatting. AI assistance was used to
develop the builder, import tooling and documentation. This is automatically
screened source material, not 5,000 individually human-reviewed entries. Older
WordNet wording and occasional uncommon meanings may need editorial review.

## Import

The `words-*.json` batches are accepted by the ordinary dictionary import
workflow. For a complete import with typed topic tags, automatic banks, preserved
provenance and verification, run the following in the application runtime after
taking a database backup:

```powershell
python tools/manage_dictionary_pack.py snapshot
python tools/manage_dictionary_pack.py preview --pack content_packs/english-wordnet-5000-v1
python tools/manage_dictionary_pack.py apply --pack content_packs/english-wordnet-5000-v1
python tools/manage_dictionary_pack.py verify --pack content_packs/english-wordnet-5000-v1
```

The merge is transactional and idempotent. It does not modify existing word
fields, definitions, manual banks, archive flags or bans. Existing case-only
aliases are preserved, but no new normalized duplicates are inserted. Reimporting
does not duplicate meanings or banks. Source notices are also retained in the
`dictionary_pack_english-wordnet-5000-v1` application setting.

Automatic banks include **Expanded English Dictionary** and topic banks with at
least 15 matching senses. These banks match definition-level tags, so a bank can
select the relevant meaning of a multi-sense word. Original banks stay untouched.
Long hints stay unabridged in definition properties rather than being truncated
to fit tag names. The full definition is always available in additional clues.

## Rebuild and Test

The builder needs `nltk==3.10.3`, `wordfreq==3.1.1` and the NLTK WordNet 3.0
corpus. Build dependencies are not required in the production application.
`--existing` accepts the saved snapshot JSON from the manager's snapshot command.

```powershell
python tools/build_dictionary_pack.py --existing existing.json --target 5000 --corpus nltk_data --output content_packs/english-wordnet-5000-v1
python tools/verify_dictionary_pack.py --pack content_packs/english-wordnet-5000-v1 --existing existing.json
```

Verification uses an isolated in-memory SQLite database with foreign keys
enabled. It exercises preview, the full merge, content preservation, repeated
import, and corrupted-batch rejection. The production verification additionally
checks every imported word, definition, topic and hint chain.
