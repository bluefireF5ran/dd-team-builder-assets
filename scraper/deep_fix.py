"""
Deep-fix script: Re-extract data from mods that had 0 skills or broken names.
Uses aggressive regex fallback to extract from broken XML.
"""
import re
import sys
import io
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

WORKSHOP = Path(r'D:\Program Files (x86)\Steam\steamapps\workshop\content\262060')
JS_PATH = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\src\data\modded_heroes.js')
HEROES_DIR = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\dd-team-builder-assets\images\modded\heroes')
SKILLS_DIR = Path(r'F:\Personal_Fran\Programas\Softwares\nextjs_projects\dd-team-builder\dd-team-builder-assets\images\modded\skills')


def extract_entries_from_xml(xml_file):
    """Try ET parser first, then regex fallback."""
    entries = {}
    skip = ['brazilian','czech','french','german','italian','japanese',
            'koreana','polish','russian','schinese','spanish','tchinese']
    if any(lang in xml_file.stem.lower() for lang in skip):
        return entries

    try:
        with open(xml_file, 'r', encoding='utf-8', errors='replace') as f:
            raw = f.read()
    except:
        return entries

    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)

    # Try standard XML parse
    try:
        root = ET.fromstring(content)
        eng = root.find(".//language[@id='english']")
        els = eng.findall('entry') if eng is not None else root.findall('.//entry')
        for el in els:
            eid = el.get('id', '')
            text = (el.text or '').strip()
            if eid and text:
                entries[eid] = text
        if entries:
            return entries
    except:
        pass

    # Regex fallback
    pat = re.compile(r'<entry\s+id="([^"]+)"[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</entry>', re.DOTALL)
    for m in pat.finditer(content):
        eid, text = m.group(1), m.group(2).strip()
        if eid and text:
            entries[eid] = text
    return entries


def clean_colour(text):
    text = re.sub(r'\{colour_start\|[^}]+\}', '', text)
    text = re.sub(r'\{colour_end\}', '', text)
    return text.strip()


def to_image_filename(name):
    return (name.lower().replace("'", "").replace(" ", "_")
            .replace("-", "").replace("(", "").replace(")", "")
            .replace(".", "").replace(",", ""))


