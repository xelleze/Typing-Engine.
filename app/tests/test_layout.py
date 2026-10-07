import unittest
from app.typing.keyboard_layout import KEYS, get_key


class LayoutTests(unittest.TestCase):
    def test_shifted_geometry(self):
        for plain, upper in [("a", "A"), ("1", "!"), ("/", "?")]:
            self.assertEqual(get_key(plain).x, get_key(upper).x)
            self.assertTrue(get_key(upper).shifted)

    def test_offsets_and_coverage(self):
        self.assertEqual(get_key("q").x, .25)
        self.assertEqual(get_key("a").x, .5)
        self.assertEqual(get_key("z").x, 1)
        self.assertTrue(set("abcdefghijklmnopqrstuvwxyz0123456789 ,.';/ -[]") <= KEYS.keys())
        self.assertFalse(get_key("é").known)
