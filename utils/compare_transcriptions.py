#!/usr/bin/env python3
"""
A/B Comparison: Claude vs. Gemini Transcriptions
Reads paired .md files from two output directories, compares metadata and
transcription quality, and writes a markdown report.
"""

import re
import sys
from pathlib import Path
from datetime import datetime


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Split a markdown file into (frontmatter_dict, body_text).
    Frontmatter is hand-built (not yaml.dump), so we parse it line-by-line
    rather than relying on pyyaml to handle [[wiki-links]] safely.
    """
    if not text.startswith('---'):
        return {}, text

    end = text.find('\n---', 3)
    if end == -1:
        return {}, text

    fm_block = text[4:end]
    body = text[end + 4:].strip()

    meta: dict = {}
    current_key = None
    current_list: list | None = None

    for line in fm_block.splitlines():
        # List item
        if line.startswith('  - '):
            val = line[4:].strip()
            if current_list is not None:
                current_list.append(val)
            continue

        # Key: value
        if ':' in line:
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()

            if current_list is not None and current_key:
                meta[current_key] = current_list

            if val == '':
                # Start of a list block
                current_key = key
                current_list = []
                meta[key] = current_list
            else:
                current_key = key
                current_list = None
                meta[key] = val

    return meta, body


def extract_section(body: str, heading: str) -> str:
    """Extract content under a ## heading."""
    pattern = rf'## {re.escape(heading)}\n(.*?)(?=\n## |\Z)'
    m = re.search(pattern, body, re.DOTALL)
    return m.group(1).strip() if m else ''


def count_ocr_artifacts(text: str) -> int:
    """
    Count lines that look like raw OCR column-bleed:
    a line that is 1-3 non-space characters (broken hyphenation, stray letters).
    """
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) <= 3 and not stripped.startswith('<!--'):
            count += 1
    return count


def entity_set(lst: list) -> set:
    """Normalise [[wiki-link]] or plain strings to a comparable set."""
    out = set()
    for item in lst:
        # Strip [[ ]] and normalise case/whitespace
        clean = re.sub(r'^\[\[|\]\]$', '', str(item)).strip().lower()
        out.add(clean)
    return out


# ---------------------------------------------------------------------------
# Per-file comparison
# ---------------------------------------------------------------------------

