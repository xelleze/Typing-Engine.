# Typing Engine

A Windows desktop app for `screen region → OCR → reviewed text → human timing → keyboard events`. Python 3.11/3.12. The layout model is US QWERTY.

## Run

Dependencies are installed in `.venv` in this workspace. Launch with:

```powershell
.\.venv\Scripts\python.exe -m app.main
# Or launch without a console window:
.\run.ps1
```

For a fresh installation:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Tesseract is a separate native application. The app checks `TESSERACT_CMD`, PATH, and `C:\Program Files\Tesseract-OCR\tesseract.exe`. You can also choose the executable in the GUI. Install its English language data. Tkinter ships with standard Windows Python.

1. Paste text, or click **Select screen region**, drag a rectangle, and release. Escape cancels selection. The app hides while capturing.
2. Review and edit OCR text. Capitalization, punctuation, spaces and line breaks are retained; recognition accuracy depends on the source. Preprocessing enlarges by 2×, corrects dark backgrounds, and applies Otsu thresholding.
3. Choose a profile, WPM and optional seed. **Build timeline** opens the timing inspector. Select a row for transition details. Export HTML for a standalone hoverable chart or JSON for full debug data.
4. **Start typing** minimizes the app. Focus the destination window during the default five-second countdown. Playback sends characters to whichever window has focus. If a region is selected, it keeps capturing and typing newly appearing text. When no new text is available, the session waits.
5. **Ctrl+Alt+P** pauses/resumes globally. **Ctrl+Alt+Esc** stops globally, including during countdown. The GUI also provides pause/resume and cancel buttons. Pause preserves remaining delays; resume uses the original timeline.

Characters outside US QWERTY retain their text and use estimated key geometry. `pynput` output support depends on the destination and OS; an output failure pauses an open session and reports an error in its status. Resume retries the pending character. Newlines emit Enter and tabs emit Tab, so destination behavior may differ from a plain text editor.

## Enter and wrapped lines

The GUI defaults to **Spaces (wrapped text)** with **Press Enter after text** unchecked. Captured line breaks become spaces, so `the` at the end of one line followed by `edge` becomes `the edge`. Playback sends no Enter keys with these defaults.

Choose **Enter per line** for actual multiline input, or **Enter per word** for a destination that requires Enter between words. Enable **Press Enter after text** when submission is needed. These policies apply before timing generation and are visible in the inspector as space or `\n` rows. The OCR review retains its original line breaks. CLI and direct TimingEngine calls preserve supplied text as before.

## Live capture

**Typos (%)** defaults to **20**. **Correct typos** is enabled: a planned nearby-key mistake is followed by Backspace and the correct character before submitting that word. Set the rate to **0** to disable intentional errors. Uncheck correction to leave mistakes in the text. Only ASCII letter words of three or more letters are eligible; spaces, punctuation, numbers and control keys are protected, with at most one typo inside each word. That cap means the measured per-letter error rate can be lower than the configured rate.

Error decisions and correction delays are prepared before keyboard playback. Additional keys share the original batch duration so the selected WPM stays consistent. Error RNG state continues across streamed batches, rather than restarting the same pattern for every snippet. The timing inspector and JSON export include typo, backspace, and correction events. Source-word progress excludes extra correction keys when recording familiarity.

Select a region, move the Typing Engine window outside that region, then click **Start live capture**. The image preview refreshes about ten times per second while OCR runs separately at the configured interval (default 0.5 seconds, or as fast as Tesseract can finish). **Start typing** starts the focus countdown and keeps capturing during playback. It can also start while waiting for the first text. **Build timeline** stops preview capture and opens the inspector. Use **Stop live capture** before starting if you want to edit recognition errors.

- **Collect changes** keeps successive prompts on separate lines. If a prompt grows from `The` to `The quick`, it extends that prompt instead of duplicating its prefix.
- **Latest text** replaces the review text with the current stable reading.

Both modes require two matching OCR readings before accepting a change. Starting preview capture clears the previous review text. During typing, the engine compares stable snapshots, adds new suffixes, and skips overlapping words when the source scrolls. Unchanged or shrinking snapshots are not retyped. Momentary blank OCR readings do not replay the previous prompt. With spaces selected, each queued block ends with a space to advance its final word.

The session remains open after its queue runs out and displays **Waiting for new text**. It ends only when you press **Stop typing**, **Stop live capture**, **Ctrl+Alt+Esc**, or close the app. The countdown occurs once per session. **Ctrl+Alt+P** pauses/resumes even while waiting. Settings are frozen for that session. Capture errors retry, and covering the source with the app suspends capture until the window is moved away. Already queued output stays available.

