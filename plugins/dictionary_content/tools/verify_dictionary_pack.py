"""Exercise the full pack against an isolated SQLite database, never production."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from app.database import Base
from app.models import DictionaryDefinition, DictionaryWord, WordBank, WordBankWord

spec = importlib.util.spec_from_file_location("pack_manager", Path(__file__).with_name("manage_dictionary_pack.py"))
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


def run(pack, existing):
    manifest, items = manager.load_pack(pack)
    keys = json.loads(existing.read_text(encoding="utf-8-sig"))["words"]
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def constraints(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        for word in keys:
            db.add(DictionaryWord(word=word, display_text=word, clue="Keep this custom clue", properties={"custom": True}))
        db.flush()
        word = db.scalar(select(DictionaryWord))
        definition = DictionaryDefinition(word=word, definition="Keep this existing definition", part_of_speech="Noun", position=0)
        db.add(definition)
        db.flush()
        bank = WordBank(name="Keep manual bank", slug="keep-manual-bank", payload={"mode": "manual"})
        bank.word_links = [WordBankWord(word=word, definition=definition, position=0)]
        db.add(bank)
        db.commit()
        baseline = manager.snapshot(db)
        preview = manager.merge(db, pack, False)
        assert manager.snapshot(db) == baseline, "Preview modified database"
        applied = manager.merge(db, pack, True)
        assert applied["added_words"] == manifest["new_words"]
        report = manager.verify(db, pack)
        assert report["active_unique_words"] == manifest["target_words"]
        repeated = manager.merge(db, pack, True)
        assert repeated["added_words"] == repeated["added_definitions"] == repeated["automatic_banks_added"] == 0
        # A modified batch must fail before any mutation.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text(json.dumps(manifest))
            (root / manifest["batches"][0]["file"]).write_text('{"items":[]}')
            try:
                manager.merge(db, root, True)
                raise RuntimeError("Tampered pack accepted")
            except AssertionError as error:
                assert "Corrupted batch" in str(error)
        print(json.dumps({"preview": preview, "apply": applied, "verify": report,
                          "idempotent": True, "preservation": True, "tamper_rejection": True}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--existing", type=Path, required=True)
    args = parser.parse_args()
    run(args.pack, args.existing)
