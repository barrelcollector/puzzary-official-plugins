"""Snapshot, validate, merge and verify a licensed dictionary pack in the app runtime."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from app.database import SessionLocal
from app.models import AppSetting, DictionaryDefinition, DictionaryWord, PuzzleTag, WordBank


def key(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def signature(definition, pos):
    return (" ".join(definition.lower().split()), " ".join(pos.lower().split()))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def word_query():
    return select(DictionaryWord).order_by(DictionaryWord.id).options(selectinload(DictionaryWord.tags),
        selectinload(DictionaryWord.definitions).selectinload(DictionaryDefinition.tags))


def snapshot(db):
    words = list(db.scalars(word_query()))
    banks = list(db.scalars(select(WordBank).options(selectinload(WordBank.tags), selectinload(WordBank.word_links))))
    return {"words": [w.word for w in words], "protected_words": {
        str(w.id): digest([w.word, w.display_text, w.clue, w.part_of_speech, w.properties, w.archived_at, w.banned_at])
        for w in words}, "protected_definitions": {
        str(d.id): digest([d.word_id, d.definition, d.part_of_speech, d.example, d.source, d.position,
                          d.properties, d.archived_at, sorted(t.id for t in d.tags)])
        for w in words for d in w.definitions}, "protected_banks": {
        str(b.id): digest([b.name, b.slug, b.category_id, b.description, b.payload, b.archived_at,
                          sorted(t.id for t in b.tags), sorted((l.word_id, l.definition_id, l.position) for l in b.word_links)])
        for b in banks}}


def load_pack(directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    items = []
    for batch in manifest["batches"]:
        path = directory / batch["file"]
        assert path.parent.resolve() == directory.resolve() and path.suffix == ".json"
        content = path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == batch["sha256"], f"Corrupted batch: {path}"
        items.extend(json.loads(content)["items"])
    assert len(items) == manifest["pack_words"]
    assert len({key(item["word"]) for item in items}) == len(items), "Duplicate headwords"
    for item in items:
        assert re.fullmatch(r"[a-z]{3,14}", item["word"])
        assert 1 <= len(item["definitions"]) <= 3
        seen = set()
        for definition in item["definitions"]:
            sig = signature(definition["definition"], definition["part_of_speech"])
            assert sig not in seen
            seen.add(sig)
            assert definition["topics"] and len(definition["clues"]) >= 2
            assert len(definition["definition"]) >= 12
            assert definition["properties"]["wordnet_synset"]
            assert definition["properties"].get("license_notice"), "Missing WordNet notice"
            assert definition["part_of_speech"] in {"Noun", "Verb", "Adjective", "Adverb"}
            assert not re.search(r"\b" + re.escape(item["word"]) + r"\b", definition["definition"], re.I)
    return manifest, items


def merge(db, directory, apply):
    manifest, items = load_pack(directory)
    if apply and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(5000432)"))
    before = snapshot(db)
    words = {key(w.word): w for w in db.scalars(word_query())}
    legacy_aliases = len(before["words"]) - len(words)
    new_count = sum(item["word"] not in words for item in items)
    projected = len(words) + new_count
    assert projected >= manifest["target_words"], "Dictionary changed; rebuild the pack against a fresh snapshot"
    tags = {(tag.tag_type, tag.name): tag for tag in db.scalars(select(PuzzleTag))}
    slugs = {tag.slug for tag in tags.values()}

    def tag(kind, name):
        pair = (kind, name)
        if pair not in tags:
            slug = re.sub(r"[^a-z0-9]+", "-", (kind + " " + name).lower()).strip("-")[:72]
            base, suffix = slug, 2
            while slug in slugs:
                slug = f"{base}-{suffix}"
                suffix += 1
            slugs.add(slug)
            tags[pair] = PuzzleTag(tag_type=kind, name=name, slug=slug)
            db.add(tags[pair])
        return tags[pair]

    added_words = added_definitions = duplicates = 0
    pack_id = manifest["pack_id"]
    license_properties = {
        "content_pack": pack_id, "attribution": "Princeton WordNet 3.0; wordfreq 3.1.1 by Robyn Speer (Copyright 2022)",
        "selection_license": "CC-BY-SA-4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "source_notice_ref": "dictionary_pack_" + pack_id,
    }
    for item in items:
        word = words.get(item["word"])
        if word is None:
            added_words += 1
            if apply:
                word = DictionaryWord(word=item["word"], display_text=item["display_text"],
                    clue="", part_of_speech=item["part_of_speech"], properties={**item["properties"], **license_properties})
                word.tags = [tag("Source", "WordNet English Expansion"), tag("Language", "English"),
                             tag("Difficulty", item["properties"]["difficulty"])]
                db.add(word)
                words[item["word"]] = word
        signatures = {signature(d.definition, d.part_of_speech) for d in word.definitions} if word else set()
        for entry in item["definitions"]:
            sig = signature(entry["definition"], entry["part_of_speech"])
            if sig in signatures:
                duplicates += 1
                continue
            signatures.add(sig)
            added_definitions += 1
            if not apply:
                continue
            definition = DictionaryDefinition(word=word, definition=entry["definition"],
                part_of_speech=entry["part_of_speech"], example=entry["example"], source="Princeton WordNet 3.0",
                position=max((d.position for d in word.definitions), default=-1) + 1,
                properties={**entry["properties"], "selection_license": "CC-BY-SA-4.0"})
            definition.tags = [tag("Part of Speech", entry["part_of_speech"]), tag("Source", "WordNet English Expansion")]
            definition.tags.extend(tag("Topic", topic) for topic in entry["topics"])
            # Long clues remain in properties, avoiding tag-column truncation.
            if len(entry["clues"][0]) <= 120:
                definition.tags.extend(tag("Clue", clue) for clue in entry["clues"] if len(clue) <= 120)
            db.add(definition)
    banks_added = 0
    if apply:
        notice_key = "dictionary_pack_" + pack_id
        notice = db.scalar(select(AppSetting).where(AppSetting.key == notice_key))
        notice_value = json.dumps({"manifest": manifest, "licenses": {
            path.name: path.read_text(encoding="utf-8") for path in (directory / "licenses").iterdir()}}, sort_keys=True)
        if notice is None:
            db.add(AppSetting(key=notice_key, value=notice_value))
        else:
            assert notice.value == notice_value, "Source provenance changed"
        source_tag = tag("Source", "WordNet English Expansion")
        desired = [("Expanded English Dictionary", "expanded-english-dictionary", source_tag)]
        topic_counts = Counter(topic for item in items for entry in item["definitions"] for topic in entry["topics"])
        for topic, count in sorted(topic_counts.items()):
            if count >= 15:
                slug = "expanded-" + re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
                desired.append(("Expanded " + topic, slug, tag("Topic", topic)))
        existing_banks = {b.slug: b for b in db.scalars(select(WordBank))}
        for name, slug, bank_tag in desired:
            if slug in existing_banks:
                assert (existing_banks[slug].payload or {}).get("content_pack") == pack_id, "Bank slug collision"
                continue
            bank = WordBank(name=name, slug=slug, description="Sense-specific automatic bank from the English expansion.",
                payload={"mode": "automatic", "content_pack": pack_id, "license": "CC-BY-SA-4.0"})
            bank.tags = [bank_tag]
            db.add(bank)
            banks_added += 1
        db.flush()
        after = snapshot(db)
        for section in ("protected_words", "protected_definitions", "protected_banks"):
            assert all(after[section].get(id_) == value for id_, value in before[section].items()), f"Changed existing data: {section}"
        assert len({key(word) for word in after["words"]}) == projected
        assert len(after["words"]) == projected + legacy_aliases
        db.commit()
    return {"apply": apply, "before_words": len(before["words"]), "after_words": projected + legacy_aliases,
            "unique_words": projected, "pre_existing_case_aliases_preserved": legacy_aliases,
            "added_words": added_words, "added_definitions": added_definitions,
            "duplicate_definitions_skipped": duplicates, "automatic_banks_added": banks_added,
            "existing_content_preserved": True}


def verify(db, directory):
    manifest, items = load_pack(directory)
    rows = list(db.scalars(word_query()))
    words = {key(w.word): w for w in rows}
    checked = definitions = multi = 0
    active = [w for w in words.values() if w.archived_at is None and w.banned_at is None]
    assert len(active) >= manifest["target_words"], "Active dictionary below target"
    for item in items:
        word = words[item["word"]]
        signatures = {signature(d.definition, d.part_of_speech): d for d in word.definitions}
        for entry in item["definitions"]:
            definition = signatures[signature(entry["definition"], entry["part_of_speech"])]
            if (definition.properties or {}).get("content_pack") != manifest["pack_id"]:
                continue  # A pre-existing identical definition was intentionally preserved.
            assert definition.archived_at is None
            assert {t.name for t in definition.tags if t.tag_type == "Topic"} >= set(entry["topics"])
            assert len(definition.properties["clues"]) >= 2 and definition.properties["license_notice"]
            definitions += 1
        checked += 1
        multi += len([d for d in word.definitions if d.archived_at is None]) > 1
    return {"words": len(rows), "unique_words": len(words), "active_unique_words": len(active),
            "definitions": sum(len(w.definitions) for w in rows), "pack_words_verified": checked,
            "pack_definitions_verified": definitions, "pack_words_with_multiple_definitions": multi,
            "word_banks": len(list(db.scalars(select(WordBank)))), "pack_id": manifest["pack_id"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "preview", "apply", "verify"))
    parser.add_argument("--pack", type=Path)
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "snapshot":
            result = snapshot(db)
        elif args.command == "verify":
            result = verify(db, args.pack)
        else:
            result = merge(db, args.pack, args.command == "apply")
        print(json.dumps(result, indent=2))
