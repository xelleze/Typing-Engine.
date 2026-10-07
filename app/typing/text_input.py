"""Explicit destination policies; OCR review text itself is left intact."""
import re

LINE_MODES = ('Spaces (wrapped text)', 'Enter per line', 'Enter per word')


def prepare_text(text: str, line_mode: str = LINE_MODES[0], enter_after: bool = True) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if line_mode == 'Spaces (wrapped text)':
        # Visual OCR wraps are word boundaries, not submission commands.
        text = re.sub(r'[ \t]*\n[ \t]*', ' ', text.strip('\n'))
    elif line_mode == 'Enter per word':
        text = '\n'.join(re.findall(r'\S+', text))
    elif line_mode != 'Enter per line':
        raise ValueError('Unknown line break mode')
    if text.strip() and enter_after and not text.endswith('\n'):
        text += '\n'
    return text
