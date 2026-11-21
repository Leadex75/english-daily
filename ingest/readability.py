from __future__ import annotations

import functools
import re
from typing import Any

import textstat
import wordfreq

from app.db import default_language, level_config, load_config, normalize_language

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
CATEGORIES = ["news", "culture", "history"]
KINDS = ["text", "audio"]
_WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def norm(value: float, low: float, high: float) -> float:
    """Linear clamp of value into [0, 1] over the [low, high] band."""
    if high == low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


@functools.lru_cache(maxsize=100_000)
def _zipf(word: str, lang: str = "en") -> float:
    try:
        return wordfreq.zipf_frequency(word, lang)
    except Exception:
        return wordfreq.zipf_frequency(word, "en")


def rare_word_ratio(text: str, lang: str = "en") -> float:
    total = 0
    rare = 0
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        for match in _WORD_RE.finditer(sentence):
            token = match.group(0)
            if token[0].isupper() and match.start() > 0:
                continue  # capitalized mid-sentence token: treat as a proper noun
            total += 1
            if _zipf(token.lower(), lang) < 4.0:
                rare += 1
    return rare / total if total else 0.0


def metrics(text: str, lang: str = "en") -> dict[str, float]:
    clean = (text or "").strip()
    words = _WORD_RE.findall(clean)
    if not clean or not words:
        return {"fk_grade": 0.0, "avg_sentence_len": 0.0, "rare_word_ratio": 0.0, "score": 0.0}
    sentences = max(1, textstat.sentence_count(clean))
    fk_grade = float(textstat.flesch_kincaid_grade(clean))
    avg_sentence_len = len(words) / sentences
    rare = rare_word_ratio(clean, lang)
    score = (
        0.45 * norm(fk_grade, 1, 16)
        + 0.25 * norm(avg_sentence_len, 6, 30)
        + 0.30 * norm(rare, 0.02, 0.25)
    )
    return {
        "fk_grade": round(fk_grade, 3),
        "avg_sentence_len": round(avg_sentence_len, 3),
        "rare_word_ratio": round(rare, 4),
        "score": round(score, 4),
    }


def classify(
    score: float, thresholds: dict[str, float] | None = None, lang: str | None = None
) -> str:
    config = load_config() if thresholds is None or lang is None else None
    limits = thresholds or (level_config(config, lang)[0] if config else {})
    for level in LEVELS[:-1]:
        if score < float(limits[level]):
            return level
    return "C2"


def clamp_level(level: str, low: str, high: str) -> str:
    if low not in LEVELS or high not in LEVELS:
        return level
    return LEVELS[min(max(LEVELS.index(level), LEVELS.index(low)), LEVELS.index(high))]


def band_center(
    level: str, thresholds: dict[str, float] | None = None, lang: str | None = None
) -> float:
    config = load_config() if thresholds is None or lang is None else None
    limits = thresholds or (level_config(config, lang)[0] if config else {})
    index = LEVELS.index(level)
    lower = 0.0 if index == 0 else float(limits[LEVELS[index - 1]])
    upper = 1.0 if index == len(LEVELS) - 1 else float(limits[level])
    return (lower + upper) / 2


def level_for_source(
    text: str | None,
    low: str,
    high: str,
    thresholds: dict[str, float] | None = None,
    min_summary_words: int = 60,
    lang: str | None = None,
) -> tuple[dict[str, float], str, str]:
    """Return (metrics, level, method) using the deterministic fusion rules."""
    computed_source = low == "computed" or high == "computed"
    words = _WORD_RE.findall(text or "")
    usable = len(words) >= min_summary_words
    if not usable:
        if computed_source:
            fallback = "B1"
            return metrics(""), fallback, "source"
        middle = LEVELS[(LEVELS.index(low) + LEVELS.index(high)) // 2]
        return metrics(""), middle, "source"
    values = metrics(text or "", lang or "en")
    computed = classify(values["score"], thresholds, lang)
    if computed_source:
        return values, computed, "computed"
    return values, clamp_level(computed, low, high), "blend"


SAMPLES = [
    ("A1 sample", "I am Tom. I live in a small town. My sister has a cat. We like to play in the park every day."),
    (
        "B1 sample",
        "Last summer we travelled to a small village by the sea where our grandparents used to live. The train "
        "was delayed, so we spent the afternoon walking through the narrow streets and talking to local people. "
        "In the evening we watched the sun set over the water and tried a traditional fish dish that everyone "
        "recommended.",
    ),
    (
        "C2 sample",
        "The epistemological ramifications of such an ostensibly innocuous amendment are far from negligible; indeed, "
        "they precipitate a reconceptualisation of the tacit assumptions underpinning the entire juridical framework. "
        "Consequently, notwithstanding the superficial plausibility of the contrary contention, the proposed "
        "instrument would inevitably engender a proliferation of unforeseen and mutually incompatible obligations.",
    ),
]


def self_test() -> None:
    config = load_config()
    thresholds, _ = level_config(config, default_language(config))
    print("Readability self-test (deterministic, no LLM)")
    for label, text in SAMPLES:
        values = metrics(text)
        print(
            f"  {label:12s} fk={values['fk_grade']:5.1f} "
            f"avg_sent={values['avg_sentence_len']:5.1f} "
            f"rare={values['rare_word_ratio']:.3f} "
            f"score={values['score']:.3f} -> {classify(values['score'], thresholds)}"
        )


if __name__ == "__main__":
    self_test()
