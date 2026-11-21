from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ItemOut(BaseModel):
    id: int
    title: str
    source: str
    source_id: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None
    level: Optional[str] = None
    slot_level: Optional[str] = None
    source_level: Optional[str] = None
    word_count: Optional[int] = None
    duration_sec: Optional[int] = None
    body_text: Optional[str] = None
    audio_url: Optional[str] = None
    description: Optional[str] = None
    license: str = "proprietary"
    attribution: Optional[str] = None
    truncated: bool = False
    guid_hash: Optional[str] = None
    summary: Optional[str] = None
    origin: str = "fresh"
    badges: list[str] = []


class SlotOut(BaseModel):
    text: Optional[ItemOut] = None
    audio: Optional[ItemOut] = None


class PhraseOut(BaseModel):
    date: str
    level: str
    word: dict[str, Any]
    expression: dict[str, Any]


class MetaOut(BaseModel):
    filled: int
    total: int
    origins: dict[str, int] = {}


class DayOut(BaseModel):
    date: str
    level: str
    slots: dict[str, SlotOut]
    phrase: Optional[PhraseOut] = None
    meta: MetaOut
