from dataclasses import dataclass
import numpy as np
from mss import mss


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError('Capture region must have positive width and height')


def desktop_bounds() -> dict:
    with mss() as capture:
        return dict(capture.monitors[0])


def capture_region(region: Region) -> np.ndarray:
    with mss() as capture:
        bounds = capture.monitors[0]
        if (region.left < bounds['left'] or region.top < bounds['top'] or
            region.left + region.width > bounds['left'] + bounds['width'] or
            region.top + region.height > bounds['top'] + bounds['height']):
            raise ValueError('Capture region lies outside the desktop')
        return np.array(capture.grab(vars(region)))
