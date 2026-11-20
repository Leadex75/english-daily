from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ItemOut(BaseModel):
    id: int
    title: str
    source: str
    url: Optional[str] = None
    published_at: Optional[str] = None
    level: Optional[str] = None
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


class SlotOut(BaseModel):
    text: Optional[ItemOut] = None
    audio: Optional[ItemOut] = None


class DayOut(BaseModel):
    date: str
    level: str
    slots: dict[str, SlotOut]
