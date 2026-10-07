"""Generate a complete, explainable timeline before any keyboard output."""
from dataclasses import dataclass
from math import isfinite
import numpy as np
from app.config.typing_profile import TypingProfile
from .keyboard_layout import get_key
from .transition_model import transition
from .word_model import WORD_PATTERN, analyze_word, chunk_at, FamiliarityStore
from .rhythm_model import RhythmModel


@dataclass(frozen=True)
class Keystroke:
    char: str
    delay_ms: float

    def __post_init__(self):
        if len(self.char) != 1 or not isfinite(self.delay_ms) or self.delay_ms < 0:
            raise ValueError("Keystroke needs one character and a finite nonnegative delay")


class TimingEngine:
    def __init__(self, profile: TypingProfile | None = None, seed: int | None = None,
                 store: FamiliarityStore | None = None):
        self.profile = profile or TypingProfile()
        # An unseeded engine gets a random session seed so explain() still
        # describes generate() exactly when text and familiarity are unchanged.
        self.seed = seed if seed is not None else np.random.SeedSequence().entropy
        self.store = store

    def generate(self, text: str) -> list[Keystroke]:
        return [Keystroke(row["char"], row["final_delay"]) for row in self.explain(text)]

    def explain(self, text: str) -> list[dict]:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not text:
            return []
        p = self.profile
        rng = np.random.default_rng(self.seed)
        rhythm = RhythmModel(rng, p.rhythm_variance)
        words = [analyze_word(m.group(), m.start(), p, self.store)
                 for m in WORD_PATTERN.finditer(text)]
        lookup = {i: word for word in words for i in range(word.start, word.end)}
        rows, motors, cognition = [], [], []
        # Stable motor skill per pair within a run, rather than per-key jitter.
        pair_skill = {}
        sentence_pending = False
        previous = None
        for i, char in enumerate(text):
            key = get_key(char)
            t = transition(previous, char)
            word = lookup.get(i)
            chunk, modifier = chunk_at(word.word, i - word.start, p.chunk_skill) if word else ("", 0.)
            pair = (previous, char)
            if pair not in pair_skill:
                pair_skill[pair] = max(.8, min(1.2, 1 + rng.normal(0, p.transition_variance)))
            score = max(.55, t.score + modifier)
            motor = max(p.base_motor_ms * .55, p.base_motor_ms * score * pair_skill[pair])
            tempo = rhythm.step()
            correlated = max(.7, min(1.3, 1 + (tempo - 1) * p.cognitive_variance / max(p.rhythm_variance, .001)))
            planning = word.planning_ms if word and i == word.start else 0.
            # Sparse hesitation at difficult unlearned internal transitions.
            internal = 0.
            if word and i > word.start and not chunk and t.score >= 1.65:
                internal = word.effective_rarity * p.rarity_sensitivity * 12 * (t.score - 1.5)
            boundary = 0.
            if char == " ":
                boundary = 25.
            elif char == "\t":
                boundary = 45.
            # Delay-before-character representation: punctuation hesitation
            # belongs to the following character, after punctuation is emitted.
            if previous == "\n":
                boundary += 180.
            elif previous == ",":
                boundary += 75.
            elif previous is not None and previous in ".!?":
                boundary += 130. if previous == "." else 150.
            elif previous is not None and previous in ";:—–()[]{}":
                boundary += 60.
            if word and i == word.start and sentence_pending:
                boundary += 150.
                sentence_pending = False
            if char in ".!?":
                sentence_pending = True
            cognitive = (planning + internal + boundary) * correlated * tempo
            motor *= tempo
            motors.append(motor)
            cognition.append(cognitive)
            rows.append({"char": char, "previous": previous, "finger": key.finger,
                         "hand": key.hand, "known_key": key.known, **t.details(),
                         "base_score": t.score, "chunk": chunk, "chunk_modifier": modifier,
                         "word_zipf": word.zipf if word else None,
                         "rarity": word.rarity if word else 0.,
                         "effective_rarity": word.effective_rarity if word else 0.,
                         "seen_count": word.seen_count if word else 0,
                         "planning_delay": planning, "internal_delay": internal,
                         "boundary_delay": boundary, "rhythm": tempo,
                         "motor_ms": motor, "cognitive_ms": cognitive,
                         "raw_delay": motor + cognitive})
            previous = char
        target = len(text) / 5 / p.target_wpm * 60000
        motor_array = np.array(motors)
        cognitive_array = np.array(cognition)
        raw = motor_array + cognitive_array
        scale = target / float(raw.sum())
        # Cap only cognitive components; redistribute residual duration across
        # motor costs to retain exact total WPM even for very slow profiles.
        final_cognitive = np.minimum(cognitive_array * scale, p.max_cognitive_ms)
        motor_scale = (target - float(final_cognitive.sum())) / float(motor_array.sum())
        final = motor_array * motor_scale + final_cognitive
        for row, delay, cognitive_ms in zip(rows, final, final_cognitive):
            row.update(final_delay=float(delay), final_cognitive_ms=float(cognitive_ms),
                       normalization_scale=scale, motor_scale=motor_scale,
                       cognitive_capped=row["cognitive_ms"] * scale > p.max_cognitive_ms)
        return rows
