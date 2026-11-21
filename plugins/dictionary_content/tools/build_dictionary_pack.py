"""Build a licensed, reproducible English content pack; no server writes."""
import argparse
from collections import Counter
import hashlib
import io
from importlib.metadata import version
from itertools import chain
import json
from pathlib import Path
import re
import tarfile
import urllib.request
import zipfile

PACK_ID = "english-wordnet-5000-v1"
WORDFREQ_NOTICE_COMMIT = "912caf64b657478d1dff1138efdc078947d54bb1"
LICENSE_NOTICE = ""
POS = {"n": "Noun", "v": "Verb", "a": "Adjective", "s": "Adjective", "r": "Adverb"}
TOPICS = {
    "act": "Actions", "animal": "Animals", "artifact": "Objects", "attribute": "Qualities",
    "body": "Anatomy", "cognition": "Ideas and Knowledge", "communication": "Communication",
    "event": "Events", "feeling": "Feelings", "food": "Food and Drink", "group": "Groups",
    "location": "Places", "motive": "Motivation", "object": "Nature", "person": "People",
    "phenomenon": "Natural Phenomena", "plant": "Plants", "possession": "Money and Ownership",
    "process": "Processes", "quantity": "Numbers and Measures", "relation": "Relationships",
    "shape": "Shapes", "state": "States and Conditions", "substance": "Materials",
    "time": "Time", "change": "Change", "competition": "Sports and Competition",
    "consumption": "Eating and Consumption", "contact": "Touch and Contact",
    "creation": "Making Things", "emotion": "Emotions", "motion": "Movement",
    "perception": "Senses", "social": "Social Life", "stative": "Being and Having",
    "weather": "Weather", "all": "Descriptions", "pert": "Related Adjectives", "ppl": "Participles",
}
SPECIAL_TOPICS = {
    "Technology": {"computer", "electronic_equipment", "software", "network", "computer_science"},
    "Tools and Workshop": {"tool", "hand_tool", "power_tool", "fastener"},
    "Kitchen and Cooking": {"kitchen_utensil", "cooking_utensil", "cookware", "cooking"},
    "Clothing": {"clothing", "garment", "footwear", "headdress"},
    "Music": {"music", "musical_instrument", "musical_composition", "musician"},
    "Transport": {"vehicle", "transportation", "travel", "road", "railway"},
    "Buildings and Home": {"building", "room", "furniture", "dwelling"},
    "Games": {"game", "board_game", "puzzle", "plaything"},
    "Art": {"art", "artwork", "painting", "sculpture"},
    "Space and Astronomy": {"celestial_body", "astronomy", "astronomical_unit"},
}
UNSUITABLE = re.compile(
    r"\b(?:sexual|sexually|homosexual\w*|intercourse|genitals?|genitalia|penis|vagina|testicles?|"
    r"pornography|pornographic|masturbat\w*|vulgar|obscene|derogatory|offensive|"
    r"racial slur|fuck\w*|shit\w*|cunt\w*|nigger\w*)\b", re.I
)
EXCLUDED_WORDS = set("ass bastard bitch cock dick tit tits rape rapist negro negros nigger nigga fag faggot cunt shit fuck fucking bullshit asshole blowjob dildo porn sexy sexuality sexual orgasm semen sperm prostitution prostitute erection erotic sodomy homosexual homosexuality queer retard retarded slut whore anal anus buttock breast breasts vagina penis testicle testicles genital genitalia masturbation menstrual menstruation ovary uterine uterus abortion racist racism suicide suicidal cocaine heroin methamphetamine marijuana cannabis tobacco cigarette cigarettes alcohol alcoholic alcoholism booze beer wine vodka whiskey whisky rum gin brandy lager ale liquor drunk drunken".split())


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def mentions(text, word):
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text, re.I))


def safe_definition(synset, word):
    text = clean(synset.definition())
    return 12 <= len(text) <= 1000 and not UNSUITABLE.search(text) and not mentions(text, word)


def topics_for(synset):
    lexname = synset.lexname().split(".")[-1]
    topics = {TOPICS.get(lexname, "Descriptions")}
    ancestors = {lemma.name().lower() for parent in synset.closure(lambda s: s.hypernyms(), depth=12)
                 for lemma in parent.lemmas()}
    ancestors.update(lemma.name().lower() for lemma in synset.lemmas())
    for topic, anchors in SPECIAL_TOPICS.items():
        if ancestors & anchors:
            topics.add(topic)
    return sorted(topics)


