import cv2
import numpy as np


def preprocess(image: np.ndarray, scale: float = 2., threshold: bool = True) -> np.ndarray:
    if image.size == 0 or not np.isfinite(scale) or scale <= 0:
        raise ValueError('Image must be nonempty and scale positive')
    if image.ndim == 2:
        gray = image.copy()
    elif image.ndim == 3 and image.shape[2] in (3, 4):
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY)
    else:
        raise ValueError('Expected grayscale, BGR, or BGRA image')
    if scale != 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    # Tesseract prefers dark text on a light background.
    if np.median(gray) < 127:
        gray = 255 - gray
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    if threshold:
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return gray
