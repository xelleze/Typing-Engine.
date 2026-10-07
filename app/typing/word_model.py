"""Word frequency and sparse cognitive planning, independent of motor cost."""
from dataclasses import dataclass
from functools import lru_cache
from math import sqrt, exp
from typing import Protocol
from wordfreq import zipf_frequency
import regex
from app.config.typing_profile import TypingProfile

WORD_PATTERN = regex.compile(r"\p{L}[\p{L}\p{M}\p{N}]*(?:['’][\p{L}\p{M}\p{N}]+)*|\p{N}+")
CHUNKS = ("th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
          "the", "ing", "and", "ion", "tion", "ment", "ough", "ould")


class FamiliarityStore(Protocol):
    def seen_count(self, word: str) -> int: ...
    def record(self, word: str, zipf: float) -> None: ...


@lru_cache(maxsize=8192)
def frequency(word: str) -> float:
    return zipf_frequency(word.lower(), "en")


@dataclass(frozen=True)
class WordInfo:
    word: str
    start: int
    end: int
    zipf: float
    rarity: float
    effective_rarity: float
    seen_count: int
    planning_ms: float


def analyze_word(word: str, start: int, profile: TypingProfile,
                 store: FamiliarityStore | None = None) -> WordInfo:
    zipf = frequency(word)
    rarity = max(0., min((5. - zipf) / 4., 1.))
    seen = store.seen_count(word.lower()) if store and zipf < 3.5 else 0
    effective = rarity * exp(-seen / 15.)
    planning = effective * profile.rarity_sensitivity * (
        profile.base_rare_pause + sqrt(max(len(word) - 6, 0)) * profile.length_rare_factor)
    return WordInfo(word, start, start + len(word), zipf, rarity, effective, seen, planning)


def chunk_at(word: str, local_index: int, skill: float = 1.) -> tuple[str, float]:
    """Discount only transitions within a chunk, never entry into it."""
    matches = []
    lower = word.lower()
    for chunk in CHUNKS:
        offset = lower.find(chunk)
        while offset >= 0:
            if offset < local_index < offset + len(chunk):
                bonus = -.04 if len(chunk) == 2 else -.07 if len(chunk) == 3 else -.09
                matches.append((chunk, bonus * skill))
            offset = lower.find(chunk, offset + 1)
    return min(matches, key=lambda item: item[1]) if matches else ("", 0.)
