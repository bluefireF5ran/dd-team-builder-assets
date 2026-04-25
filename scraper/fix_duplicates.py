"""
Fix same-name-different-modId duplicates by adding modId suffix to the weaker entries.
Keeps the entry with most skills as the base name.
"""
import re
import sys
import io
import urllib.request
import json
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

JS_PATH = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\src\data\modded_heroes.js')


def main():
    with open(JS_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all hero entries
    entries = []
    for m in re.finditer(r"  '([^']+)': \{\s*\n(.*?)\n  \}", content, re.DOTALL):
        name, block = m.group(1), m.group(2)
        mid = re.search(r"modId: '(\d+)'", block)
        sm = re.search(r'skills: \[([^\]]*)\]', block)
        skill_count = len(re.findall(r"'([^']+)'", sm.group(1))) if sm else 0
        entries.append({
            'name': name,
            'modid': mid.group(1) if mid else '0',
            'skills': skill_count,
            'start': m.start(),
            'end': m.end(),
        })

    # Group by name
    by_name = defaultdict(list)
    for e in entries:
        by_name[e['name']].append(e)

    dups = {k: v for k, v in by_name.items() if len(v) > 1}

    # For each duplicate group, keep the best (most skills), rename others with modId suffix
    renames = []  # (old_name, modid, new_name)
    for name, group in dups.items():
        sorted_group = sorted(group, key=lambda x: x['skills'], reverse=True)
        for i, e in enumerate(sorted_group):
            if i == 0:
                continue
            new_name = f"{name} ({e['modid']})"
            renames.append((name, e['modid'], new_name))

    print(f"Renames to apply: {len(renames)}")

    # Apply renames - go in reverse order to preserve positions
    # For each rename, we need to find the specific entry with this name AND modid
    for old_name, modid, new_name in renames:
        escaped_old = re.escape(old_name)
        escaped_mid = re.escape(modid)
        # Find the specific entry block
        pattern = rf"  '{escaped_old}': \{{\s*\n(.*?)\n  \}}"
        for m in re.finditer(pattern, content, re.DOTALL):
            block = m.group(1)
            if f"modId: '{modid}'" in block:
                # Replace just this occurrence
                old_text = f"  '{old_name}': {{"
                new_text = f"  '{new_name}': {{"
                # Replace only in the specific range
                before = content[:m.start()]
                after = content[m.end():]
                block_content = content[m.start():m.end()]
                block_content = block_content.replace(old_text, new_text, 1)
                content = before + block_content + after
                break

    # Sort alphabetically
    with open(JS_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    # Re-read and sort
    with open(JS_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    header_match = re.match(r'^(.*?export const MODDED_HERO_CLASSES = \{)\s*\n', content, re.DOTALL)
    if not header_match:
        print("ERROR: Could not parse header")
        return

    header = header_match.group(1)
    obj_start = header_match.end()

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

    pattern = r"  '([^']+)':\s*\{"
    matches = list(re.finditer(pattern, obj_content))

    parsed = []
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
        block = obj_content[start_pos:end_pos].rstrip().rstrip(',')
        parsed.append((name, block.strip()))

    parsed.sort(key=lambda x: x[0].lower())

    output = header + '\n'
    for i, (name, block) in enumerate(parsed):
        lines = block.split('\n')
        if not lines[0].startswith('  '):
            lines[0] = '  ' + lines[0].lstrip()
        output += '\n'.join(lines)
        if i < len(parsed) - 1:
            output += ','
        output += '\n'

    output += '};\n' + remaining

    with open(JS_PATH, 'w', encoding='utf-8') as f:
        f.write(output)

    # Final stats
    skills_ok = 0
    zero_skills = 0
    chinese = 0
    modids = set()
    names = defaultdict(int)
    for name, block in parsed:
        names[name] += 1
        mid = re.search(r"modId: '(\d+)'", block)
        if mid:
            modids.add(mid.group(1))
        sm = re.search(r'skills: \[([^\]]*)\]', block)
        if sm and sm.group(1).strip():
            skills_ok += 1
        else:
            zero_skills += 1
        if re.search(r'[\u4e00-\u9fff]', name):
            chinese += 1

    dups_remaining = {k: v for k, v in names.items() if v > 1}

    print(f"\n=== FINAL STATS ===")
    print(f"Total heroes: {len(parsed)}")
    print(f"Unique modIds: {len(modids)}")
    print(f"With skills: {skills_ok} ({skills_ok * 100 // len(parsed)}%)")
    print(f"Zero skills: {zero_skills} ({zero_skills * 100 // len(parsed)}%)")
    print(f"Chinese names: {chinese}")
    print(f"Remaining duplicate names: {len(dups_remaining)}")
    for name, count in sorted(dups_remaining.items()):
        print(f"  {name!r}: {count}x")


if __name__ == '__main__':
    main()
