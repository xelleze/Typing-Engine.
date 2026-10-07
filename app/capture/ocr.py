import os
from pathlib import Path
import shutil
import unicodedata
import pytesseract
from .preprocess import preprocess


def configure_tesseract(executable: str | None = None) -> str:
    candidates = [executable, os.environ.get('TESSERACT_CMD'), shutil.which('tesseract'),
                  r'C:\Program Files\Tesseract-OCR\tesseract.exe']
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return str(candidate)
    raise RuntimeError('Tesseract OCR was not found. Install it, then set TESSERACT_CMD or choose its executable in the app.')


def normalize_text(text: str) -> str:
    # Do not collapse spaces, strip line breaks, or change punctuation/case.
    return unicodedata.normalize('NFC', text.replace('\r\n', '\n').replace('\r', '\n')).replace('\x0c', '')


def recognize(image, executable: str | None = None, language: str = 'eng',
              psm: int = 6, scale: float = 2., threshold: bool = True) -> str:
    configure_tesseract(executable)
    return normalize_text(pytesseract.image_to_string(
        preprocess(image, scale, threshold), lang=language,
        config=f'--psm {int(psm)} -c preserve_interword_spaces=1', timeout=30))
