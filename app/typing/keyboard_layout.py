"""US QWERTY geometry, including shifted keys and Unicode fallbacks."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Key:
    char: str
    x: float
    y: float
    row: int
    hand: str
    finger: str
    shifted: bool = False
    known: bool = True


def _build() -> dict[str, Key]:
    result = {}
    rows = [("`1234567890-=", 0.0), ("qwertyuiop[]\\", 0.25),
            ("asdfghjkl;'", 0.5), ("zxcvbnm,./", 1.0)]
    fingers = [
        ["pinky", "pinky", "ring", "middle", "index", "index", "index", "index", "middle", "ring", "pinky", "pinky", "pinky"],
        ["pinky", "ring", "middle", "index", "index", "index", "index", "middle", "ring", "pinky", "pinky", "pinky", "pinky"],
        ["pinky", "ring", "middle", "index", "index", "index", "index", "middle", "ring", "pinky", "pinky"],
        ["pinky", "ring", "middle", "index", "index", "index", "index", "middle", "ring", "pinky"],
    ]
    for row, (chars, offset) in enumerate(rows):
        split = 6 if row == 0 else 5
        for i, char in enumerate(chars):
            result[char] = Key(char, i + offset, float(row), row,
                               "L" if i < split else "R", fingers[row][i])
    result[" "] = Key(" ", 5.5, 4.0, 4, "R", "thumb")
    result["\n"] = Key("\n", 12.0, 2.0, 2, "R", "pinky")
    result["\t"] = Key("\t", -1.0, 1.0, 1, "L", "pinky")
    for char in "abcdefghijklmnopqrstuvwxyz":
        result[char.upper()] = replace(result[char], char=char.upper(), shifted=True)
    for plain, shifted in zip("`1234567890-=[]\\;',./", '~!@#$%^&*()_+{}|:"<>?'):
        result[shifted] = replace(result[plain], char=shifted, shifted=True)
    return result


KEYS = _build()


def get_key(char: str) -> Key:
    if len(char) != 1:
        raise ValueError("Expected exactly one character")
    # Non-US glyphs remain in the timeline; mark their estimated motor cost.
    return KEYS.get(char, Key(char, 6.0, 2.0, 2, "R", "index", known=False))
