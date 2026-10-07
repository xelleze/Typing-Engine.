"""Console explanation and a standalone timeline plot (no extra dependency)."""
import html
import json
from pathlib import Path


def print_explanation(rows: list[dict]) -> None:
    print(f"{'char':8} {'delay':>8} {'finger':8} {'hand':4} {'score':>6} {'Zipf':>6} {'rarity':>7} {'chunk':>7} {'plan':>7} {'rhythm':>7}")
    for r in rows:
        zipf = '-' if r['word_zipf'] is None else f"{r['word_zipf']:.2f}"
        print(f"{repr(r['char']):8} {r['final_delay']:8.2f} {r['finger']:8} {r['hand']:4} "
              f"{r['base_score']:6.2f} {zipf:>6} {r['rarity']:7.2f} "
              f"{r['chunk_modifier']:7.2f} {r['planning_delay']:7.2f} {r['rhythm']:7.4f}")
    total = sum(r['final_delay'] for r in rows)
    wpm = len(rows) / 5 * 60000 / total if total else 0
    print(f"\n{len(rows)} characters | {total / 1000:.3f} seconds | {wpm:.2f} WPM")


def export_timeline(rows: list[dict], path: str | Path) -> None:
    path = Path(path)
    if path.suffix.lower() == '.json':
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        return
    width = max(900, len(rows) * 17 + 80)
    highest = max((r['final_delay'] for r in rows), default=1) or 1
    bars = []
    for i, row in enumerate(rows):
        height = row['final_delay'] / highest * 240
        color = '#fb923c' if row['planning_delay'] else '#60a5fa'
        title = html.escape(json.dumps(row, ensure_ascii=False, indent=2))
        char = html.escape(repr(row['char'])[1:-1])
        bars.append(f'<g><title>{title}</title><rect x="{50 + i * 17}" y="{280 - height}" width="12" height="{height}" fill="{color}"/><text x="{50 + i * 17}" y="300" fill="#eee" font-size="11">{char}</text></g>')
    total = sum(r['final_delay'] for r in rows)
    path.write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Typing timeline</title><body style="background:#111827;color:#eee;font-family:system-ui;padding:24px">
<h1>Typing timeline</h1><p>{len(rows)} characters · {total / 1000:.3f} seconds. Orange marks word planning. Hover a bar for full timing details.</p>
<div style="overflow-x:auto"><svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="340" role="img" aria-label="Per-character delay in milliseconds">
<text x="0" y="22" fill="#eee">{highest:.1f} ms</text>{''.join(bars)}</svg></div></body></html>''', encoding='utf-8')
