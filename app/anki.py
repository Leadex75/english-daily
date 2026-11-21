from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

MODEL_NAME = "English Daily Phrase"
MODEL_ID = 2067318401
DECK_NAME = "English Daily"
DECK_ID = 1608233901
FIELDS = ("Front", "Back", "Example", "Source", "Level", "Language", "Date", "Guid")
FNV_SEEDS = (2166136261, 2654435761, 2246822519, 3266489917)

MODEL_CSS = """
.card { font-family:Arial, sans-serif; font-size:18px; text-align:center; color:#23221f; background:#fbfaf7; }
.ed-front { font-size:26px; font-weight:700; }
.ed-source, .ed-example, .ed-meta { color:#635f58; font-size:13px; margin-top:12px; }
.ed-back { font-size:21px; margin-top:14px; }
hr#answer { border:0; border-top:1px solid #8c887e; margin:18px 0; }
"""


def stable_guid(value: str) -> str:
    text = str(value or "")
    parts = []
    for seed in FNV_SEEDS:
        number = seed & 0xFFFFFFFF
        for byte in text.encode("utf-8"):
            number ^= byte
            number = (number * 16777619) & 0xFFFFFFFF
        parts.append(f"{number:08x}")
    return "".join(parts)


def stable_int(value: str) -> int:
    return int(hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:8], 16)


def anki_html(value: Any) -> str:
    text = str(value or "").replace("<br/>", "\n").replace("<br>", "\n")
    return "<br>".join(html.escape(line) for line in text.splitlines())


def normalize_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        entries = value
    elif isinstance(value, dict):
        entries = value.get("items") or value.get("glossary") or value.get("notes") or []
    else:
        entries = []
    return [entry for entry in entries if isinstance(entry, dict)]


def build_note(entry: dict[str, Any], lang: str = "en", day: str = "") -> dict[str, Any]:
    front = str(entry.get("text") or entry.get("expression") or "").strip()
    meaning_fr = str(entry.get("meaning_fr") or "").strip()
    meaning = str(entry.get("meaning") or "").strip()
    back = " — ".join(part for part in (meaning_fr, meaning) if part)
    example = str(entry.get("example") or "").strip()
    key = str(entry.get("key") or entry.get("guid_hash") or "").strip()
    note_date = str(day or entry.get("learned_at") or "").strip()
    kind = str(entry.get("type") or entry.get("kind") or "phrase").strip()
    level = str(entry.get("level") or "").strip()
    source = str(entry.get("source") or "English Daily").strip()
    guid = stable_guid("|".join((lang, key, front, back, example)))
    tags = ["english-daily", f"lang-{lang}", f"kind-{kind}"]
    if note_date:
        tags.append(f"date-{note_date}")
    if level:
        tags.append(f"level-{level.lower()}")
    fields = {
        "Front": anki_html(front),
        "Back": anki_html(back),
        "Example": anki_html(example),
        "Source": anki_html(source),
        "Level": anki_html(level),
        "Language": anki_html(lang),
        "Date": anki_html(note_date),
        "Guid": guid,
    }
    return {
        "guid": guid,
        "note_id": int(guid[:12], 16),
        "model_name": MODEL_NAME,
        "deck_name": DECK_NAME,
        "key": key,
        "fields": fields,
        "tags": sorted(set(tags)),
    }


def build_notes(entries: Any, lang: str = "en", day: str = "") -> list[dict[str, Any]]:
    notes = [build_note(entry, lang=lang, day=day) for entry in normalize_entries(entries)]
    unique = {note["guid"]: note for note in notes if note["fields"]["Front"]}
    return [unique[key] for key in sorted(unique)]


def anki_connect_note(note: dict[str, Any], deck_name: str | None = None) -> dict[str, Any]:
    deck = deck_name or note.get("deck_name") or DECK_NAME
    return {
        "deckName": deck,
        "modelName": note.get("model_name") or MODEL_NAME,
        "fields": dict(note["fields"]),
        "tags": list(note.get("tags") or []),
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck",
            "duplicateScopeOptions": {
                "deckName": deck,
                "checkChildren": False,
                "checkAllModels": False,
            },
        },
    }


def load_entries_file(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    return normalize_entries(payload)


def write_apkg(notes: list[dict[str, Any]], output: str | Path, lang: str = "en", deck_name: str | None = None) -> Path:
    import genanki

    deck = deck_name or DECK_NAME
    model = genanki.Model(
        MODEL_ID,
        MODEL_NAME,
        fields=[{"name": name} for name in FIELDS],
        templates=[{
            "Name": "English Daily phrase",
            "qfmt": '<div class="ed-front">{{Front}}</div><div class="ed-source">{{Source}}</div>',
            "afmt": '{{FrontSide}}<hr id="answer"><div class="ed-back">{{Back}}</div>{{#Example}}<div class="ed-example">{{Example}}</div>{{/Example}}<div class="ed-meta">{{Level}} · {{Language}} · {{Date}}</div>',
        }],
        css=MODEL_CSS,
    )
    package_deck = genanki.Deck(stable_int(f"{lang}:{deck}"), deck)
    for note in notes:
        package_deck.add_note(genanki.Note(
            guid=note["note_id"],
            model=model,
            fields=[note["fields"][name] for name in FIELDS],
            tags=note["tags"],
        ))
    target = Path(output)
    if not target.is_absolute():
        target = Path.cwd() / target
    target.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(package_deck).write_to_file(str(target))
    return target
