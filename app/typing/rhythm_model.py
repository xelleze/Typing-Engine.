import numpy as np


class RhythmModel:
    """AR(1) tempo; randomness changes a persistent state, not key delays."""
    def __init__(self, rng: np.random.Generator, variance: float = .025):
        self.rng = rng
        self.variance = variance
        self.tempo = 1.

    def step(self) -> float:
        noise = self.rng.normal(0., self.variance)
        self.tempo = self.tempo * .94 + (1. + noise) * .06
        self.tempo = max(.75, min(self.tempo, 1.25))
        return self.tempo
