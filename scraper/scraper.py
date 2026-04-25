"""
DD Mod Scraper - CLI orchestrator for batch-scraping Darkest Dungeon mods.

Usage:
    python scraper.py                    # Show status summary
    python scraper.py --all              # Scrape all new/changed mods
    python scraper.py --mod ID [ID...]   # Scrape specific mods
    python scraper.py --dry-run [--all|--mod]  # Analyze without writing
    python scraper.py --force            # Re-scrape ignoring manifest
    python scraper.py --validate         # Check image/JS data consistency
"""
import argparse
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for unicode chars
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add this directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import config
from dd_mod_scraper import DarkestDungeonModScraper


# Paths derived from config
IMAGES_OUTPUT = Path(config.ASSETS_REPO) / 'images' / 'modded'
JS_OUTPUT = Path(config.APP_REPO) / 'src' / 'data' / 'modded_heroes.js'
MANIFEST_PATH = Path(__file__).parent / 'manifest.json'


def load_manifest() -> dict:
    """Load the manifest file, or return empty structure if it doesn't exist."""
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'version': 1, 'mods': {}}


def save_manifest(manifest: dict):
    """Save the manifest file."""
    manifest['last_run'] = datetime.now().isoformat(timespec='seconds')
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def get_mod_fingerprint(mod_path: Path) -> dict:
    """Compute a lightweight fingerprint of a mod directory for change detection."""
    fingerprint = {}
    key_dirs = ['heroes', 'localization', 'raid', 'panels']
    for key_dir in key_dirs:
        dir_path = mod_path / key_dir
        if dir_path.exists():
            # Use mtime + file count as fingerprint
            try:
                mtime = dir_path.stat().st_mtime
                file_count = sum(1 for _ in dir_path.rglob('*') if _.is_file())
                fingerprint[key_dir] = {'mtime': mtime, 'files': file_count}
            except OSError:
                fingerprint[key_dir] = None
    return fingerprint


def mod_needs_scraping(mod_id: str, manifest: dict, force: bool = False) -> bool:
    """Check if a mod needs to be (re-)scraped based on manifest and file changes."""
    if force:
        return True

    mod_entry = manifest['mods'].get(mod_id)
    if not mod_entry:
        return True

    if mod_entry.get('status') != 'success':
        return True

    # Compare fingerprints
    mod_path = Path(config.STEAM_WORKSHOP) / mod_id
    if not mod_path.exists():
        return False

    saved_fp = mod_entry.get('fingerprint', {})
    current_fp = get_mod_fingerprint(mod_path)

    for key in current_fp:
        if current_fp[key] is None:
            continue
        saved = saved_fp.get(key)
        if not saved:
            return True
        if saved.get('mtime') != current_fp[key].get('mtime') or saved.get('files') != current_fp[key].get('files'):
            return True

    return False


def get_all_mod_ids() -> list[str]:
    """List all workshop mod IDs."""
    workshop = Path(config.STEAM_WORKSHOP)
    if not workshop.exists():
        print(f"Workshop path not found: {workshop}")
        return []
    return sorted(d.name for d in workshop.iterdir() if d.is_dir())


def is_hero_mod(mod_id: str) -> bool:
    """Quick check if a mod contains hero content."""
    mod_path = Path(config.STEAM_WORKSHOP) / mod_id
    heroes_dir = mod_path / 'heroes'
    if not heroes_dir.exists():
        return False
    # At least one subdirectory in heroes/
    return any(d.is_dir() for d in heroes_dir.iterdir())


def analyze_mod(mod_id: str) -> dict | None:
    """Analyze a mod and return extracted data (read-only, no file writes)."""
    mod_path = Path(config.STEAM_WORKSHOP) / mod_id
    if not mod_path.exists():
        return None

    scraper = DarkestDungeonModScraper(str(mod_path))
    hero_classes = scraper.find_all_hero_classes()
    if not hero_classes:
        return None

    heroes_data = []
    for hero_class in hero_classes:
        internal_id = scraper.find_hero_internal_id(hero_class)
        display_name = scraper.get_hero_class_display_name(hero_class, internal_id)
        skills = scraper.get_combat_skills(hero_class, internal_id)
        custom_camp, vanilla_camp, camp_id_map = scraper.get_camp_skills(hero_class)
        trinkets = scraper.get_trinkets_for_hero(hero_class, internal_id)

        heroes_data.append({
            'folder': hero_class,
            'internal_id': internal_id,
            'display_name': display_name,
            'skills': skills,
            'camp_skills': vanilla_camp + custom_camp,
            'vanilla_camp_skills': vanilla_camp,
            'custom_camp_skills': custom_camp,
            'trinkets': trinkets,
        })

    return {
        'mod_id': mod_id,
        'heroes': heroes_data,
        'fingerprint': get_mod_fingerprint(mod_path),
    }