def compare_pair(name: str, claude_path: Path, gemini_path: Path) -> dict:
    claude_text = claude_path.read_text(encoding='utf-8')
    gemini_text = gemini_path.read_text(encoding='utf-8')

    cm, cb = parse_frontmatter(claude_text)
    gm, gb = parse_frontmatter(gemini_text)

    c_transcription = extract_section(cb, 'Transcription')
    g_transcription = extract_section(gb, 'Transcription')

    c_overview = extract_section(cb, 'Overview')
    g_overview = extract_section(gb, 'Overview')

    # Entity sets
    fields = ['people', 'organization', 'locations', 'themes']
    entity_stats = {}
    for f in fields:
        c_set = entity_set(cm.get(f) or [])
        g_set = entity_set(gm.get(f) or [])
        entity_stats[f] = {
            'claude_count': len(c_set),
            'gemini_count': len(g_set),
            'shared': c_set & g_set,
            'claude_only': c_set - g_set,
            'gemini_only': g_set - c_set,
        }

    return {
        'name': name,
        'claude': {
            'title': cm.get('title', ''),
            'date': cm.get('date', ''),
            'transcription_len': len(c_transcription),
            'ocr_artifacts': count_ocr_artifacts(c_transcription),
            'illegible_count': c_transcription.lower().count('[illegible]'),
            'overview': c_overview,
            'entities': entity_stats,
            'meta': cm,
        },
        'gemini': {
            'title': gm.get('title', ''),
            'date': gm.get('date', ''),
            'transcription_len': len(g_transcription),
            'ocr_artifacts': count_ocr_artifacts(g_transcription),
            'illegible_count': g_transcription.lower().count('[illegible]'),
            'overview': g_overview,
            'entities': entity_stats,
            'meta': gm,
        },
    }


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_report(comparisons: list[dict]) -> str:
    lines = []
    a = lines.append

    a(f'# Claude vs. Gemini Transcription Comparison')
    a(f'')
    a(f'Generated: {datetime.now().strftime("%B %d, %Y at %H:%M")}')
    a(f'Documents compared: {len(comparisons)}')
    a(f'')

    # ---- Summary table ----
    a('## Summary')
    a('')
    a('| Document | Date (C) | Date (G) | Transcription length | OCR artifacts | [illegible] markers |')
    a('|----------|----------|----------|---------------------|---------------|---------------------|')

    for c in comparisons:
        cl = c['claude']
        ge = c['gemini']
        date_c = cl['date'] or '—'
        date_g = ge['date'] or '—'
        len_diff = f"C:{cl['transcription_len']:,} / G:{ge['transcription_len']:,}"
        artifacts = f"C:{cl['ocr_artifacts']} / G:{ge['ocr_artifacts']}"
        illegible = f"C:{cl['illegible_count']} / G:{ge['illegible_count']}"
        a(f"| {c['name']} | {date_c} | {date_g} | {len_diff} | {artifacts} | {illegible} |")

    a('')

    # ---- Entity extraction summary ----
    a('## Entity Extraction Summary')
    a('')
    a('| Document | Field | Claude | Gemini | Shared | Claude-only | Gemini-only |')
    a('|----------|-------|--------|--------|--------|-------------|-------------|')

    for comp in comparisons:
        # Use entity_stats from claude dict (same object shared between both)
        for field, stats in comp['claude']['entities'].items():
            shared_n = len(stats['shared'])
            co_n = len(stats['claude_only'])
            go_n = len(stats['gemini_only'])
            a(f"| {comp['name']} | {field} | {stats['claude_count']} | {stats['gemini_count']} | {shared_n} | {co_n} | {go_n} |")

    a('')

    # ---- Per-document detail ----
    a('## Per-Document Details')
    a('')

    for comp in comparisons:
        cl = comp['claude']
        ge = comp['gemini']
        a(f"### {comp['name']}")
        a('')

        # Titles
        if cl['title'] != ge['title']:
            a(f'**Title divergence:**')
            a(f'- Claude: `{cl["title"]}`')
            a(f'- Gemini: `{ge["title"]}`')
            a('')

        # Date
        a(f'**Date extracted:** Claude `{cl["date"] or "—"}` / Gemini `{ge["date"] or "—"}`')
        a('')

        # Overviews
        a('**Overviews:**')
        a('')
        a(f'*Claude:* {cl["overview"]}')
        a('')
        a(f'*Gemini:* {ge["overview"]}')
        a('')

        # Entity differences
        has_diffs = False
        for field, stats in cl['entities'].items():
            if stats['claude_only'] or stats['gemini_only']:
                if not has_diffs:
                    a('**Entity differences:**')
                    a('')
                    has_diffs = True
                if stats['claude_only']:
                    items = ', '.join(f'`{v}`' for v in sorted(stats['claude_only']))
                    a(f'- *{field}* — Claude only: {items}')
                if stats['gemini_only']:
                    items = ', '.join(f'`{v}`' for v in sorted(stats['gemini_only']))
                    a(f'- *{field}* — Gemini only: {items}')
        if has_diffs:
            a('')

        # Transcription quality
        a('**Transcription quality:**')
        a(f'- Length: Claude {cl["transcription_len"]:,} chars / Gemini {ge["transcription_len"]:,} chars')
        a(f'- OCR artifact lines: Claude {cl["ocr_artifacts"]} / Gemini {ge["ocr_artifacts"]}')
        a(f'- `[illegible]` markers: Claude {cl["illegible_count"]} / Gemini {ge["illegible_count"]}')
        a('')
        a('---')
        a('')

    # ---- Aggregate stats ----
    a('## Aggregate Statistics')
    a('')

    total = len(comparisons)
    claude_got_date = sum(1 for c in comparisons if c['claude']['date'])
    gemini_got_date = sum(1 for c in comparisons if c['gemini']['date'])
    a(f'- **Date extracted:** Claude {claude_got_date}/{total} · Gemini {gemini_got_date}/{total}')

    c_artifacts_total = sum(c['claude']['ocr_artifacts'] for c in comparisons)
    g_artifacts_total = sum(c['gemini']['ocr_artifacts'] for c in comparisons)
    a(f'- **Total OCR artifact lines:** Claude {c_artifacts_total} · Gemini {g_artifacts_total}')

    c_illegible_total = sum(c['claude']['illegible_count'] for c in comparisons)
    g_illegible_total = sum(c['gemini']['illegible_count'] for c in comparisons)
    a(f'- **Total `[illegible]` markers:** Claude {c_illegible_total} · Gemini {g_illegible_total}')

    for field in ['people', 'organization', 'locations', 'themes']:
        c_total = sum(c['claude']['entities'][field]['claude_count'] for c in comparisons)
        g_total = sum(c['gemini']['entities'][field]['gemini_count'] for c in comparisons)
        a(f'- **Total {field} extracted:** Claude {c_total} · Gemini {g_total}')

    a('')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Compare Claude vs. Gemini transcription outputs'
    )
    parser.add_argument('--claude', type=Path, default=Path('transcriptions_claude'),
                        help='Directory of Claude .md files')
    parser.add_argument('--gemini', type=Path, default=Path('transcriptions_gemini'),
                        help='Directory of Gemini .md files')
    parser.add_argument('--output', type=Path, default=Path('comparison_report.md'),
                        help='Output report path (default: comparison_report.md)')
    args = parser.parse_args()

    if not args.claude.exists():
        print(f'❌ Claude directory not found: {args.claude}')
        sys.exit(1)
    if not args.gemini.exists():
        print(f'❌ Gemini directory not found: {args.gemini}')
        sys.exit(1)

    gemini_files = {f.name for f in args.gemini.glob('*.md')}
    pairs = sorted(
        f for f in args.claude.glob('*.md') if f.name in gemini_files
    )

    if not pairs:
        print('No matching files found in both directories.')
        sys.exit(1)

    print(f'Comparing {len(pairs)} document pairs...')
    comparisons = []
    for claude_path in pairs:
        gemini_path = args.gemini / claude_path.name
        name = claude_path.stem
        print(f'  {name}')
        comparisons.append(compare_pair(name, claude_path, gemini_path))

    report = render_report(comparisons)
    args.output.write_text(report, encoding='utf-8')
    print(f'\n✓ Report written to: {args.output}')


if __name__ == '__main__':
    main()
