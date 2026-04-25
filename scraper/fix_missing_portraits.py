"""Copy missing hero portraits from workshop mods to assets."""
import re
import sys
import io
import shutil
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

JS_PATH = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\src\data\modded_heroes.js')
HEROES_DIR = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\dd-team-builder-assets\images\modded\heroes')
WORKSHOP = Path(r'D:\Program Files (x86)\Steam\steamapps\workshop\content\262060')


def to_image_filename(name):
    return (name.lower().replace("'", "").replace(" ", "_")
            .replace("-", "").replace("(", "").replace(")")
            .replace(".", "").replace(",", ""))


def main():
    # Backup JS first
    shutil.copy2(JS_PATH, JS_PATH.with_suffix('.js.bak3'))

    with open(JS_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    missing = []
    for m in re.finditer(r"  '([^']+)': \{\s*\n(.*?)\n  \}", content, re.DOTALL):
        name, block = m.group(1), m.group(2)
        mid = re.search(r"modId: '(\d+)'", block)
        img_m = re.search(r"image: '([^']+)'", block)
        if not mid or not img_m:
            continue
        img = img_m.group(1)
        modid = mid.group(1)
        if not (HEROES_DIR / img).exists():
            missing.append((name, modid, img))

    print(f"Missing portraits: {len(missing)}")

    copied = 0
    not_found = 0
    image_fixes = []

    for name, modid, expected_img in missing:
        mod_path = WORKSHOP / modid
        heroes_dir = mod_path / 'heroes'
        if not heroes_dir.exists():
            not_found += 1
            continue

        # Try all hero subfolders for a portrait
        portrait_found = None
        folder_name = None
        for hero_folder in sorted(heroes_dir.iterdir()):
            if not hero_folder.is_dir():
                continue
            if hero_folder.name.endswith(('_A', '_B', '_C', '_D', '_E', '_F')):
                continue

            folder_name = hero_folder.name
            # Deep search for any *_portrait_roster.png in this hero's tree
            for portrait in hero_folder.rglob('*portrait_roster*'):
                portrait_found = portrait
                break
            if portrait_found:
                break

            # Also check directly in the hero folder
            for png in hero_folder.glob('*.png'):
                if 'portrait' in png.name.lower():
                    portrait_found = png
                    break
            if portrait_found:
                break

        if not portrait_found:
            not_found += 1
            continue

        # Copy to output with sanitized name
        out_name = f'{folder_name}.png'
        dest = HEROES_DIR / out_name
        shutil.copy2(portrait_found, dest)
        copied += 1

        # Update JS image field if needed
        if expected_img != out_name:
            image_fixes.append((expected_img, out_name))

    print(f"Copied: {copied}")
    print(f"Not found in mods: {not_found}")

    # Update JS image fields
    if image_fixes:
        with open(JS_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        for old_img, new_img in image_fixes:
            content = content.replace(f"image: '{old_img}'", f"image: '{new_img}'")
        with open(JS_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {len(image_fixes)} image references in JS")


if __name__ == '__main__':
    main()