def scrape_mod(mod_id: str, dry_run: bool = False) -> dict:
    """Scrape a single mod: extract data, copy images, update JS."""
    mod_path = Path(config.STEAM_WORKSHOP) / mod_id
    if not mod_path.exists():
        return {'mod_id': mod_id, 'status': 'error', 'error': 'Mod directory not found'}

    scraper = DarkestDungeonModScraper(str(mod_path))
    hero_classes = scraper.find_all_hero_classes()
    if not hero_classes:
        return {'mod_id': mod_id, 'status': 'skipped', 'reason': 'No hero classes found'}

    result = {
        'mod_id': mod_id,
        'status': 'success',
        'heroes': [],
        'images_written': {'heroes': 0, 'skills': 0, 'camp_skills': 0, 'trinkets': 0},
        'fingerprint': get_mod_fingerprint(mod_path),
    }

    for hero_class in hero_classes:
        internal_id = scraper.find_hero_internal_id(hero_class)
        display_name = scraper.get_hero_class_display_name(hero_class, internal_id)
        skills = scraper.get_combat_skills(hero_class, internal_id)
        custom_camp, vanilla_camp, camp_id_map = scraper.get_camp_skills(hero_class)
        trinkets = scraper.get_trinkets_for_hero(hero_class, internal_id)
        all_camp = vanilla_camp + custom_camp

        hero_info = {
            'folder': hero_class,
            'display_name': display_name,
            'skills': skills,
            'camp_skills': all_camp,
            'trinkets': trinkets,
        }
        result['heroes'].append(hero_info)

        if dry_run:
            print(f"  [DRY RUN] Would scrape: {display_name} ({len(skills)} skills, {len(trinkets)} trinkets)")
            continue

        # Copy images directly to assets repo
        scraper.copy_hero_portrait(hero_class, output_path=IMAGES_OUTPUT)
        scraper.copy_skill_images(hero_class, skills, output_path=IMAGES_OUTPUT)
        scraper.copy_camp_skill_images(hero_class, all_camp, camp_id_map, output_path=IMAGES_OUTPUT)
        scraper.copy_trinket_images_for_hero(hero_class, internal_id, output_path=IMAGES_OUTPUT)

        # Update JS data in main app
        scraper.update_modded_heroes_js(
            display_name, skills, all_camp,
            vanilla_camp, trinkets, hero_class,
            js_path=str(JS_OUTPUT)
        )

        # Count written images
        mod_prefix = f"{mod_id}_"
        for category in ['heroes', 'skills', 'camp_skills', 'trinkets']:
            cat_dir = IMAGES_OUTPUT / category
            if cat_dir.exists():
                result['images_written'][category] = sum(
                    1 for f in cat_dir.iterdir()
                    if f.is_file() and f.name.startswith(mod_prefix)
                )

    if not dry_run and result['heroes']:
        # Auto-sort modded_heroes.js after all heroes are written
        sort_modded_heroes_js()

    return result


