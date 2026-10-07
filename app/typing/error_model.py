"""Preplan sparse neighbouring-key typos and optional correction events."""
from math import hypot, isfinite
import numpy as np
import regex
from .keyboard_layout import KEYS, get_key
from .transition_model import transition


class ErrorModel:
    def __init__(self, rate=.2, correct=True, seed=None):
        if not isfinite(rate) or not 0 <= rate <= 1:
            raise ValueError('Error rate must be between 0 and 100 percent')
        self.rate, self.correct = rate, correct
        self.rng = np.random.default_rng(seed)

    def plan(self, rows):
        if not rows:
            return []
        text = ''.join(r['char'] for r in rows)
        mistakes = {}
        for word in regex.finditer(r'[A-Za-z]{3,}', text):
            # At most one typo per word, inside it so correction happens before
            # its space can submit the word to the destination.
            if self.rate and self.rng.random() < 1 - (1 - self.rate) ** len(word.group()):
                candidates = list(range(word.start() + 1, word.end() - 1))
                weights = np.array([rows[i]['base_score'] for i in candidates])
                index = int(self.rng.choice(candidates, p=weights / weights.sum()))
                key = get_key(text[index].lower())
                neighbours = [char for char in 'abcdefghijklmnopqrstuvwxyz'
                              if char != text[index].lower() and
                              hypot(KEYS[char].x - key.x, KEYS[char].y - key.y) <= 1.5]
                wrong = str(self.rng.choice(neighbours))
                mistakes[index] = wrong.upper() if text[index].isupper() else wrong
        result = []
        for i, original in enumerate(rows):
            intended = original['char']
            wrong = mistakes.get(i)
            row = dict(original, intended_char=intended, event='normal', source_progress=i + 1)
            if wrong:
                key = get_key(wrong)
                t = transition(original['previous'], wrong)
                row.update(char=wrong, finger=key.finger, hand=key.hand,
                           event='typo', **t.details(), base_score=t.score,
                           source_progress=i if self.correct else i + 1)
            result.append(row)
            if wrong and self.correct:
                backspace = dict(row, char='\b', previous=wrong, finger='pinky', hand='R',
                                 event='backspace', chunk='', chunk_modifier=0.,
                                 planning_delay=0., source_progress=i,
                                 final_delay=180 * original['rhythm'])
                correction = dict(original, intended_char=intended, previous='\b',
                                  event='correction', source_progress=i + 1,
                                  planning_delay=0., final_delay=max(30., original['final_delay'] * .75))
                result.extend((backspace, correction))
        # Count extra events in the planned timeline, keeping the original total
        # duration/WPM. Recovery time is planned, never recomputed by playback.
        duration = sum(r['final_delay'] for r in rows)
        scale = duration / sum(r['final_delay'] for r in result)
        for row in result:
            row['pre_error_delay'] = row['final_delay']
            row['final_delay'] *= scale
            row['error_scale'] = scale
        return result
