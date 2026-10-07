"""Tk desktop UI: select a region, review text, inspect timing, then play."""
import ctypes
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from app.capture.screen import Region, desktop_bounds, capture_region
from app.capture.ocr import recognize
from app.capture.live import LiveCapture
from app.config.typing_profile import PROFILES, profile_named
from app.typing.timing_engine import TimingEngine, Keystroke
from app.typing.debug import export_timeline
from app.typing.executor import KeyboardExecutor
from app.typing.text_input import LINE_MODES, prepare_text
from app.typing.stream_text import StreamTextPlanner
from app.typing.error_model import ErrorModel

SAMPLE = 'The extraordinarily uncommon terminology surprised everyone.'


class TypingApp:
    def __init__(self, root: tk.Tk, store_path: str | Path | None = None):
        from app.typing.rare_store import RareWordStore
        self.root = root
        self.store = RareWordStore(store_path or Path(__file__).parent / 'data' / 'rare_words.sqlite')
        self.executor = KeyboardExecutor()
        self.events = Queue()
        self.rows = []
        self.generated_text = None
        self.generated_settings = None
        self.playback_text = ''
        self.streaming = False
        self.stream_planner = None
        self.stream_settings = None
        self.capture_warning = ''
        self.stream_revision = 0
        self.error_model = None
        self.playback_positions = []
        self.recorded_words = set()
        self._reported_error = False
        self.ocr_busy = False
        self.live = None
        self.preview_image = None
        self.region = None
        self.overlay = None
        self.root.title('Typing Engine')
        self.root.geometry('1120x820')
        self.root.minsize(860, 650)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TButton', padding=(10, 6))
        style.configure('Title.TLabel', font=('Segoe UI', 20, 'bold'))
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Typing Engine', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='Capture text, review it, and build a human timing sequence.').pack(anchor='w', pady=(0, 12))
        settings = ttk.Frame(outer)
        settings.pack(fill='x', pady=(0, 12))
        self.profile_name = tk.StringVar(value='fast')
        self.wpm = tk.StringVar(value='110')
        self.seed = tk.StringVar(value='42')
        self.countdown = tk.StringVar(value='5')
        ttk.Label(settings, text='Profile').pack(side='left')
        combo = ttk.Combobox(settings, textvariable=self.profile_name, values=list(PROFILES), state='readonly', width=10)
        combo.pack(side='left', padx=(5, 18))
        combo.bind('<<ComboboxSelected>>', lambda e: self.wpm.set(str(PROFILES[self.profile_name.get()].target_wpm)))
        for label, variable, width in [('WPM', self.wpm, 7), ('Seed', self.seed, 9), ('Focus countdown (s)', self.countdown, 5)]:
            ttk.Label(settings, text=label).pack(side='left')
            ttk.Entry(settings, textvariable=variable, width=width).pack(side='left', padx=(5, 18))
        self.tabs = ttk.Notebook(outer)
        review = ttk.Frame(self.tabs, padding=12)
        inspect = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(review, text='Text review')
        self.tabs.add(inspect, text='Timing inspector')
        capture_bar = ttk.Frame(review)
        capture_bar.pack(fill='x')
        self.select_button = ttk.Button(capture_bar, text='Select screen region', command=self.select_region)
        self.select_button.pack(side='left')
        self.recapture_button = ttk.Button(capture_bar, text='Capture again', command=self.capture_again, state='disabled')
        self.recapture_button.pack(side='left', padx=8)
        ttk.Button(capture_bar, text='Tesseract executable…', command=self.choose_tesseract).pack(side='left')
        self.tesseract = ''
        self.region_label = ttk.Label(review, text='You can also paste or edit text below.')
        self.region_label.pack(anchor='w', pady=8)
        live_bar = ttk.Frame(review)
        live_bar.pack(fill='x', pady=(0, 8))
        self.live_button = ttk.Button(live_bar, text='Start live capture', command=self.start_live)
        self.live_button.pack(side='left')
        self.stop_live_button = ttk.Button(live_bar, text='Stop live capture', command=self.stop_live, state='disabled')
        self.stop_live_button.pack(side='left', padx=8)
        self.live_mode = tk.StringVar(value='Collect changes')
        ttk.Combobox(live_bar, textvariable=self.live_mode, values=['Collect changes', 'Latest text'], state='readonly', width=16).pack(side='left')
        ttk.Label(live_bar, text='OCR every (s)').pack(side='left', padx=(12, 5))
        self.live_interval = tk.StringVar(value='0.5')
        ttk.Entry(live_bar, textvariable=self.live_interval, width=5).pack(side='left')
        self.preview = tk.Canvas(review, height=100, bg='#111827', highlightthickness=0)
        self.preview.pack(fill='x', pady=(0, 8))
        self.preview.create_text(12, 12, text='Live region preview appears here. Start typing uses the captured text.', anchor='nw', fill='white')
        typing_bar = ttk.Frame(review)
        typing_bar.pack(fill='x', pady=(0, 8))
        ttk.Label(typing_bar, text='Line breaks').pack(side='left')
        self.line_mode = tk.StringVar(value='Spaces (wrapped text)')
        ttk.Combobox(typing_bar, textvariable=self.line_mode, values=LINE_MODES, state='readonly', width=23).pack(side='left', padx=8)
        self.enter_after = tk.BooleanVar(value=False)
        ttk.Checkbutton(typing_bar, text='Press Enter after text', variable=self.enter_after).pack(side='left', padx=8)
        ttk.Label(typing_bar, text='Typos (%)').pack(side='left', padx=(8, 4))
        self.error_percent = tk.StringVar(value='20')
        ttk.Entry(typing_bar, textvariable=self.error_percent, width=5).pack(side='left')
        self.correct_typos = tk.BooleanVar(value=True)
        ttk.Checkbutton(typing_bar, text='Correct typos', variable=self.correct_typos).pack(side='left', padx=8)
        text_frame = ttk.Frame(review)
        text_frame.pack(fill='both', expand=True)
        self.text = tk.Text(text_frame, wrap='word', font=('Consolas', 13), undo=True, padx=12, pady=12)
        scrollbar = ttk.Scrollbar(text_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.text.pack(fill='both', expand=True)
        self.text.insert('1.0', SAMPLE)
        self.text.edit_modified(False)
        self.text.bind('<<Modified>>', self.text_changed)
        ttk.Label(review, text='OCR preserves whitespace and punctuation. Review recognition errors before starting.').pack(anchor='w', pady=(8, 0))
        self.chart = tk.Canvas(inspect, height=155, bg='#111827', highlightthickness=0)
        self.chart.pack(fill='x')
        self.chart.bind('<Configure>', lambda e: self.draw_chart())
        columns = ('char', 'delay', 'finger', 'hand', 'score', 'zipf', 'rarity', 'chunk', 'plan', 'rhythm')
        tree_frame = ttk.Frame(inspect)
        tree_frame.pack(fill='both', expand=True, pady=8)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        for name, heading in zip(columns, ['Character', 'Delay ms', 'Finger', 'Hand', 'Score', 'Zipf', 'Rarity', 'Chunk', 'Plan ms', 'Rhythm']):
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=78, minwidth=45, anchor='center')
        scroll = ttk.Scrollbar(tree_frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.inspect_row)
        self.detail = tk.StringVar(value='Select a row to inspect the transition.')
        ttk.Label(inspect, textvariable=self.detail, wraplength=1000).pack(anchor='w')
        self.summary = tk.StringVar(value='Build a timeline to inspect the timings.')
        footer = ttk.Frame(outer)
        footer.pack(side='bottom', fill='x')
        ttk.Label(footer, textvariable=self.summary).pack(anchor='w', pady=(12, 8))
        actions = ttk.Frame(footer)
        actions.pack(fill='x')
        self.build_button = ttk.Button(actions, text='Build timeline', command=self.build)
        self.build_button.pack(side='left')
        self.export_button = ttk.Button(actions, text='Export timeline…', command=self.export, state='disabled')
        self.export_button.pack(side='left', padx=8)
        self.start_button = ttk.Button(actions, text='Start typing', command=self.start, state='disabled')
        self.start_button.pack(side='left')
        self.pause_button = ttk.Button(actions, text='Pause / resume', command=lambda: self.executor.toggle_pause(), state='disabled')
        self.pause_button.pack(side='left', padx=8)
        self.cancel_button = ttk.Button(actions, text='Stop typing', command=lambda: self.executor.cancel(), state='disabled')
        self.cancel_button.pack(side='left')
        self.status = tk.StringVar(value='Ready')
        ttk.Label(footer, textvariable=self.status).pack(anchor='w', pady=(10, 4))
        ttk.Label(footer, text='Global controls: Ctrl + Alt + P to pause/resume · Ctrl + Alt + Esc to stop').pack(anchor='w')
        self.tabs.pack(fill='both', expand=True)
        self.root.after(80, self.poll)

    def text_changed(self, event=None):
        if self.text.edit_modified():
            if self.streaming:
                self.text.edit_modified(False)
                return
            self.generated_text = None
            self.rows = []
            ready = (bool(self.text.get('1.0', 'end-1c').strip()) or self.live is not None) and not self.playback_text
            self.start_button.configure(state='normal' if ready else 'disabled')
            self.export_button.configure(state='disabled')
            self.tree.delete(*self.tree.get_children())
            self.draw_chart()
            self.summary.set('Text ready. Start typing builds its timeline automatically.' if ready else 'Waiting for text to type.')
            self.text.edit_modified(False)

    def settings(self):
        return (self.profile_name.get(), float(self.wpm.get()),
                int(self.seed.get()) if self.seed.get().strip() else None,
                self.line_mode.get(), self.enter_after.get(),
                float(self.error_percent.get()) / 100, self.correct_typos.get())

    def text_for_typing(self):
        return prepare_text(self.text.get('1.0', 'end-1c'), self.line_mode.get(), self.enter_after.get())

    def build(self, freeze_capture=True):
        try:
            if self.live and freeze_capture:
                self.stop_live()
            text = self.text_for_typing()
            if not text.strip():
                raise ValueError('Enter or capture some text first.')
            name, wpm, seed, line_mode, enter_after, error_rate, correct = self.settings()
            rows = TimingEngine(profile_named(name, wpm), seed, self.store).explain(text)
            rows = ErrorModel(error_rate, correct, seed).plan(rows)
            self.rows = rows
            self.generated_text = text
            self.generated_settings = (name, wpm, seed, line_mode, enter_after, error_rate, correct)
            self.tree.delete(*self.tree.get_children())
            for i, r in enumerate(rows):
                self.tree.insert('', 'end', iid=str(i), values=(repr(r['char']), f"{r['final_delay']:.1f}", r['finger'], r['hand'],
                    f"{r['base_score']:.2f}", '-' if r['word_zipf'] is None else f"{r['word_zipf']:.2f}",
                    f"{r['rarity']:.2f}", r['chunk'] or '-', f"{r['planning_delay']:.1f}", f"{r['rhythm']:.4f}"))
            duration = sum(r['final_delay'] for r in rows) / 1000
            unknown = sum(not r['known_key'] for r in rows)
            self.summary.set(f'{len(rows)} keystrokes · {duration:.3f} seconds · {wpm:g} WPM · {line_mode}' +
                             (' · Enter after text' if enter_after else '') +
                             f" · {sum(r['event'] == 'typo' for r in rows)} planned typos" +
                             (f' · {unknown} characters use estimated key geometry' if unknown else ''))
            self.start_button.configure(state='normal')
            self.export_button.configure(state='normal')
            self.tabs.select(1)
            self.draw_chart()
            return True
        except Exception as exc:
            messagebox.showerror('Cannot build timeline', str(exc), parent=self.root)
            return False

    def draw_chart(self):
        self.chart.delete('all')
        if not self.rows:
            return
        width = max(100, self.chart.winfo_width())
        highest = max(r['final_delay'] for r in self.rows)
        # Bucket very long timelines so chart work remains bounded by width.
        buckets = min(len(self.rows), max(1, width // 3))
        for i in range(buckets):
            group = self.rows[i * len(self.rows) // buckets:(i + 1) * len(self.rows) // buckets]
            delay = max(r['final_delay'] for r in group)
            color = '#fb923c' if any(r['planning_delay'] for r in group) else '#60a5fa'
            self.chart.create_rectangle(i * width / buckets, 145 - delay / highest * 120,
                                        (i + 1) * width / buckets - 1, 145, fill=color, outline='')
        self.chart.create_text(8, 8, text=f'{highest:.1f} ms peak · orange = word planning', anchor='nw', fill='white')

    def inspect_row(self, event=None):
        selected = self.tree.selection()
        if not selected or int(selected[0]) >= len(self.rows):
            return
        r = self.rows[int(selected[0])]
        self.detail.set(f"{r.get('event', 'normal')}: {r['previous']!r} → {r['char']!r} "
            f"(intended {r.get('intended_char', r['char'])!r}): distance {r['distance']:.2f}, "
            f"same finger {r['same_finger']}, alternating hands {r['alternate_hand']}, "
            f"chunk modifier {r['chunk_modifier']:.2f}, planning {r['planning_delay']:.1f} ms, "
            f"internal hesitation {r['internal_delay']:.1f} ms, boundary {r['boundary_delay']:.1f} ms, "
            f"seen {r['seen_count']} times, final cognitive {r['final_cognitive_ms']:.1f} ms.")

    def export(self):
        if not self.rows:
            return
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension='.html',
            filetypes=[('Timeline visualization', '*.html'), ('Full debug data', '*.json')])
        if path:
            try:
                export_timeline(self.rows, path)
                self.status.set(f'Exported {Path(path).name}')
            except Exception as exc:
                messagebox.showerror('Export failed', str(exc), parent=self.root)

    def start(self):
        try:
            if self.live:
                self.poll_live()
            if self.ocr_busy:
                raise RuntimeError('Wait for OCR to finish.')
            # Freeze capture and precompute the full timeline before playback.
            if self.live and not self.text_for_typing().strip():
                self.rows = []
                self.generated_text = ''
                self.generated_settings = self.settings()
            elif self.generated_text != self.text_for_typing() or self.generated_settings != self.settings():
                if not self.build(freeze_capture=False):
                    return
            name, wpm, seed, line_mode, enter_after, error_rate, correct = self.settings()
            snapshot = self.text.get('1.0', 'end-1c')
            initial_source = self.generated_text
            revision = 0
            if self.live:
                # Take one coherent snapshot so OCR finishing during Start
                # cannot lose new text or queue a reading already included.
                with self.live.lock:
                    snapshot = self.live.collector.accepted
                    revision = self.live.revision
                    initial_source = ('\n'.join(self.live.collector.segments)
                                      if self.live.collector.mode == 'Collect changes' else snapshot) or ''
            planner = StreamTextPlanner(snapshot or '', line_mode, enter_after)
            initial = planner.format(initial_source)
            error_model = ErrorModel(error_rate, correct, seed)
            planned = error_model.plan(TimingEngine(profile_named(name, wpm), seed, self.store).explain(initial))
            timeline = [Keystroke(r['char'], r['final_delay']) for r in planned]
            countdown = float(self.countdown.get())
            watcher = self.live
            if self.region and watcher is None:
                watcher = LiveCapture(self.region, float(self.live_interval.get()), self.live_mode.get(), self.tesseract or None)
            # Keep the same worker and hotkeys alive while its queue is empty.
            self.executor.start(timeline, countdown, keep_open=True)
            self.streaming = True
            self.stream_planner = planner
            self.stream_revision = revision
            self.stream_settings = (name, wpm, seed)
            self.error_model = error_model
            self.playback_positions = [r['source_progress'] for r in planned]
            self.capture_warning = ''
            self.playback_text = initial
            if watcher is not None and not self.live:
                self.live = watcher
                self.live.start()
            if self.live:
                self.stop_live_button.configure(state='normal')
            self.recorded_words = set()
            self._reported_error = False
            self.text.configure(state='disabled')
            for widget in (self.start_button, self.build_button, self.select_button, self.recapture_button, self.live_button):
                widget.configure(state='disabled')
            self.pause_button.configure(state='normal')
            self.cancel_button.configure(state='normal')
            self.status.set('Focus the destination window during the countdown.')
            self.root.iconify()
        except Exception as exc:
            messagebox.showerror('Cannot start playback', str(exc), parent=self.root)

    def choose_tesseract(self):
        path = filedialog.askopenfilename(parent=self.root, title='Choose tesseract.exe', filetypes=[('Executable', '*.exe')])
        if path:
            self.tesseract = path

    def region_overlaps_window(self):
        if not self.region or self.root.state() in ('iconic', 'withdrawn'):
            return False
        r = self.region
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        return (r.left < x + self.root.winfo_width() + 10 and r.left + r.width > x - 10
                and r.top < y + self.root.winfo_height() + 10 and r.top + r.height > y - 35)

    def start_live(self):
        try:
            if self.live or self.ocr_busy or self.playback_text:
                raise RuntimeError('Finish the current capture or playback first.')
            if not self.region:
                raise ValueError('Select a screen region first, then start live capture.')
            if self.region_overlaps_window():
                raise ValueError('Move the Typing Engine window outside the selected region so it can capture the source text.')
            live = LiveCapture(self.region, float(self.live_interval.get()), self.live_mode.get(), self.tesseract or None)
            live.start()
            self.live = live
            self.text.delete('1.0', 'end')
            self.text_changed()
            self.text.configure(state='disabled')
            for widget in (self.live_button, self.select_button, self.recapture_button):
                widget.configure(state='disabled')
            self.stop_live_button.configure(state='normal')
            self.tabs.select(0)
            self.status.set('Live capture running. Start typing uses the collected text; Stop allows editing.')
        except Exception as exc:
            messagebox.showerror('Cannot start live capture', str(exc), parent=self.root)

    def apply_live_text(self, text):
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', text)
        self.text_changed()
        if self.live:
            self.text.configure(state='disabled')

    def stop_live(self):
        live = self.live
        if not live:
            return
        live.stop()
        if self.streaming:
            self.live = None
            self.executor.cancel()
            return
        # Keep any already accepted reading waiting for the next GUI poll.
        while True:
            try:
                kind, payload = live.updates.get_nowait()
                if kind == 'text':
                    self.apply_live_text(payload)
            except Empty:
                break
        self.live = None
        self.text.configure(state='normal')
        for widget in (self.live_button, self.select_button, self.build_button):
            widget.configure(state='normal')
        self.start_button.configure(state='normal' if self.text.get('1.0', 'end-1c').strip() else 'disabled')
        self.recapture_button.configure(state='normal' if self.region else 'disabled')
        self.stop_live_button.configure(state='disabled')
        self.status.set('Live capture stopped. Review the collected text and build a timeline.')

    def poll_live(self):
        live = self.live
        if not live:
            return
        if self.region_overlaps_window():
            if self.streaming:
                live.suspended.set()
                self.capture_warning = 'Capture paused: move the app outside the selected region.'
                return
            self.stop_live()
            self.status.set('Live capture stopped: the app moved over the selected region. Move it away and restart.')
            return
        if live.suspended.is_set():
            self.capture_warning = ''
        live.suspended.clear()
        try:
            frame = live.previews.get_nowait()
            from PIL import Image, ImageTk
            image = Image.fromarray(frame[:, :, :3][:, :, ::-1])
            image.thumbnail((max(1, self.preview.winfo_width()), 100))
            self.preview_image = ImageTk.PhotoImage(image, master=self.root)
            self.preview.delete('all')
            self.preview.create_image(0, 0, image=self.preview_image, anchor='nw')
        except Empty:
            pass
        try:
            while True:
                kind, payload = live.updates.get_nowait()
                if kind == 'warning':
                    self.capture_warning = f'Capture retrying: {payload}'
                    if not self.streaming:
                        self.status.set(self.capture_warning)
                    continue
                if kind == 'error':
                    self.stop_live()
                    self.status.set(f'Live capture failed: {payload}')
                    return
                if kind == 'reading':
                    if self.streaming and self.executor.state not in ('cancelled', 'error', 'completed'):
                        revision, reading = payload
                        if revision <= self.stream_revision:
                            continue
                        self.stream_revision = revision
                        self.capture_warning = ''
                        additional = self.stream_planner.observe(reading or '')
                        if additional:
                            name, wpm, seed = self.stream_settings
                            planned = self.error_model.plan(TimingEngine(profile_named(name, wpm), seed, self.store).explain(additional))
                            timeline = [Keystroke(r['char'], r['final_delay']) for r in planned]
                            try:
                                self.executor.append(timeline)
                                self.playback_positions.extend(len(self.playback_text) + r['source_progress'] for r in planned)
                                self.playback_text += additional
                            except RuntimeError:
                                if self.executor.state not in ('cancelled', 'error', 'completed'):
                                    raise
                    continue
                if self.streaming:
                    continue
                self.apply_live_text(payload)
                self.status.set(f'Live capture running · {len(payload)} characters. Start typing uses this text; Stop allows editing.')
        except Empty:
            pass

    def select_region(self):
        if self.ocr_busy or self.live:
            return
        try:
            bounds = desktop_bounds()
            self.root.withdraw()
            overlay = tk.Toplevel(self.root)
            self.overlay = overlay
            overlay.overrideredirect(True)
            overlay.attributes('-topmost', True)
            overlay.attributes('-alpha', .3)
            overlay.geometry(f"{bounds['width']}x{bounds['height']}+0+0")
            canvas = tk.Canvas(overlay, bg='black', cursor='crosshair', highlightthickness=0)
            canvas.pack(fill='both', expand=True)
            overlay.update_idletasks()
            # Tk negative geometry offsets are relative to the desktop's edge;
            # SetWindowPos gives absolute positions for monitors left of primary.
            if hasattr(ctypes, 'windll'):
                hwnd = ctypes.windll.user32.GetParent(overlay.winfo_id()) or overlay.winfo_id()
                ctypes.windll.user32.SetWindowPos(hwnd, -1, bounds['left'], bounds['top'], bounds['width'], bounds['height'], 0x0040)
            else:
                overlay.geometry(f"{bounds['width']}x{bounds['height']}+{bounds['left']}+{bounds['top']}")
            start = []
            rectangle = [None]
            def down(event):
                start[:] = [event.x_root, event.y_root, event.x, event.y]
                if rectangle[0]:
                    canvas.delete(rectangle[0])
                rectangle[0] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='white', width=3)
            def drag(event):
                if start:
                    canvas.coords(rectangle[0], start[2], start[3], event.x, event.y)
            def up(event):
                if not start:
                    return
                left, top = min(start[0], event.x_root), min(start[1], event.y_root)
                width, height = abs(event.x_root - start[0]), abs(event.y_root - start[1])
                overlay.destroy()
                self.overlay = None
                if width < 5 or height < 5:
                    self.root.deiconify()
                    return
                self.region = Region(left, top, width, height)
                self.root.after(180, self.capture_selected)
            def escape(event=None):
                overlay.destroy()
                self.overlay = None
                self.root.deiconify()
            canvas.bind('<ButtonPress-1>', down)
            canvas.bind('<B1-Motion>', drag)
            canvas.bind('<ButtonRelease-1>', up)
            overlay.bind('<Escape>', escape)
            overlay.focus_force()
        except Exception as exc:
            if self.overlay:
                self.overlay.destroy()
                self.overlay = None
            self.root.deiconify()
            messagebox.showerror('Selection failed', str(exc), parent=self.root)

    def capture_again(self):
        if self.region and not self.ocr_busy and not self.live:
            self.root.withdraw()
            self.root.after(180, self.capture_selected)

    def capture_selected(self):
        self.ocr_busy = True
        region, executable = self.region, self.tesseract
        self.status.set('Recognizing selected region…')
        def worker():
            try:
                self.events.put(('ocr', recognize(capture_region(region), executable or None)))
            except Exception as exc:
                self.events.put(('ocr_error', str(exc)))
        Thread(target=worker, daemon=True).start()

    def poll(self):
        self.poll_live()
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self.ocr_busy = False
                self.root.deiconify()
                self.recapture_button.configure(state='normal')
                if kind == 'ocr':
                    self.text.delete('1.0', 'end')
                    self.text.insert('1.0', payload)
                    self.text_changed()
                    self.tabs.select(0)
                    self.status.set('OCR ready. Review text and build the timeline.' if payload.strip() else 'No text recognized. Select another region.')
                    self.region_label.configure(text=f'Region: {self.region.left}, {self.region.top} · {self.region.width} × {self.region.height}')
                else:
                    messagebox.showerror('OCR failed', payload, parent=self.root)
                    self.status.set('OCR failed; pasted text is still available.')
        except Empty:
            pass
        state = self.executor.state
        if self.playback_text or self.streaming:
            label = 'Waiting for new text — Stop typing to end' if state == 'waiting' else state.capitalize()
            self.status.set(f'{label} · {self.executor.completed}/{self.executor.total} keystrokes' +
                            (f' · {self.executor.error}' if self.executor.error else '') +
                            (f' · {self.capture_warning}' if self.capture_warning else ''))
            if state in ('completed', 'cancelled', 'error'):
                self.streaming = False
                if self.live:
                    self.live.stop()
                    self.live = None
                self.stop_live_button.configure(state='disabled')
                # Record only fully emitted words; never count OCR or previews.
                try:
                    self.record_emitted_words()
                except Exception as exc:
                    self.status.set(f'{state.capitalize()}; could not save familiarity: {exc}')
                self.playback_text = ''
                self.root.deiconify()
                self.text.configure(state='normal')
                for widget in (self.start_button, self.build_button, self.select_button, self.live_button):
                    widget.configure(state='normal')
                self.recapture_button.configure(state='normal' if self.region else 'disabled')
                self.pause_button.configure(state='disabled')
                self.cancel_button.configure(state='disabled')
                if self.executor.error and not self._reported_error:
                    self._reported_error = True
                    messagebox.showerror('Playback failed', self.executor.error, parent=self.root)
        self.root.after(80, self.poll)

    def close(self):
        if self.live:
            self.live.stop()
            self.live = None
        self.executor.close()
        self.record_emitted_words()
        self.store.close()
        self.root.destroy()

    def record_emitted_words(self):
        from app.typing.word_model import WORD_PATTERN, frequency
        consumed = (self.playback_positions[self.executor.completed - 1]
                    if self.executor.completed and self.playback_positions else 0)
        for match in WORD_PATTERN.finditer(self.playback_text):
            if match.end() <= consumed and match.start() not in self.recorded_words:
                self.store.record(match.group(), frequency(match.group()))
                self.recorded_words.add(match.start())


def launch():
    if hasattr(ctypes, 'windll'):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except OSError:
            pass
    root = tk.Tk()
    TypingApp(root)
    root.mainloop()