def sort_modded_heroes_js():
    """Sort entries in modded_heroes.js alphabetically."""
    if not JS_OUTPUT.exists():
        return

    with open(JS_OUTPUT, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract header (everything up to the opening of MODDED_HERO_CLASSES)
    header_match = re.match(r'^(.*?export const MODDED_HERO_CLASSES = \{)\s*\n', content, re.DOTALL)
    if not header_match:
        return

    header = header_match.group(1)
    obj_start = header_match.end()

    # Find the closing brace by counting braces
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

    if obj_end == obj_start:
        return

    obj_content = content[obj_start:obj_end]
    remaining = content[obj_end + 1:]
    if remaining.startswith(';'):
        remaining = remaining[1:]

    # Parse individual hero entries
    pattern = r"(\s*'([^']+)':\s*\{)"
    matches = list(re.finditer(pattern, obj_content))

    classes = {}
    for i, match in enumerate(matches):
        class_name = match.group(2)
        start_pos = match.start()

        brace_count = 0
        in_string = False
        escape_next = False
        end_pos = start_pos

        content_from_match = obj_content[match.end() - 1:]
        for j, char in enumerate(content_from_match):
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

        class_content = obj_content[start_pos:end_pos].rstrip()
        if class_content.endswith(','):
            class_content = class_content[:-1]
        classes[class_name] = class_content.strip()

    # Sort alphabetically (case-insensitive)
    sorted_names = sorted(classes.keys(), key=lambda x: x.lower())

    # Rebuild
    sorted_content = header + '\n'
    for i, name in enumerate(sorted_names):
        block = classes[name]
        lines = block.split('\n')
        if not lines[0].startswith('  '):
            lines[0] = '  ' + lines[0].lstrip()
        sorted_content += '\n'.join(lines)
        if i < len(sorted_names) - 1:
            sorted_content += ','
        sorted_content += '\n'

    sorted_content += '};\n' + remaining

    with open(JS_OUTPUT, 'w', encoding='utf-8') as f:
        f.write(sorted_content)

    print(f"  Sorted {len(sorted_names)} hero entries alphabetically")


def cmd_status(manifest: dict):
    """Show current manifest status."""
    all_mods = get_all_mod_ids()
    hero_mods = [m for m in all_mods if is_hero_mod(m)]

    scraped = sum(1 for m in hero_mods if manifest['mods'].get(m, {}).get('status') == 'success')
    new_or_changed = sum(1 for m in hero_mods if mod_needs_scraping(m, manifest))

    print(f"\n{'='*60}")
    print("DD MOD SCRAPER - STATUS")
    print(f"{'='*60}")
    print(f"  Workshop path: {config.STEAM_WORKSHOP}")
    print(f"  Assets output: {IMAGES_OUTPUT}")
    print(f"  JS output:     {JS_OUTPUT}")
    print(f"  Total workshop mods: {len(all_mods)}")
    print(f"  Hero mods: {len(hero_mods)}")
    print(f"  Already scraped: {scraped}")
    print(f"  New/changed: {new_or_changed}")
    print(f"{'='*60}\n")


def cmd_scrape(mod_ids: list[str], dry_run: bool, force: bool, manifest: dict):
    """Scrape specified mods (or all if empty)."""
    if not mod_ids:
        # --all mode: scrape all hero mods that need it
        all_mods = get_all_mod_ids()
        hero_mods = [m for m in all_mods if is_hero_mod(m)]
        mod_ids = [m for m in hero_mods if mod_needs_scraping(m, manifest, force)]

    if not mod_ids:
        print("Nothing to scrape.")
        return

    print(f"\n{'='*60}")
    mode = "DRY RUN - " if dry_run else ""
    print(f"{mode}SCRAPING {len(mod_ids)} MOD(S)")
    print(f"{'='*60}\n")

    results = []
    for i, mod_id in enumerate(mod_ids):
        print(f"\n[{i+1}/{len(mod_ids)}] Processing mod: {mod_id}")
        print('-' * 40)

        try:
            result = scrape_mod(mod_id, dry_run=dry_run)
            results.append(result)

            if result['status'] == 'success':
                for hero in result['heroes']:
                    print(f"  {hero['display_name']}: {len(hero['skills'])} skills, {len(hero['trinkets'])} trinkets")

                if not dry_run:
                    manifest['mods'][mod_id] = {
                        'scraped_at': datetime.now().isoformat(timespec='seconds'),
                        'status': 'success',
                        'heroes': [h['display_name'] for h in result['heroes']],
                        'fingerprint': result['fingerprint'],
                        'images_written': result['images_written'],
                    }
            elif result['status'] == 'skipped':
                print(f"  Skipped: {result.get('reason', 'unknown')}")
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({'mod_id': mod_id, 'status': 'error', 'error': str(e)})
            manifest['mods'][mod_id] = {
                'scraped_at': datetime.now().isoformat(timespec='seconds'),
                'status': 'error',
                'error': str(e),
            }

    if not dry_run:
        save_manifest(manifest)

    # Summary
    success = sum(1 for r in results if r['status'] == 'success')
    errors = sum(1 for r in results if r['status'] == 'error')
    skipped = sum(1 for r in results if r['status'] == 'skipped')

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  Processed: {len(results)}")
    print(f"  Success: {success}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"{'='*60}\n")


def cmd_validate(manifest: dict):
    """Validate consistency between images on disk and JS data."""
    if not JS_OUTPUT.exists():
        print("modded_heroes.js not found")
        return

    with open(JS_OUTPUT, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse hero entries from JS
    hero_pattern = re.findall(r"'([^']+)':\s*\{\s*modId:\s*'(\d+)'", content)
    heroes_in_js = {name: mod_id for name, mod_id in hero_pattern}

    print(f"\n{'='*60}")
    print("VALIDATION")
    print(f"{'='*60}")
    print(f"  Heroes in modded_heroes.js: {len(heroes_in_js)}")

    # Check hero portraits
    missing_portraits = []
    for name, mod_id in heroes_in_js.items():
        sanitized = name.lower().replace("'", "").replace(" ", "_").replace("-", "")
        sanitized = re.sub(r'[^\w_]', '', sanitized)
        portrait_path = IMAGES_OUTPUT / 'heroes' / f'{sanitized}.png'
        # Also check with modId (older naming)
        alt_portrait = IMAGES_OUTPUT / 'heroes' / f'{mod_id}.png'
        if not portrait_path.exists() and not alt_portrait.exists():
            missing_portraits.append((name, sanitized))

    if missing_portraits:
        print(f"\n  Missing hero portraits ({len(missing_portraits)}):")
        for name, filename in missing_portraits:
            print(f"    - {name} (expected: {filename}.png)")
    else:
        print(f"  All hero portraits present")

    # Check skill images
    missing_skills = []
    for name, mod_id in heroes_in_js.items():
        # Find skills for this hero
        skills_match = re.search(
            rf"'{re.escape(name)}':\s*\{{[^}}]*?skills:\s*\[(.*?)\]",
            content, re.DOTALL
        )
        if skills_match:
            skills_str = skills_match.group(1)
            skill_names = re.findall(r"'([^']+)'", skills_str)
            for skill in skill_names:
                sanitized = skill.lower().replace("'", "").replace(" ", "_").replace("-", "")
                sanitized = re.sub(r'[^\w_]', '', sanitized)
                skill_path = IMAGES_OUTPUT / 'skills' / f'{mod_id}_{sanitized}.png'
                if not skill_path.exists():
                    missing_skills.append((name, skill, f'{mod_id}_{sanitized}.png'))

    if missing_skills:
        print(f"\n  Missing skill images ({len(missing_skills)}):")
        for hero, skill, filename in missing_skills[:20]:
            print(f"    - {hero} / {skill} (expected: {filename})")
        if len(missing_skills) > 20:
            print(f"    ... and {len(missing_skills) - 20} more")
    else:
        print(f"  All skill images present")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description='DD Mod Scraper - Batch scrape Darkest Dungeon workshop mods')
    parser.add_argument('--all', action='store_true', help='Scrape all new/changed hero mods')
    parser.add_argument('--mod', nargs='+', metavar='ID', help='Scrape specific mod(s) by workshop ID')
    parser.add_argument('--dry-run', action='store_true', help='Analyze without writing files')
    parser.add_argument('--force', action='store_true', help='Re-scrape even if already in manifest')
    parser.add_argument('--validate', action='store_true', help='Check image/JS data consistency')
    parser.add_argument('--status', action='store_true', help='Show manifest status')

    args = parser.parse_args()

    # Validate paths
    if not Path(config.STEAM_WORKSHOP).exists():
        print(f"ERROR: Workshop path not found: {config.STEAM_WORKSHOP}")
        print("Edit scraper/config.py with your Steam workshop path.")
        sys.exit(2)

    manifest = load_manifest()

    if args.validate:
        cmd_validate(manifest)
    elif args.status:
        cmd_status(manifest)
    elif args.all or args.mod:
        mod_ids = args.mod or []
        cmd_scrape(mod_ids, dry_run=args.dry_run, force=args.force, manifest=manifest)
    else:
        # Default: show status
        cmd_status(manifest)


if __name__ == '__main__':
    main()
