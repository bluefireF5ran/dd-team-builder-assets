"""
Fix hero data issues in modded_heroes.js:
1. Chinese/unparsed names -> proper English names
2. Vanilla name clashes -> add (Rework) suffix
3. Placeholder names -> proper names
4. Portrait image field -> match actual filename on disk
"""
import re
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

JS_PATH = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\src\data\modded_heroes.js')
HEROES_DIR = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\dd-team-builder-assets\images\modded\heroes')

# Name fixes: old_name -> new_name (per modId to avoid ambiguity)
NAME_FIXES = {
    # Chinese mods -> English names from Steam workshop titles
    ('{colour_start|bleed}血圣{colour_end}', '3131289832'): 'Blood Saint',
    ('{colour_start|blight}追剧死士{colour_end}', '3124755746'): 'Plague Doctor Fanatic',
    ('{colour_start|white}The Stars{colour_end}', '2360027730'): 'The Stars',
    ('兼职修女', '3132616946'): 'Part-time Nun',
    ('小猪？', '3028580969'): 'Pig Boss',
    ('犁马娘', '3372687509'): 'Plowmare',
    ('莉莉丝', '3607474042'): 'Lilith (Rework)',
    ('独角兽', '3611958999'): 'Unicorn (Rework)',
    ('蕾之忍者', '3476262502'): 'Ninja of Budding',
    ('恶魔小富婆', '3357715659'): 'Librarian',
    ('{colour_start|bleed}狂信者{colour_end}', '3397134362'): 'Exorcist',
    ('{colour_start|buff}六娃{colour_end}', '3406827854'): 'Sixth Child',
    ('{colour_start|bleed}血月{colour_end} {colour_start|stun}大小姐{colour_end}', '3170796947'): 'Remilia Scarlet',
    ('{colour_start|white}旁白{colour_end}', '3003019559'): 'Ancestor Narrator',
    ('卢卡尔', '2487750624'): 'Rugal',
    ('Heroname', '3033009726'): 'Template Hero',
    ('Dummy', '3671373469'): 'Dummy',
    ('Meaningless, to be filled in', '3182753700'): 'Yuzao Witch',

    # Multi-hero mod 3397134362 cleanup
    ('Abigailwilliams', '3397134362'): 'Abigail Williams',
    ('Bloodyhunter', '3397134362'): 'Bloody Hunter',
    ('Crusaderremakefromkaze', '3397134362'): 'Crusader (Kaze)',
    ('Exotic Princess', '3397134362'): 'Exotic Princess',
    ('Ghost Shark', '3397134362'): 'Ghost Shark',
    ('Heir', '3397134362'): 'Heir',
    ('Librarian', '3397134362'): 'Librarian (Kaze)',
    ('Lyzm', '3397134362'): 'Lyzm',
    ('Wc 1 Jester', '3397134362'): 'Jester (WC)',
    ('Wc 1 Plague Doctor', '3397134362'): 'Plague Doctor (WC)',
    ('Wc 1 Vestal', '3397134362'): 'Vestal (WC)',
    ('Wc Arona', '3397134362'): 'Arona',
    ('Wc Houndmaster', '3397134362'): 'Houndmaster (WC)',
    ('Wc Jester', '3397134362'): 'Jester (WC2)',
    ('Wc Lihuovan', '3397134362'): 'Li Huo Wang',
    ('Wc Man At Arms', '3397134362'): 'Man-at-Arms (WC)',
    ('Wc Plague Doctor', '3397134362'): 'Plague Doctor (WC2)',
    ('Wc Shieldbreaker', '3397134362'): 'Shieldbreaker (WC)',
    ('Wc Vestal', '3397134362'): 'Vestal (WC2)',
}

# Vanilla name clashes - add suffix
VANILLA_NAMES = {
    'Antiquarian', 'Arbalest', 'Bounty Hunter', 'Crusader', 'Grave Robber',
    'Hellion', 'Highwayman', 'Houndmaster', 'Jester', 'Leper', 'Man-at-Arms',
    'Man At Arms', 'Musketeer', 'Occultist', 'Plague Doctor', 'Shieldbreaker',
    'Vestal', 'Flagellant', 'Abomination'
}