def sense(synset, word):
    definition = clean(synset.definition())
    # Keep complete short clauses in typed tags; long definitions stay unabridged in properties.
    primary = definition[:1].upper() + definition[1:]
    if len(primary) > 120:
        clauses = re.split(r"; |\. ", primary)
        primary = next((clause for clause in clauses if 12 <= len(clause) <= 119), primary)
    clues = [primary.rstrip(".") + "."]
    examples = [clean(example) for example in synset.examples() if not UNSUITABLE.search(example)]
    example = next((example for example in examples if mentions(example, word)), "")
    if example:
        masked = re.sub(r"\b" + re.escape(word) + r"\b", "_____", example, flags=re.I)
        clues.append("In context: " + masked)
    synonyms = sorted({lemma.name().replace("_", " ") for lemma in synset.lemmas()
                       if word not in lemma.name().lower() and not UNSUITABLE.search(lemma.name())
                       and len(lemma.name()) <= 30})
    if synonyms:
        clues.append("Similar meaning: " + ", ".join(synonyms[:3]) + ".")
    if len(clues) < 2:
        parents = sorted(synset.hypernyms(), key=lambda parent: parent.name())
        for parent in parents:
            explanation = clean(parent.definition())
            if 15 <= len(explanation) <= 180 and not mentions(explanation, word) and not UNSUITABLE.search(explanation):
                clues.append("Broader meaning: " + explanation + ".")
                break
    # Structural help is the final fallback, never the main clue or sole information.
    if len(clues) < 2:
        clues.append(f"Spelling hint: {len(word)} letters, beginning with {word[0].upper()}.")
    return {"definition": definition, "part_of_speech": POS[synset.pos()], "example": example,
            "clues": list(dict.fromkeys(clues)), "topics": topics_for(synset),
            "properties": {"wordnet_synset": synset.name(), "wordnet_lexname": synset.lexname(),
                           "source_url": "https://wordnet.princeton.edu/", "clues": clues,
                           "license_notice": LICENSE_NOTICE,
                           "license": "WordNet-3.0", "content_pack": PACK_ID}}


