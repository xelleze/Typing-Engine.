"""Optional real-desktop smoke check. Uses fake keyboard output exclusively.

Run: python -m app.tests.desktop_smoke
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import tkinter as tk
import cv2
from app.gui import TypingApp
from app.capture.screen import Region, capture_region
from app.capture.ocr import recognize
from app.typing.executor import KeyboardExecutor


def pump(root, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        time.sleep(.01)


def main():
    with TemporaryDirectory() as directory:
        root = tk.Tk()
        app = TypingApp(root, Path(directory) / 'rare.sqlite')
        app.error_percent.set('0')
        class Output:
            def __init__(self):
                self.chars = []
            def emit(self, char):
                self.chars.append(char)
        output = Output()
        app.executor = KeyboardExecutor(output, hotkeys=False)
        source = None
        try:
            pump(root, .2)
            assert app.build()
            root.attributes('-topmost', True)
            root.lift()
            pump(root, .5)
            assert len(app.tree.get_children()) == 60
            assert app.line_mode.get() == 'Spaces (wrapped text)'
            assert not app.enter_after.get()
            artifacts = Path('artifacts')
            artifacts.mkdir(exist_ok=True)
            image = capture_region(Region(root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()))
            cv2.imwrite(str(artifacts / 'desktop-smoke.png'), image)
            root.attributes('-topmost', False)
            # Capture an application-owned text window, then run real Tesseract.
            source = tk.Tk()
            source.title('OCR verification source')
            source.geometry('760x160+60+60')
            source.attributes('-topmost', True)
            label = tk.Label(source, text='Hello, WORLD!\nTyping engine 123.', font=('Arial', 26), bg='white', fg='black', padx=20, pady=10)
            label.pack(fill='both', expand=True)
            pump(root, .3)
            region = Region(label.winfo_rootx(), label.winfo_rooty(), label.winfo_width(), label.winfo_height())
            recognized = recognize(capture_region(region))
            assert 'Hello, WORLD!' in recognized, repr(recognized)
            assert 'Typing engine 123.' in recognized, repr(recognized)
            # The explicitly topmost source remains visible above the app.
            app.region = region
            overlap_check = app.region_overlaps_window
            app.region_overlaps_window = lambda: False
            app.live_interval.set('0.2')
            app.start_live()
            pump(root, 2.)
            assert app.live is not None
            assert 'Hello, WORLD!' in app.text.get('1.0', 'end-1c')
            assert app.preview_image is not None
            label.configure(text='New prompt 456.')
            pump(root, 2.)
            collected = app.text.get('1.0', 'end-1c')
            assert 'Hello, WORLD!' in collected and 'New prompt 456.' in collected, repr(collected)
            assert collected.count('New prompt 456.') == 1, repr(collected)
            # Regression: Start must be usable directly during live capture,
            # without manually stopping or building first.
            assert str(app.start_button.cget('state')) == 'normal'
            assert str(app.build_button.cget('state')) == 'normal'
            app.wpm.set('600')
            app.countdown.set('0')
            app.start_button.invoke()
            pump(root, 3.)
            initial_output = app.text_for_typing() + ' '
            assert ''.join(output.chars) == initial_output, repr(output.chars)
            assert '\n' not in ''.join(output.chars)
            assert 'WORLD! Typing engine' in ''.join(output.chars)
            assert app.executor.state == 'waiting'
            assert app.streaming and app.live is not None
            label.configure(text='Next words arrive.')
            pump(root, 2.)
            assert ''.join(output.chars) == initial_output + 'Next words arrive. ', repr(output.chars)
            assert app.executor.state == 'waiting'
            label.configure(text='words arrive. More follows.')
            pump(root, 2.)
            assert ''.join(output.chars) == initial_output + 'Next words arrive. More follows. ', repr(output.chars)
            pump(root, .3)
            assert app.executor.state == 'waiting'
            app.cancel_button.invoke()
            pump(root, .2)
            assert app.executor.state == 'cancelled'
            assert not app.streaming
            output.chars.clear()
            assert app.live is None and app.text.cget('state') == 'normal'
            app.region_overlaps_window = overlap_check
            source.destroy()
            source = None
            app.region = region
            # Feed the actual OCR result through the GUI's asynchronous result path.
            app.events.put(('ocr', recognized))
            pump(root, .15)
            assert app.text.get('1.0', 'end-1c') == recognized
            assert not app.rows
            app.region = None
            app.text.delete('1.0', 'end')
            app.text.insert('1.0', 'Onychophora.')
            pump(root, .1)
            app.wpm.set('600')
            app.countdown.set('0')
            # Force one planned typo in this word to verify correction through
            # GUI -> executor and source-progress accounting end to end.
            app.error_percent.set('100')
            assert app.build()
            assert any(r['event'] == 'backspace' for r in app.rows)
            app.start()
            pump(root, 1.)
            visible = []
            for char in output.chars:
                if char == '\b':
                    visible.pop()
                else:
                    visible.append(char)
            assert '\b' in output.chars
            assert ''.join(visible) == 'Onychophora. '
            assert app.executor.state == 'waiting'
            app.cancel_button.invoke()
            pump(root, .2)
            assert app.executor.state == 'cancelled'
            assert app.store.seen_count('onychophora') == 1
            assert app.text.cget('state') == 'normal'
            controls = KeyboardExecutor(output, hotkeys=True)
            try:
                controls.start([], .1)
                controls.emergency_stop()
                controls.join(1.)
                assert controls.state == 'cancelled'
            finally:
                controls.close()
            app.select_region()
            pump(root, .2)
            assert app.overlay is not None
            app.overlay.event_generate('<Escape>')
            pump(root, .2)
            assert app.overlay is None
            print('Desktop smoke passed: GUI build/review, live MSS -> preprocessing -> Tesseract, fake playback, adaptive storage.')
            print(f'OCR result: {recognized!r}')
            print(f'Screenshot: {artifacts / "desktop-smoke.png"}')
        finally:
            if source is not None:
                source.destroy()
            app.close()


if __name__ == '__main__':
    main()
