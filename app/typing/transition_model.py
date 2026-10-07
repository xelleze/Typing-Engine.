"""Cached motor cost; geometry is only one of several contributors."""
from dataclasses import dataclass, asdict
from functools import lru_cache
from math import hypot
from .keyboard_layout import KEYS, get_key


@dataclass(frozen=True)
class Transition:
    distance: float
    same_hand: bool
    same_finger: bool
    alternate_hand: bool
    row_change: int
    repeated_key: bool
    shift_required: bool
    awkward_reach: bool
    score: float

    def details(self):
        return asdict(self)


@lru_cache(maxsize=32768)
def transition(previous: str | None, char: str) -> Transition:
    b = get_key(char)
    if previous is None:
        return Transition(0, False, False, False, 0, False, b.shifted,
                          not b.known, 1.0 + 0.15 * b.shifted + 0.12 * (not b.known))
    a = get_key(previous)
    distance = hypot(a.x - b.x, a.y - b.y)
    same_hand = a.hand == b.hand
    same_finger = same_hand and a.finger == b.finger
    row_change = abs(a.row - b.row)
    repeated = a.x == b.x and a.y == b.y
    awkward = (same_hand and distance > 3.0) or (same_finger and row_change >= 2) or not b.known
    score = (1 + distance * .08 + .30 * same_finger + .10 * same_hand
             - .12 * (not same_hand) + row_change * .08 + .18 * repeated
             + .15 * b.shifted + .12 * awkward)
    return Transition(distance, same_hand, same_finger, not same_hand,
                      row_change, repeated, b.shifted, awkward, max(.55, min(score, 2.25)))


TRANSITION_MATRIX = {(a, b): transition(a, b) for a in KEYS for b in KEYS}
