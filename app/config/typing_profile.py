from dataclasses import dataclass, replace
from math import isfinite


@dataclass(frozen=True)
class TypingProfile:
    target_wpm: float = 110
    transition_variance: float = .08
    cognitive_variance: float = .15
    rarity_sensitivity: float = 1.0
    chunk_skill: float = 1.0
    rhythm_variance: float = .025
    base_motor_ms: float = 75
    base_rare_pause: float = 65
    length_rare_factor: float = 9
    max_cognitive_ms: float = 450

    def __post_init__(self):
        for name, value in vars(self).items():
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.target_wpm == 0 or self.base_motor_ms == 0 or self.max_cognitive_ms == 0:
            raise ValueError("WPM, motor time and cognitive cap must be positive")


PROFILES = {
    "average": TypingProfile(target_wpm=55),
    "fast": TypingProfile(),
    "expert": TypingProfile(target_wpm=140, chunk_skill=1.25, rarity_sensitivity=.65,
                            base_rare_pause=50, length_rare_factor=7),
}


def profile_named(name: str, wpm: float | None = None) -> TypingProfile:
    profile = PROFILES[name]
    return replace(profile, target_wpm=wpm) if wpm is not None else profile