Text that disappears before two matching readings can be missed; shorten the OCR interval for quicker prompts. OCR is imperfect: the engine cannot always distinguish a recognition correction from a new prompt, and identical repeated prompts without distinguishing context may be skipped. Select only source text: including the destination input field can cause OCR to collect text already typed there.

## Timing model

The precomputed transition matrix accounts for geometry, hand alternation, same finger, repeated keys, row movement, shift, and awkward reach. Familiar chunks discount internal transitions with a raw motor score floor of 0.55. A bounded skill offset is sampled once per distinct transition pair within a run; there is no independent per-character delay jitter. Correlated AR(1) tempo drives gradual drift and boundary variation.

`wordfreq.zipf_frequency` supplies familiarity. Rare words get planning costs at entry and small extra hesitation at difficult internal transitions; length alone does not slow common words. Boundaries carry space, punctuation, sentence and newline costs. Seeded runs with the same profile and familiarity database are reproducible.

WPM is used only after all raw delays are generated. The target total is `len(text) / 5 / WPM * 60000` ms, including whitespace and the first character's delay. Ordinary normalization scales the full sequence. Cognitive costs are capped at 450 ms after scaling; any residual duration is redistributed proportionally across motor costs. The raw score floor is preserved before normalization; extremely high WPM can yield impractically short physical delays. Wall-clock output overhead and pauses can reduce achieved WPM.

The `average`, `fast`, and `expert` profiles provide starting configurations. Expert increases chunk skill and reduces planning costs while keeping the motor model. `TypingProfile` exposes all parameters for custom programmatic profiles.

Only words below Zipf 3.5 are stored in `app/data/rare_words.sqlite`, created automatically. Completed playback records fully emitted words, including complete words before cancellation. OCR and timeline previews never increment encounter counts. Planning rarity decays by `exp(-seen_count / 15)`; motor costs remain. Delete the SQLite file while the app is closed to reset adaptation.

## Text-only milestone

```powershell
.\.venv\Scripts\python.exe -m app.main --text "The extraordinarily uncommon terminology surprised everyone." --wpm 110 --seed 42 --export milestone-timeline.html
.\.venv\Scripts\python.exe -m app.main --file input.txt --export timeline.json
```

These commands print per-character explanations and never emit keyboard events.

```python
from app.config.typing_profile import TypingProfile
from app.typing.timing_engine import TimingEngine

engine = TimingEngine(TypingProfile(target_wpm=110), seed=42)
timeline = engine.generate("The extraordinarily uncommon terminology surprised everyone.")
details = engine.explain("The extraordinarily uncommon terminology surprised everyone.")
```

`Keystroke.delay_ms` is a delay **before** emitting its character. `KeyboardExecutor.start()` accepts only a list of these objects and snapshots it. It never calculates timings or calls OCR. `explain()` returns raw motor/cognitive components, transition features, chunk modifiers, Zipf, adaptation, rhythm, normalization and final timings.

`KeyboardExecutor.start(timeline, keep_open=True)` waits for additional precomputed keystrokes when its queue is empty. `append(timeline)` adds another snapshot to that same session. The GUI generates and normalizes each new batch before appending it, preserving existing queued delays. Calls without `keep_open=True` retain finite playback for programmatic use.

Punctuation and line-change pauses apply to the following character. A final punctuation mark has no extra trailing pause. Engines without an explicit seed use a random session seed, so explanations still match generated timelines within the same engine.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s app/tests -v
```

Tests cover layout, transition ordering, repetitions, chunk discounts, rare-word planning, correlated tempo, reproducibility, exact target duration, cognitive caps, playback interruption and sparse database adaptation. Executor tests use a fake output and never type into another application.

An optional real-desktop smoke check opens test windows, captures a known text label through MSS, runs installed Tesseract, checks the GUI and hotkey listener, and verifies adaptation using fake keyboard output:

```powershell
.\.venv\Scripts\python.exe -m app.tests.desktop_smoke
```

A full 60-second reactive test keeps each prompt visible until its words have been typed, then replaces it with the next prompt. It uses live MSS capture, Tesseract, Latest text mode, 0.5-second OCR, and 180 WPM. Current words change color and receive an underline. Keyboard output is simulated and checked character by character against the known source, including repeated words at page boundaries:

```powershell
.\.venv\Scripts\python.exe -u -m app.tests.live_soak --label check
```

The test writes readings, mismatches, session states, and output to `artifacts/live-soak-check.json`, plus a screenshot of its test window. It runs for a full minute and explicitly cancels the session afterward.
