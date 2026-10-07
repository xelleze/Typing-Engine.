import unittest
from unittest.mock import patch
import numpy as np
from app.capture.ocr import normalize_text, recognize
from app.capture.preprocess import preprocess
from app.capture.screen import Region


class OCRTests(unittest.TestCase):
    def test_preserves_text_structure(self):
        self.assertEqual(normalize_text('Hello,  WORLD!\r\nNext line.\n\x0c'), 'Hello,  WORLD!\nNext line.\n')

    def test_preprocessing(self):
        image = np.full((20, 40, 4), 255, dtype=np.uint8)
        image[5:15, 10:30, :3] = 0
        processed = preprocess(image)
        self.assertEqual(processed.shape, (40, 80))
        self.assertEqual(processed.dtype, np.uint8)
        self.assertEqual(set(np.unique(processed)), {0, 255})
        with self.assertRaises(ValueError):
            preprocess(image, scale=0)
        with self.assertRaises(ValueError):
            Region(0, 0, 0, 20)

    def test_ocr_configuration_and_normalization(self):
        with patch('app.capture.ocr.configure_tesseract'), patch('app.capture.ocr.pytesseract.image_to_string', return_value='Hello!\r\n') as read:
            self.assertEqual(recognize(np.full((20, 40), 255, dtype=np.uint8)), 'Hello!\n')
            self.assertIn('preserve_interword_spaces=1', read.call_args.kwargs['config'])