def build(existing, target, output, corpus):
    global LICENSE_NOTICE
    import nltk
    from nltk.corpus import wordnet as wn
    from wordfreq import iter_wordlist, zipf_frequency
    assert version("wordfreq") == "3.1.1", "Use the documented wordfreq version"
    nltk.data.path.insert(0, str(corpus))
    with zipfile.ZipFile(corpus / "corpora" / "wordnet.zip") as archive:
        LICENSE_NOTICE = archive.read("wordnet/LICENSE").decode("utf-8")
    existing_keys = {re.sub(r"[^a-z0-9]", "", w.lower()) for w in existing}
    needed = max(0, target - len(existing_keys))
    candidates = []
    considered = set()
    for word in chain(sorted(existing_keys), iter_wordlist("en", wordlist="large")):
        if word in considered:
            continue
        considered.add(word)
        if not re.fullmatch(r"[a-z]{3,14}", word) or word in EXCLUDED_WORDS:
            continue
        synsets = [s for s in wn.synsets(word) if any(l.name() == word for l in s.lemmas())
                   and safe_definition(s, word)]
        if not synsets:
            continue
        synsets.sort(key=lambda s: -sum(lemma.count() for lemma in s.lemmas() if lemma.name() == word))
        unique_senses = {}
        for synset in synsets:
            unique_senses.setdefault((POS[synset.pos()], clean(synset.definition()).lower()), synset)
        synsets = list(unique_senses.values())
        # Prefer distinct parts of speech, then distinct semantic domains, up to three senses.
        selected = []
        for s in synsets:
            if not any(POS[s.pos()] == POS[item.pos()] for item in selected):
                selected.append(s)
        for s in synsets:
            if len(selected) >= 3:
                break
            if not any(s.lexname() == item.lexname() and s.pos() == item.pos() for item in selected):
                selected.append(s)
        if len(selected) < 3:
            for s in synsets:
                if s not in selected:
                    selected.append(s)
                if len(selected) == 3:
                    break
        selected = selected[:3]
        frequency = zipf_frequency(word, "en")
        definitions = [sense(s, word) for s in selected]
        candidates.append({"word": word, "display_text": word, "part_of_speech": definitions[0]["part_of_speech"],
                           "definitions": definitions, "properties": {"content_pack": PACK_ID,
                           "frequency_zipf": frequency, "language": "English", "license": "CC-BY-SA-4.0",
                           "difficulty": "Common" if frequency >= 4.5 else "Intermediate" if frequency >= 3.7 else "Advanced"}})
        if sum(item["word"] not in existing_keys for item in candidates) >= needed:
            break
    assert len({item["word"] for item in candidates} - existing_keys) == needed, "Insufficient usable headwords"
    output.mkdir(parents=True, exist_ok=True)
    licenses = output / "licenses"
    licenses.mkdir(exist_ok=True)
    with zipfile.ZipFile(corpus / "corpora" / "wordnet.zip") as archive:
        (licenses / "WordNet-LICENSE.txt").write_bytes(archive.read("wordnet/LICENSE"))
    with urllib.request.urlopen("https://pypi.org/pypi/wordfreq/3.1.1/json", timeout=60) as response:
        release = json.load(response)
    sdist = next(file for file in release["urls"] if file["packagetype"] == "sdist")
    with urllib.request.urlopen(sdist["url"], timeout=60) as response:
        source = response.read()
    assert hashlib.sha256(source).hexdigest() == sdist["digests"]["sha256"]
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:gz") as archive:
        for filename in ("LICENSE.txt",):
            member = next(m for m in archive.getmembers() if m.name.endswith("/" + filename))
            (licenses / ("wordfreq-" + filename)).write_bytes(archive.extractfile(member).read())
    urls = {"CC-BY-SA-4.0.txt": "https://creativecommons.org/licenses/by-sa/4.0/legalcode.txt",
            "wordfreq-NOTICE.md": f"https://raw.githubusercontent.com/rspeer/wordfreq/{WORDFREQ_NOTICE_COMMIT}/NOTICE.md"}
    for filename, url in urls.items():
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PuzzaryContentBuilder/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            (licenses / filename).write_bytes(response.read())
    # API-sized batches, also usable by the ordinary dictionary import endpoint.
    batches = []
    for offset in range(0, len(candidates), 250):
        filename = f"words-{offset // 250 + 1:02d}.json"
        payload = json.dumps({"items": candidates[offset:offset + 250]}, indent=2, ensure_ascii=True) + "\n"
        assert len(payload.encode()) <= 2_000_000, "Batch exceeds the dictionary source fetch limit"
        (output / filename).write_text(payload, encoding="utf-8", newline="\n")
        batches.append({"file": filename, "sha256": hashlib.sha256(payload.encode()).hexdigest()})
    report = {"pack_id": PACK_ID, "target_words": target, "existing_words": len(existing_keys),
              "pack_words": len(candidates), "new_words": needed,
              "definitions": sum(len(w["definitions"]) for w in candidates),
              "multi_definition_words": sum(len(w["definitions"]) > 1 for w in candidates),
              "topics": dict(sorted(Counter(t for w in candidates for d in w["definitions"] for t in d["topics"]).items())),
              "parts_of_speech": dict(Counter(d["part_of_speech"] for w in candidates for d in w["definitions"])),
              "batches": batches, "license": "CC-BY-SA-4.0; definitions also retain WordNet license",
              "sources": {"definitions": "Princeton WordNet 3.0", "selection": "wordfreq 3.1.1 English large"},
              "wordfreq_sdist_sha256": sdist["digests"]["sha256"],
              "wordfreq_notice_commit": WORDFREQ_NOTICE_COMMIT,
              "nltk_version": nltk.__version__, "content_review": "Automated screening, not individual human review"}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in report.items() if k != "batches"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, required=True, help="JSON snapshot produced by manage_dictionary_pack.py")
    parser.add_argument("--target", type=int, default=5000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    args = parser.parse_args()
    build(json.loads(args.existing.read_text(encoding="utf-8-sig"))["words"], args.target, args.output, args.corpus)