# Special chars that need cleaning
SPECIAL_NAMES = {
    ('Babička', '2998304395'): 'Babicka',
    ('Doppelsöldner', '3002636946'): 'Doppelsoldner',
    ('Prophète', '2998565091'): 'Prophete',
    ('Der Fluchschütze', '3355797677'): 'Der Fluchschutzte',
}


def to_image_filename(name):
    """Match the JS app's toImageFileName function."""
    return (name.lower()
            .replace("'", "")
            .replace(" ", "_")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
            .replace(".", "")
            .replace(",", ""))


def find_portrait_filename(hero_name, mod_id):
    """Find the actual portrait file for a hero on disk."""
    # Try display name
    expected = to_image_filename(hero_name) + '.png'
    if (HEROES_DIR / expected).exists():
        return expected

    # Try modId.png
    if (HEROES_DIR / f'{mod_id}.png').exists():
        return f'{mod_id}.png'

    # Try fuzzy: find any image on disk whose stem matches parts of the hero name
    hero_lower = hero_name.lower().replace("'", "").replace(" ", "").replace("-", "")
    for img in HEROES_DIR.glob('*.png'):
        stem = img.stem.lower().replace("_", "").replace("'", "")
        if stem == hero_lower:
            return img.name

    return None


def main():
    with open(JS_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse all hero entries
    pattern = r"  '([^']+)': \{"
    modid_pattern = r"modId: '(\d+)'"
    image_pattern = r"image: '([^']+)'"

    changes = []

    # Find all hero blocks
    hero_blocks = list(re.finditer(r"  '([^']+)': \{\s*\n(.*?)\n  \}", content, re.DOTALL))

    for match in hero_blocks:
        old_name = match.group(1)
        block = match.group(2)

        modid_match = re.search(modid_pattern, block)
        if not modid_match:
            continue
        mod_id = modid_match.group(1)

        new_name = None

        # Check NAME_FIXES first (most specific)
        key = (old_name, mod_id)
        if key in NAME_FIXES:
            new_name = NAME_FIXES[key]
        elif key in SPECIAL_NAMES:
            new_name = SPECIAL_NAMES[key]
        elif old_name in VANILLA_NAMES and mod_id not in [
            # These modIds are the actual vanilla class mods, not reworks
        ]:
            # Check if there's already a suffix
            has_suffix = any(c in old_name for c in '()')
            if not has_suffix:
                new_name = f'{old_name} (Rework)'

        if new_name and new_name != old_name:
            changes.append(('name', old_name, new_name, mod_id))

    # Apply name changes (do in reverse order to preserve positions)
    for change_type, old_name, new_name, mod_id in reversed(changes):
        # Escape special regex chars in the old name
        escaped_old = re.escape(old_name)
        # Replace the hero name
        content = re.sub(
            f"  '{escaped_old}': {{",
            f"  '{new_name}'" + ': {',
            content,
            count=1
        )

    # Now fix image fields to match actual portrait filenames
    hero_blocks = list(re.finditer(r"  '([^']+)': \{\s*\n(.*?)\n  \}", content, re.DOTALL))
    image_fixes = []

    for match in hero_blocks:
        hero_name = match.group(1)
        block = match.group(2)

        modid_match = re.search(modid_pattern, block)
        image_match = re.search(image_pattern, block)
        if not modid_match or not image_match:
            continue

        mod_id = modid_match.group(1)
        current_image = image_match.group(1)

        actual = find_portrait_filename(hero_name, mod_id)
        if actual and actual != current_image:
            image_fixes.append((hero_name, current_image, actual))

    for hero_name, old_img, new_img in image_fixes:
        content = content.replace(f"image: '{old_img}'", f"image: '{new_img}'")

    # Write back
    with open(JS_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Name changes: {len(changes)}")
    for ct, old, new, mid in changes:
        print(f"  {old!r} -> {new!r} (modId: {mid})")

    print(f"\nImage fixes: {len(image_fixes)}")
    for hero, old, new in image_fixes:
        print(f"  {hero}: {old} -> {new}")


if __name__ == '__main__':
    main()
