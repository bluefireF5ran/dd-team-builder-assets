"""Deduplicate modded_heroes.js: keep entry with most skills per (name, modId)."""
import re
import sys
import io
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

JS_PATH = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\src\data\modded_heroes.js')


def parse_js_entries(content):
    """Parse all hero entries from the JS file."""
    header_match = re.match(r'^(.*?export const MODDED_HERO_CLASSES = \{)\s*\n', content, re.DOTALL)
    if not header_match:
        return None, [], ''

    header = header_match.group(1)
    obj_start = header_match.end()

    # Find closing brace
    brace_count = 1
    obj_end = obj_start
    in_string = False
    escape_next = False

    for i, char in enumerate(content[obj_start:]):
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == "'" and not in_string:
            in_string = True
        elif char == "'" and in_string:
            in_string = False
        elif not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    obj_end = obj_start + i
                    break

    obj_content = content[obj_start:obj_end]
    remaining = content[obj_end + 1:]
    if remaining.startswith(';'):
        remaining = remaining[1:]

    # Parse individual entries
    pattern = r"  '([^']+)':\s*\{"
    matches = list(re.finditer(pattern, obj_content))

    entries = []
    for match in matches:
        name = match.group(1)
        start_pos = match.start()

        brace_count = 0
        in_string = False
        escape_next = False
        end_pos = start_pos

        content_from = obj_content[match.end() - 1:]
        for j, char in enumerate(content_from):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == "'" and not in_string:
                in_string = True
            elif char == "'" and in_string:
                in_string = False
            elif not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = match.end() - 1 + j + 1
                        break

        block_text = obj_content[start_pos:end_pos]
        block = block_text.rstrip().rstrip(',')

        sm = re.search(r'skills: \[([^\]]*)\]', block_text)
        skill_count = len(re.findall(r"'([^']+)'", sm.group(1))) if sm else 0

        mid = re.search(r"modId: '(\d+)'", block_text)
        modid = mid.group(1) if mid else '0'

        entries.append({
            'name': name,
            'block': block.strip(),
            'skill_count': skill_count,
            'modid': modid,
        })

    return header, entries, remaining


def main():
    with open(JS_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    header, entries, remaining = parse_js_entries(content)
    if header is None:
        print("ERROR: Could not parse JS file")
        return

    print(f"Total entries parsed: {len(entries)}")

    # Deduplicate: keep best (most skills) per (name, modId)
    by_key = defaultdict(list)
    for e in entries:
        by_key[(e['name'], e['modid'])].append(e)

    unique = []
    for key, candidates in by_key.items():
        best = max(candidates, key=lambda x: x['skill_count'])
        unique.append(best)

    removed = len(entries) - len(unique)
    print(f"After dedup (same name+modId): {len(unique)} (removed {removed})")

    # Sort alphabetically
    unique.sort(key=lambda x: x['name'].lower())

    # Rebuild
    output = header + '\n'
    for i, e in enumerate(unique):
        block = e['block']
        lines = block.split('\n')
        if not lines[0].startswith('  '):
            lines[0] = '  ' + lines[0].lstrip()
        output += '\n'.join(lines)
        if i < len(unique) - 1:
            output += ','
        output += '\n'

    output += '};\n' + remaining

    with open(JS_PATH, 'w', encoding='utf-8') as f:
        f.write(output)

    # Stats
    skills_ok = sum(1 for e in unique if e['skill_count'] > 0)
    zero = sum(1 for e in unique if e['skill_count'] == 0)
    modids = set(e['modid'] for e in unique)
    chinese = [e['name'] for e in unique if re.search(r'[\u4e00-\u9fff]', e['name'])]

    print(f"\n=== FINAL STATS ===")
    print(f"Total heroes: {len(unique)}")
    print(f"Unique modIds: {len(modids)}")
    print(f"With skills: {skills_ok} ({skills_ok * 100 // len(unique)}%)")
    print(f"Zero skills: {zero} ({zero * 100 // len(unique)}%)")
    print(f"Chinese names: {len(chinese)}")
    for c in chinese:
        print(f"  {c!r}")

    # Check remaining duplicates (same name, different modId)
    name_counts = defaultdict(int)
    for e in unique:
        name_counts[e['name']] += 1
    dups = {k: v for k, v in name_counts.items() if v > 1}
    print(f"Same-name-different-modId: {len(dups)} heroes")
    for name, count in sorted(dups.items()):
        print(f"  {name!r}: {count}x")


if __name__ == '__main__':
    main()
