import unittest
from unittest.mock import Mock
from app.typing.text_input import prepare_text
from app.typing.executor import PynputOutput


class TextInputTests(unittest.TestCase):
    def test_wrapped_text_has_space_and_final_enter(self):
        text = 'The old oak tree had stood at the\nedge of the meadow for longer than\nanyone could remember. Its massive\n'
        self.assertEqual(prepare_text(text), 'The old oak tree had stood at the edge of the meadow for longer than anyone could remember. Its massive\n')

    def test_joining_does_not_double_spaces(self):
        self.assertEqual(prepare_text('the  \n  edge', enter_after=False), 'the edge')
        self.assertEqual(prepare_text('a  b\nc', enter_after=False), 'a  b c')

    def test_multiline_mode_and_no_duplicate_final_enter(self):
        self.assertEqual(prepare_text('First\nSecond', 'Enter per line'), 'First\nSecond\n')
        self.assertEqual(prepare_text('First\nSecond\n', 'Enter per line'), 'First\nSecond\n')

    def test_enter_after_each_word(self):
        self.assertEqual(prepare_text('First,  second!\nthird.', 'Enter per word'), 'First,\nsecond!\nthird.\n')

    def test_disabled_submit_and_blank_input(self):
        self.assertEqual(prepare_text('First', enter_after=False), 'First')
        self.assertEqual(prepare_text(''), '')
        self.assertFalse(prepare_text(' \n ').strip())

    def test_newline_emits_real_enter_key(self):
        # Exercise the real adapter without creating a controller or emitting
        # any system keyboard events.
        output = PynputOutput.__new__(PynputOutput)
        enter = object()
        output.special = {'\n': enter}
        output.controller = Mock()
        output.emit('\n')
        output.controller.press.assert_called_once_with(enter)
        output.controller.release.assert_called_once_with(enter)
        output.controller.type.assert_not_called()
