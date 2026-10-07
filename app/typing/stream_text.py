"""Find new words across expanding or scrolling OCR snapshots."""
import re
from difflib import SequenceMatcher
from .text_input import prepare_text


def tokens(text):
    return [m.group().casefold() for m in re.finditer(r'\S+', text)]


class StreamTextPlanner:
    def __init__(self, initial_snapshot='', line_mode='Spaces (wrapped text)', enter_after=False):
        self.previous = tokens(initial_snapshot)
        self.line_mode = line_mode
        self.enter_after = enter_after

    def format(self, text):
        prepared = prepare_text(text, self.line_mode, self.enter_after)
        if not prepared.strip():
            return ''
        # Submit the final word so a typing test can reveal its next prompt.
        separator = ' ' if self.line_mode == 'Spaces (wrapped text)' and not self.enter_after else '\n'
        return prepared if prepared.endswith((' ', '\n', '\t')) else prepared + separator

    def observe(self, snapshot):
        matches = list(re.finditer(r'\S+', snapshot))
        new = [m.group().casefold() for m in matches]
        old = self.previous
        if not new:
            # Keep the last snapshot across blank OCR frames to avoid replaying
            # the same prompt after a momentary recognition failure.
            return ''
        if new == old:
            return ''
        # A shrinking viewport or colour change must not replay visible words.
        if any(old[i:i + len(new)] == new for i in range(max(0, len(old) - len(new) + 1))):
            return ''
        overlap = 0
        # One common word at a page boundary is not evidence of scrolling.
        # Longer viewports need a three-word anchor; short growing prompts can
        # still match their full prefix (including an initial single word).
        maximum = min(len(old), len(new))
        minimum = min(3 if len(old) >= 6 and len(new) >= 6 else 2, maximum)
        for size in range(maximum, minimum - 1, -1):
            tail, head = old[-size:], new[:size]
            errors = sum(a != b for a, b in zip(tail, head))
            exact = size - errors
            # Highlighting/cursors can change a word's OCR spelling. Match a
            # strong surrounding anchor rather than replaying the whole page.
            fuzzy = size >= 4 and exact >= 3 and errors <= max(1, size // 10)
            if errors == 0 or fuzzy:
                overlap = size
                break
        if not overlap and old:
            matcher = SequenceMatcher(a=old, b=new, autojunk=False)
            if len(new) <= len(old) and matcher.ratio() >= .85:
                # A near-identical correction has no new tail. Similarity alone
                # must not select a random shared word as an insertion cursor.
                self.previous = new
                return ''
        self.previous = new
        if overlap >= len(new):
            return ''
        return self.format(snapshot[matches[overlap].start():])
