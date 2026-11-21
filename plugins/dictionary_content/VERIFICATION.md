# English Dictionary Expansion Verification

The English WordNet content pack was installed on the live Puzzary service on
2026-10-07 after an isolated full-import test and a PostgreSQL database backup.

| Measure | Before | After |
| --- | ---: | ---: |
| Dictionary records | 432 | 5,017 |
| Distinct normalized active words | 415 | 5,000 |
| Definitions | 438 | 12,257 |
| Word banks | 55 | 100 |

The 17 pre-existing case-only aliases were preserved to avoid disrupting their
references. No new normalized duplicate words were inserted. Original word
fields, definitions, bans, archive flags, and all 55 banks were checked for
preservation inside the import transaction before commit.

The pack added 4,585 words, 11,819 definitions, and 45 automatic banks. Eligible
existing words also received additional distinct meanings; original definitions
were not rewritten. 4,012 words covered by the pack have multiple active
definitions after the merge. Every imported sense has a part of speech,
definition-level topics, at least two clue steps, and source provenance. Some
WordNet wording and less common senses will benefit from human editorial review.

Verification included:

- Preview without mutations, full merge and repeated import in isolated SQLite.
- Foreign-key enforcement, original-content preservation and checksum rejection.
- Live readback of every imported word, definition, topic and clue sequence.
- A live repeat-import preview showing zero new words or definitions.
- In-memory generation of a 10-word Word Search, 10-answer Crossword, Word
  Pyramid and Spell It against live data, without creating production puzzles.
- Five different seeds yielding five distinct five-row anagram-plus-one pyramids.

The larger library exposed an existing admin-page query bottleneck: tag usage
was calculated by loading four relationships for every tag. A separately tested
query optimization uses four aggregate queries and batched dictionary
relationship loading, with two aggregate bank-count queries instead of loading
every matching entry for list counts. It retains matching rules and usage counts.
The follow-up performance fix was deployed after the operator reported slow
pages. Admin sections now load only the data they need; dictionary lists show
100 searchable entries per page, and tag lists show 200 with search and type
filters. Word-bank counts are resolved using two aggregate SQL queries. Library
filters include only tags attached to visible puzzles, rather than every
definition clue in the dictionary. Multi-bank generation shares a single loaded
dictionary across its automatic banks.

Live request checks measured roughly 0.10 seconds for the library, 0.02 seconds
for generation, 0.17 seconds for the dictionary, 0.16 seconds for word banks,
0.09 seconds for tags and 0.06 seconds for users. The dashboard was about 2.9
seconds. Measurements are local service responses, not guarantees of latency
through a public tunnel. Dictionary counts remained unchanged after deployment.

See the [content pack](content_packs/english-wordnet-5000-v1/README.md) for
licenses, attribution, import and rebuild instructions.