def main():
    with open(JS_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all problem entries
    problems = defaultdict(list)  # modId -> list of hero names with issues
    for match in re.finditer(r"  '([^']+)': \{\s*\n(.*?)\n  \}", content, re.DOTALL):
        name, block = match.group(1), match.group(2)
        modid_m = re.search(r"modId: '(\d+)'" , block)
        skills_m = re.search(r'skills: \[([^\]]*)\]', block)
        if not modid_m:
            continue
        modid = modid_m.group(1)
        has_skills = bool(skills_m and skills_m.group(1).strip())
        is_broken = bool(re.search(r'[\u4e00-\u9fff]', name) or 'colour_start' in name)
        if not has_skills or is_broken:
            problems[modid].append(name)

    # Only fix mods on disk
    fixable = {mid: names for mid, names in problems.items() if (WORKSHOP / mid).exists()}
    print(f"Problem mods on disk: {len(fixable)}")

    fixes_applied = 0

    for modid in sorted(fixable):
        mod_path = WORKSHOP / modid
        heroes_dir = mod_path / 'heroes'
        loc_dir = mod_path / 'localization'

        if not heroes_dir.exists() or not loc_dir.exists():
            continue

        hero_folders = [d.name for d in heroes_dir.iterdir()
                       if d.is_dir() and not d.name.endswith(('_A','_B','_C','_D','_E','_F'))]
        if not hero_folders:
            continue

        # Extract all localization entries
        all_entries = {}
        for xml_file in loc_dir.glob('*string_table*.xml'):
            all_entries.update(extract_entries_from_xml(xml_file))

        if not all_entries:
            print(f"  {modid}: NO entries extracted from XML")
            continue

        for folder in hero_folders:
            folder_lower = folder.lower()

            # Find display name
            display_name = None
            for eid, text in all_entries.items():
                clean = clean_colour(text)
                if not clean:
                    continue
                if eid.lower() == f'hero_class_name_{folder_lower}':
                    display_name = clean
                    break
                if eid.lower() == f'hero_name_{folder_lower}':
                    display_name = clean
                    break

            # Find combat skills
            skills = []
            seen = set()
            for eid, text in all_entries.items():
                clean = clean_colour(text)
                if not clean:
                    continue
                pattern = f'combat_skill_name_{folder_lower}_'
                if pattern in eid.lower():
                    suffix = eid[eid.lower().index(pattern) + len(pattern):]
                    if suffix.lower() != 'move' and clean not in seen:
                        seen.add(clean)
                        skills.append(clean)

            # Find camp skills from JSON
            camp_custom = []
            camp_vanilla = []
            camping_json = mod_path / 'raid' / 'camping' / f'{folder_lower}.camping_skills.json'
            if camping_json.exists():
                try:
                    with open(camping_json, 'r', encoding='utf-8') as f:
                        cdata = json.load(f)
                    VANILLA_IDS = {
                        'encourage','first_aid','wound_care','pep_talk','clean_guns',
                        'bandits_sense','maintain_equipment','anger_management','eldritch_blood',
                        'psych_up','the_quickening','resupply','trinket_scrounge','strange_powders',
                        'tracking','this_is_how_we_planned_it','caltrops','zealous_speech',
                        'zealous_vigil','unshakeable_leader','stand_tall','lash_anger','lash_kiss',
                        'self_flagellation','absolution','suffer','snuff_box','gallows_humor',
                        'pilfer','night_moves','battle_trance','revel','reject_the_gods',
                        'sharpen_swords','unparalleled_finesse','clean_musket','therapy_dog',
                        'hounds_watch','release_the_hound','lick_wounds','man_and_best_friend',
                        'every_rose_has_its_thorn','turn_back_time','tiger_eye','mockery',
                        'quarantine','reflection','bloody_shroud','let_the_mask_down','tactics',
                        'weapons_practice','instruction','stand_guard','snipers_mark',
                        'field_dressing','abandon_hope','dark_strength','unspeakable_commune',
                        'dark_ritual','the_cure','experimental_vapours','leeches','self_medicate',
                        'serpent_sway','snake_eyes','adders_embrace','bless','sanctuary','pray','chant'
                    }
                    camp_id_to_name = {}
                    for eid2, text2 in all_entries.items():
                        if 'camping_skill_name_' in eid2.lower() and text2:
                            camp_id_to_name[eid2.lower().replace('camping_skill_name_', '')] = clean_colour(text2).title()

                    for skill in cdata.get('skills', []):
                        sid = skill.get('id', '').lower()
                        name_c = camp_id_to_name.get(sid, sid.replace('_', ' ').title())
                        if sid in VANILLA_IDS:
                            camp_vanilla.append(name_c)
                        else:
                            camp_custom.append(name_c)
                except:
                    pass

            # Find trinkets
            trinkets = []
            seen_trinkets = set()
            for eid, text in all_entries.items():
                clean = clean_colour(text)
                if 'str_inventory_title_trinket' in eid.lower() and clean and clean not in seen_trinkets:
                    seen_trinkets.add(clean)
                    trinkets.append(clean)

            # Check if we got useful data
            has_new_data = len(skills) > 0 or display_name
            if not has_new_data:
                continue

            # Find the existing entry for this hero in modded_heroes.js and update it
            old_names = fixable[modid]
            # Match by folder name or old broken name
            matched_old_name = None
            for old_name in old_names:
                old_lower = old_name.lower().replace(' ', '').replace("'", "").replace("(", "").replace(")", "")
                fldr_lower = folder_lower.replace(" ", "").replace("'", "")
                if old_lower == fldr_lower or fldr_lower in old_lower or old_lower in fldr_lower:
                    matched_old_name = old_name
                    break

            if not matched_old_name:
                # Try matching by display name
                if display_name:
                    for old_name in old_names:
                        if old_name in problems[modid]:
                            dn_lower = display_name.lower().replace(' ', '')
                            on_lower = old_name.lower().replace(' ', '')
                            if dn_lower in on_lower or on_lower in dn_lower:
                                matched_old_name = old_name
                                break

            use_name = display_name or matched_old_name or folder.replace('_', ' ').title()
            use_name = clean_colour(use_name)

            all_camp = camp_vanilla + camp_custom

            print(f"  {modid} | {folder} -> {use_name}: {len(skills)} skills, {len(all_camp)} camp, {len(trinkets)} trinkets")
            fixes_applied += 1

            # Now update the JS file - replace the old entry
            if matched_old_name:
                escaped = re.escape(matched_old_name)
                old_entry_pat = rf"  '{escaped}': \{{\s*\n(.*?)\n  \}}"
                old_match = re.search(old_entry_pat, content, re.DOTALL)
                if old_match:
                    # Build new entry
                    def fmt_arr(items, indent=6):
                        if not items:
                            return ''
                        ind = ' ' * indent
                        return ',\n'.join(f"{ind}'{i.replace(chr(39), chr(92)+chr(39))}'" for i in items)

                    # Get modId and image from old entry
                    old_block = old_match.group(1)
                    old_modid_m = re.search(r"modId: '(\d+)'" , old_block)
                    old_image_m = re.search(r"image: '([^']+)'" , old_block)
                    use_modid = old_modid_m.group(1) if old_modid_m else modid
                    old_image = old_image_m.group(1) if old_image_m else f'{modid}.png'

                    # Find actual image on disk
                    img_name = to_image_filename(use_name) + '.png'
                    if not (HEROES_DIR / img_name).exists():
                        img_name = old_image  # keep old
                        if not (HEROES_DIR / img_name).exists():
                            img_name = f'{modid}.png'
                            if not (HEROES_DIR / img_name).exists():
                                img_name = f'{folder_lower}.png'

                    new_entry = f"""  '{use_name}': {{
    modId: '{use_modid}',
    skills: [
{fmt_arr(skills)}
    ],
    campSkills: [
{fmt_arr(all_camp)}
    ],
    vanillaCampSkills: [
{fmt_arr(camp_vanilla)}
    ],
    image: '{img_name}',
    classSpecificTrinkets: [
{fmt_arr(trinkets)}
    ]
  }},"""

                    content = content[:old_match.start()] + new_entry + content[old_match.end()+1:]

    # Write back
    with open(JS_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\nFixes applied: {fixes_applied}")


if __name__ == '__main__':
    main()
