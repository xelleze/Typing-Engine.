"""Run the desktop app, or inspect supplied text without keyboard output."""
import argparse
import sys
from pathlib import Path

# Also allow `python app/main.py` from the project directory.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Screen OCR and human typing timeline engine')
    parser.add_argument('--text', help='Generate and explain supplied text; sends no keyboard events')
    parser.add_argument('--file', type=Path, help='Read UTF-8 text for a timeline; sends no keyboard events')
    parser.add_argument('--profile', choices=['average', 'fast', 'expert'], default='fast')
    parser.add_argument('--wpm', type=float)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--export', type=Path, help='Export timeline to .html or .json')
    args = parser.parse_args(argv)
    if args.text is not None and args.file is not None:
        parser.error('Use either --text or --file')
    if args.text is not None or args.file is not None:
        from app.config.typing_profile import profile_named
        from app.typing.timing_engine import TimingEngine
        from app.typing.debug import print_explanation, export_timeline
        from app.typing.rare_store import RareWordStore
        try:
            text = args.text if args.text is not None else args.file.read_text(encoding='utf-8')
            with RareWordStore(Path(__file__).parent / 'data' / 'rare_words.sqlite') as store:
                rows = TimingEngine(profile_named(args.profile, args.wpm), args.seed, store).explain(text)
            print_explanation(rows)
            if args.export:
                export_timeline(rows, args.export)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    else:
        from app.gui import launch
        launch()


if __name__ == '__main__':
    main()
