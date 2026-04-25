"""Remove zero-skill hero entries from modded_heroes.js."""
import re
import sys
import io
import json
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

JS_PATH = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\src\data\modded_heroes.js')
INCOMPLETE_PATH = Path(__file__).parent / 'incomplete_mods.json'


def main():
    with open(JS_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find zero-skill hero entries using the same regex as other scripts
    zero_names = set()
    zero_info = []
    for m in re.finditer(r"  '([^']+)': \{\s*\n(.*?)\n  \}", content, re.DOTALL):
        name, block = m.group(1), m.group(2)
        sm = re.search(r'skills: \[([^\]]*)\]', block)
        has_skills = bool(sm and sm.group(1).strip())
        if not has_skills:
            mid = re.search(r"modId: '(\d+)'", block)
            zero_names.add(name)
            zero_info.append({'name': name, 'modId': mid.group(1) if mid else '0'})

    print(f'Removing {len(zero_names)} zero-skill entries')

    # Save incomplete mod info
    modids = sorted(set(e['modId'] for e in zero_info))
    INCOMPLETE_PATH.write_text(json.dumps({
        'description': 'Mods with zero skills - need re-scraping when data is available',
        'count': len(zero_info),
        'modIds': modids,
        'heroes': zero_info
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Saved {len(modids)} unique modIds to incomplete_mods.json')

    # Remove zero-skill entries using regex replacement
    # Pattern matches the full entry block including trailing comma
    for name in zero_names:
        escaped = re.escape(name)
        # Match entry with optional trailing comma
        pat = rf"  '{escaped}': \{{\s*\n.*?\n  \}},?\n"
        content = re.sub(pat, '', content, flags=re.DOTALL, count=1)

    # Write back
    with open(JS_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    # Verify
    with open(JS_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    remaining = list(re.finditer(r"  '([^']+)': \{\s*\n(.*?)\n  \}", content, re.DOTALL))
    modid_set = set()
    for m in remaining:
        mid = re.search(r"modId: '(\d+)'", m.group(2))
        if mid:
            modid_set.add(mid.group(1))

    print(f'Remaining heroes: {len(remaining)}')
    print(f'Unique modIds: {len(modid_set)}')


if __name__ == '__main__':
    main()
