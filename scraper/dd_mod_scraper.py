import os
import shutil
import re
import xml.etree.ElementTree as ET
import json
from pathlib import Path
from typing import Dict, List, Optional


class DarkestDungeonModScraper:
    def __init__(self, mod_path: str, modded_output_path: str = None, modded_heroes_path: str = None):
        """
        Inicializa el scraper con las rutas necesarias.

        Args:
            mod_path: Ruta al directorio raíz del mod (ej: 924245318)
            modded_output_path: Ruta a la carpeta modded de salida (opcional, para compatibilidad)
            modded_heroes_path: Ruta al archivo modded_heroes.js (opcional, para compatibilidad)
        """
        self.mod_path = Path(mod_path)
        self.modded_output_path = Path(modded_output_path) if modded_output_path else None
        self.modded_heroes_path = Path(modded_heroes_path) if modded_heroes_path else None
        self.mod_id = self.mod_path.name

        # Crear subcarpetas si se proporcionó output_path
        if self.modded_output_path:
            self.create_output_folders()
        
    def create_output_folders(self):
        """Crea las carpetas de salida necesarias."""
        folders = ['heroes', 'skills', 'camp_skills', 'trinkets']
        for folder in folders:
            (self.modded_output_path / folder).mkdir(parents=True, exist_ok=True)
    
    def is_valid_hero_folder(self, folder_path: Path) -> bool:
        """
        Determina si una carpeta contiene un héroe nuevo válido (no solo override de vanilla).
        
        Una carpeta es válida si:
        - Tiene archivo .info.darkest, o
        - Tiene imágenes de abilities (.ability.*.png), o
        - Tiene subcarpetas de skins (_A, _B, etc.)
        
        Una carpeta es inválida si solo tiene archivos .override.darkest
        """
        if not folder_path.is_dir():
            return False
        
        has_info_file = False
        has_ability_images = False
        has_skin_folders = False
        only_has_override = True
        
        for item in folder_path.iterdir():
            if item.is_file():
                name_lower = item.name.lower()
                if name_lower.endswith('.info.darkest'):
                    has_info_file = True
                    only_has_override = False
                elif '.ability.' in name_lower and name_lower.endswith('.png'):
                    has_ability_images = True
                    only_has_override = False
                elif not name_lower.endswith('.override.darkest'):
                    only_has_override = False
            elif item.is_dir():
                # Subcarpetas como hero_A, hero_B son skins
                if item.name.endswith(('_A', '_B', '_C', '_D', '_E', '_F')):
                    has_skin_folders = True
                    only_has_override = False
                elif item.name in ('anim', 'fx', 'icons_equip'):
                    only_has_override = False
        
        # Es válido si tiene contenido de héroe y no es solo un override
        return (has_info_file or has_ability_images or has_skin_folders) and not only_has_override
    
    def find_all_hero_classes(self) -> List[str]:
        """
        Encuentra todas las clases de héroe válidas del mod.
        
        Excluye:
        - Subcarpetas de variantes (_A, _B, _C, _D)
        - Carpetas que solo contienen overrides de clases vanilla (.override.darkest)
        
        Returns:
            Lista de nombres de carpetas de héroes válidos
        """
        heroes_path = self.mod_path / 'heroes'
        hero_classes = []
        
        if heroes_path.exists():
            for item in heroes_path.iterdir():
                # Excluir variantes de skin
                if item.is_dir() and not item.name.endswith(('_A', '_B', '_C', '_D', '_E', '_F')):
                    # Verificar si es una carpeta de héroe válida
                    if self.is_valid_hero_folder(item):
                        hero_classes.append(item.name)
        
        return sorted(hero_classes)  # Ordenar para consistencia
    
    def find_hero_class_name(self) -> Optional[str]:
        """
        Encuentra el nombre de la clase del héroe desde los archivos.
        NOTA: Retorna solo el primer héroe. Para mods multi-héroe usar find_all_hero_classes().
        """
        hero_classes = self.find_all_hero_classes()
        return hero_classes[0] if hero_classes else None
    
    def find_hero_internal_id(self, folder_name: str) -> str:
        """
        Encuentra el ID interno del héroe buscando hero_class_name_* en los archivos de localización.
        Algunos mods usan un ID diferente al nombre de la carpeta (ej: demiurge usa 7FG).
        
        Args:
            folder_name: Nombre de la carpeta del héroe
            
        Returns:
            El ID interno del héroe (puede ser diferente al nombre de la carpeta)
        """
        localization_path = self.mod_path / 'localization'
        
        if not localization_path.exists():
            return folder_name
        
        # Primero, verificar si el nombre de la carpeta es un ID válido
        # Buscar combat_skill_name_{folder_name}_ en todos los archivos
        folder_lower = folder_name.lower()
        for file in localization_path.glob('*.xml'):
            if 'string_table' in file.stem.lower():
                # Leer contenido raw para buscar sin depender del parser de idiomas
                try:
                    with open(file, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read().lower()
                    if f'combat_skill_name_{folder_lower}_' in content:
                        # El nombre de carpeta es un ID válido
                        return folder_name
                except:
                    pass
        
        # Si el nombre de carpeta no es un ID válido, buscar un ID alternativo
        # Solo en archivos en inglés
        for file in localization_path.glob('*.xml'):
            if 'string_table' in file.stem.lower():
                entries = self.parse_string_table(file)
                
                for entry_id in entries.keys():
                    # Patrón: hero_class_name_<id> o hero_name_<id>
                    if entry_id.startswith('hero_class_name_') or entry_id.startswith('hero_name_'):
                        # Extraer el ID
                        if entry_id.startswith('hero_class_name_'):
                            internal_id = entry_id.replace('hero_class_name_', '')
                        else:
                            internal_id = entry_id.replace('hero_name_', '')
                        
                        # Verificar que hay combat_skills con este ID
                        for other_id in entries.keys():
                            if f'combat_skill_name_{internal_id}_' in other_id:
                                return internal_id
        
        return folder_name
    
    def is_english_file(self, file_path: Path) -> bool:
        """
        Determina si un archivo es en inglés.
        
        Args:
            file_path: Ruta al archivo a verificar
            
        Returns:
            True si es un archivo en inglés, False en caso contrario
        """
        filename_lower = file_path.stem.lower()
        
        # Lista de idiomas a excluir
        exclude_languages = [
            'brazilian', 'czech', 'french', 'german', 'italian', 
            'japanese', 'koreana', 'polish', 'russian', 
            'schinese', 'spanish', 'tchinese', 'portuguese',
            'chinese', 'korean', 'dutch', 'turkish'
        ]
        
        # Si el nombre del archivo contiene algún idioma a excluir, no es inglés
        if any(lang in filename_lower for lang in exclude_languages):
            return False
        
        # Si el archivo contiene "english" explícitamente, es inglés
        if 'english' in filename_lower:
            return True
        
        # Archivos sin sufijo de idioma se asumen en inglés
        # (como hero.string_table.xml, hero_exp.string_table.xml)
        return True
    
    def parse_string_table(self, file_path: Path, force_parse: bool = False) -> Dict[str, str]:
        """
        Parsea un archivo .string_table.xml y extrae las entradas SOLO de la sección en inglés.
        
        Args:
            file_path: Ruta al archivo XML
            force_parse: Si es True, ignora el filtro por nombre de archivo
            
        Returns:
            Diccionario con id -> texto
        """
        entries = {}
        
        # Verificar primero si el archivo es en inglés por su nombre
        # A menos que force_parse sea True
        if not force_parse and not self.is_english_file(file_path):
            return entries
        
        try:
            # Intentar con múltiples encodings para manejar archivos mal codificados
            content = None
            encodings_to_try = ['utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'latin-1']
            
            for encoding in encodings_to_try:
                try:
                    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                        content = f.read()
                    # Verificar si tiene caracteres de reemplazo problemáticos
                    # (mojibake típico de UTF-8 leído como Latin-1)
                    if 'ï¿½' not in content and '\ufffd' not in content:
                        break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                # Fallback: leer con latin-1 que acepta cualquier byte
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            
            # Problema: XML no permite "--" dentro de comentarios excepto al inicio/fin
            # Solución: Reemplazar comentarios problemáticos
            
            # Función para limpiar el contenido de comentarios
            def fix_comment(match):
                comment_content = match.group(1)
                # Reemplazar múltiples guiones por un solo guion
                cleaned = re.sub(r'-{2,}', '-', comment_content)
                # Limpiar guiones al inicio y final
                cleaned = cleaned.strip('-').strip()
                # Si queda vacío, devolver cadena vacía (eliminar comentario)
                if not cleaned:
                    return ''
                return f'<!-- {cleaned} -->'
            
            # Buscar y corregir todos los comentarios
            content = re.sub(r'<!--(.+?)-->', fix_comment, content, flags=re.DOTALL)
            
            # Eliminar comentarios vacíos que puedan haber quedado
            content = re.sub(r'<!--\s*-->', '', content)
            
            # También manejar comentarios mal formados (<!--- o --->)
            content = re.sub(r'<!-{3,}', r'<!--', content)
            content = re.sub(r'-{3,}>', r'-->', content)
            
            # Limpiar caracteres de control ilegales en XML (excepto tab, newline, carriage return)
            content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)
            
            # Corregir etiquetas XML duplicadas (<<entry -> <entry, <</ -> </)
            content = re.sub(r'<{2,}', '<', content)
            content = re.sub(r'>{2,}', '>', content)
            
            # Parsear el XML corregido
            root = ET.fromstring(content)
            
            # Buscar específicamente la sección de idioma inglés
            english_section = root.find(".//language[@id='english']")
            
            if english_section is not None:
                # Solo extraer entradas dentro de la sección de inglés
                for entry in english_section.findall('entry'):
                    entry_id = entry.get('id')
                    text = entry.text or ''
                    # Limpiar CDATA si existe
                    text = text.strip()
                    if entry_id and text:
                        entries[entry_id] = text
            else:
                # Si no hay sección de idioma, verificar que no haya secciones de otros idiomas
                all_language_sections = root.findall(".//language")
                
                # Si hay secciones de idioma pero ninguna es inglés, no extraer nada
                if all_language_sections:
                    # Verificar si alguna sección es de otro idioma
                    for lang_section in all_language_sections:
                        lang_id = lang_section.get('id', '').lower()
                        if lang_id and lang_id != 'english':
                            # Hay una sección de otro idioma, no procesar este archivo
                            return entries
                
                # Si no hay secciones de idioma, extraer todas las entradas (formato antiguo)
                for entry in root.findall('.//entry'):
                    entry_id = entry.get('id')
                    text = entry.text or ''
                    text = text.strip()
                    if entry_id and text:
                        entries[entry_id] = text
                        
        except ET.ParseError as e:
            # XML parser failed - try regex fallback to extract entries
            if content:
                entry_pattern = re.compile(r'<entry\s+id="([^"]+)"[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</entry>', re.DOTALL)
                for m in entry_pattern.finditer(content):
                    entry_id = m.group(1)
                    text = m.group(2).strip()
                    if entry_id and text:
                        entries[entry_id] = text
        except Exception as e:
            print(f"⚠ Error procesando {file_path.name}: {e}")
        
        return entries
    
    def clean_skill_name(self, text: str) -> str:
        """
        Limpia el nombre de una skill eliminando códigos de formato del juego.
        
        Args:
            text: Texto con posibles códigos de formato
            
        Returns:
            Texto limpio
        """
        # Eliminar códigos de color: {colour_start|...} y {colour_end}
        text = re.sub(r'\{colour_start\|[^}]+\}', '', text)
        text = re.sub(r'\{colour_end\}', '', text)
        
        # Eliminar símbolos especiales usados para iconos
        text = re.sub(r'[¤]+', '', text)
        
        # Limpiar saltos de línea y espacios múltiples
        text = text.replace('\n', ' ')
        text = ' '.join(text.split())
        
        return text.strip()
    
    def get_combat_skills(self, hero_class: str, internal_id: str = None) -> List[str]:
        """
        Obtiene los nombres de las habilidades de combate.
        
        Args:
            hero_class: Nombre de la carpeta del héroe
            internal_id: ID interno del héroe (si es diferente al nombre de carpeta)
        """
        localization_path = self.mod_path / 'localization'
        skills = []  # Usamos lista para mantener orden
        seen_skills = set()  # Para evitar duplicados
        
        if not localization_path.exists():
            return skills
        
        # Usar internal_id si está disponible, sino usar hero_class
        search_id = internal_id or hero_class
        
        # Buscar archivos .xml que contengan string_table
        for file in localization_path.glob('*.xml'):
            if 'string_table' in file.stem.lower():
                # Si el archivo contiene el nombre del héroe, forzar parseo
                # (para mods que nombran archivos como ectoplasm_schinese.string_table.xml)
                force = hero_class.lower() in file.stem.lower() or search_id.lower() in file.stem.lower()
                entries = self.parse_string_table(file, force_parse=force)
                
                # Buscar entradas de combat skills (case-insensitive)
                for entry_id, text in entries.items():
                    entry_id_lower = entry_id.lower()
                    search_pattern = f'combat_skill_name_{search_id.lower()}_'
                    
                    if search_pattern in entry_id_lower:
                        # Extraer el nombre de la skill usando el índice correcto
                        skill_suffix = entry_id[entry_id_lower.find(search_pattern) + len(search_pattern):]
                        # Ignorar "move" ya que es genérico
                        if skill_suffix.lower() != 'move' and text:
                            # Filtrar skills inválidas (URLs)
                            if text.startswith('http://') or text.startswith('https://'):
                                continue
                            
                            # Limpiar códigos de formato
                            clean_text = self.clean_skill_name(text)
                            
                            # Si después de limpiar queda vacío, saltar
                            if not clean_text:
                                continue
                            
                            # Añadir solo si no está duplicado
                            if clean_text not in seen_skills:
                                seen_skills.add(clean_text)
                                skills.append(clean_text)
        
        return skills
    
    def get_camp_skills(self, hero_class: str) -> tuple[List[str], List[str], Dict[str, str]]:
        """
        Obtiene las camp skills del héroe desde el archivo JSON de camping.
        Los nombres se obtienen de los archivos de localización del mod.
        
        Returns:
            Tupla (custom_camp_skills, vanilla_camp_skills, skill_id_to_display_name)
            - custom_camp_skills: Lista de nombres de skills custom del mod
            - vanilla_camp_skills: Lista de nombres de skills vanilla
            - skill_id_to_display_name: Mapeo de ID interno -> nombre legible (solo custom)
        """
        # Lista completa de IDs de vanilla camp skills del juego base
        VANILLA_CAMP_SKILL_IDS = {
            # Universales
            'encourage', 'first_aid', 'wound_care', 'pep_talk',
            # Arbalest
            'clean_guns', 'bandits_sense', 'maintain_equipment',
            # Abomination  
            'anger_management', 'eldritch_blood', 'psych_up', 'the_quickening',
            # Antiquarian
            'resupply', 'trinket_scrounge', 'strange_powders',
            # Bounty Hunter
            'tracking', 'this_is_how_we_planned_it', 'caltrops',
            # Crusader
            'zealous_speech', 'zealous_vigil', 'unshakeable_leader', 'stand_tall',
            # Flagellant
            'lash_anger', 'lash_kiss', 'self_flagellation', 'absolution', 'suffer',
            # Grave Robber
            'snuff_box', 'gallows_humor', 'pilfer', 'night_moves',
            # Hellion
            'battle_trance', 'revel', 'reject_the_gods', 'sharpen_swords',
            # Highwayman
            'unparalleled_finesse', 'clean_musket', 'tracking', 'bandits_sense',
            # Houndmaster
            'therapy_dog', 'hounds_watch', 'release_the_hound', 'lick_wounds', 'man_and_best_friend',
            # Jester
            'every_rose_has_its_thorn', 'turn_back_time', 'tiger_eye', 'mockery',
            # Leper
            'quarantine', 'reflection', 'bloody_shroud', 'let_the_mask_down',
            # Man at Arms
            'tactics', 'weapons_practice', 'instruction', 'stand_guard',
            # Musketeer (vanilla)
            'clean_musket', 'snipers_mark', 'field_dressing',
            # Occultist
            'abandon_hope', 'dark_strength', 'unspeakable_commune', 'dark_ritual',
            # Plague Doctor
            'the_cure', 'experimental_vapours', 'leeches', 'self_medicate',
            # Shieldbreaker
            'serpent_sway', 'snake_eyes', 'adders_embrace',
            # Vestal
            'bless', 'sanctuary', 'pray', 'chant',
        }
        
        # Nombres oficiales de las vanilla camp skills (fallback si no están en localización del mod)
        VANILLA_SKILL_NAMES = {
            'encourage': 'Encourage',
            'first_aid': 'Wound Care',  # El juego lo llama "Wound Care", no "First Aid"
            'wound_care': 'Wound Care',
            'pep_talk': 'Pep Talk',
            'clean_guns': 'Clean Guns',
            'bandits_sense': "Bandit's Sense",
            'maintain_equipment': 'Maintain Equipment',
            'anger_management': 'Anger Management',
            'eldritch_blood': 'Eldritch Blood',
            'psych_up': 'Psych Up',
            'the_quickening': 'The Quickening',
            'resupply': 'Resupply',
            'trinket_scrounge': 'Trinket Scrounge',
            'strange_powders': 'Strange Powders',
            'tracking': 'Tracking',
            'this_is_how_we_planned_it': 'This Is How We Planned It',
            'caltrops': 'Caltrops',
            'zealous_speech': 'Zealous Speech',
            'zealous_vigil': 'Zealous Vigil',
            'unshakeable_leader': 'Unshakeable Leader',
            'stand_tall': 'Stand Tall',
            'lash_anger': "Lash's Anger",
            'lash_kiss': "Lash's Kiss",
            'self_flagellation': 'Self-Flagellation',
            'absolution': 'Absolution',
            'suffer': 'Suffer',
            'snuff_box': 'Snuff Box',
            'gallows_humor': 'Gallows Humor',
            'pilfer': 'Pilfer',
            'night_moves': 'Night Moves',
            'battle_trance': 'Battle Trance',
            'revel': 'Revel',
            'reject_the_gods': 'Reject The Gods',
            'sharpen_swords': 'Sharpen Swords',
            'unparalleled_finesse': 'Unparalleled Finesse',
            'clean_musket': 'Clean Musket',
            'therapy_dog': 'Therapy Dog',
            'hounds_watch': "Hound's Watch",
            'release_the_hound': 'Release The Hound',
            'lick_wounds': 'Lick Wounds',
            'man_and_best_friend': 'Man And Best Friend',
            'every_rose_has_its_thorn': 'Every Rose Has Its Thorn',
            'turn_back_time': 'Turn Back Time',
            'tiger_eye': "Tiger's Eye",
            'mockery': 'Mockery',
            'quarantine': 'Quarantine',
            'reflection': 'Reflection',
            'bloody_shroud': 'Bloody Shroud',
            'let_the_mask_down': 'Let The Mask Down',
            'tactics': 'Tactics',
            'weapons_practice': 'Weapons Practice',
            'instruction': 'Instruction',
            'stand_guard': 'Stand Guard',
            'snipers_mark': "Sniper's Mark",
            'field_dressing': 'Field Dressing',
            'abandon_hope': 'Abandon Hope',
            'dark_strength': 'Dark Strength',
            'unspeakable_commune': 'Unspeakable Commune',
            'dark_ritual': 'Dark Ritual',
            'the_cure': 'The Cure',
            'experimental_vapours': 'Experimental Vapours',
            'leeches': 'Leeches',
            'self_medicate': 'Self-Medicate',
            'serpent_sway': 'Serpent Sway',
            'snake_eyes': 'Snake Eyes',
            'adders_embrace': "Adder's Embrace",
            'bless': 'Bless',
            'sanctuary': 'Sanctuary',
            'pray': 'Pray',
            'chant': 'Chant',
        }
        
        custom_skills = []
        vanilla_skills = []
        custom_skill_id_to_name = {}  # Mapeo ID -> nombre para skills custom
        localization_path = self.mod_path / 'localization'
        
        # Mapa de ID -> nombre legible desde localización del mod
        skill_id_to_name = {}
        if localization_path.exists():
            for file in localization_path.glob('*.xml'):
                if 'string_table' in file.stem.lower():
                    entries = self.parse_string_table(file)
                    for entry_id, text in entries.items():
                        # Patrón: camping_skill_name_<skill_id>
                        if 'camping_skill_name_' in entry_id.lower() and text:
                            skill_id = entry_id.lower().replace('camping_skill_name_', '')
                            skill_id_to_name[skill_id] = text.title()
        
        # Leer el archivo JSON de camping skills para saber qué skills tiene este héroe
        camping_json_path = self.mod_path / 'raid' / 'camping' / f'{hero_class.lower()}.camping_skills.json'
        if camping_json_path.exists():
            try:
                with open(camping_json_path, 'r', encoding='utf-8') as f:
                    camping_data = json.load(f)
                    
                for skill in camping_data.get('skills', []):
                    skill_id = skill.get('id', '').lower()
                    
                    # Prioridad para obtener nombre:
                    # 1. Localización del mod
                    # 2. Nombre vanilla predefinido (para skills vanilla)
                    # 3. ID formateado como fallback
                    if skill_id in skill_id_to_name:
                        skill_name = skill_id_to_name[skill_id]
                    elif skill_id in VANILLA_SKILL_NAMES:
                        skill_name = VANILLA_SKILL_NAMES[skill_id]
                    else:
                        skill_name = skill_id.replace('_', ' ').title()
                    
                    if skill_id in VANILLA_CAMP_SKILL_IDS:
                        vanilla_skills.append(skill_name)
                    else:
                        custom_skills.append(skill_name)
                        custom_skill_id_to_name[skill_id] = skill_name
                        
            except Exception as e:
                print(f"Error leyendo camping skills JSON: {e}")
        else:
            # Fallback: usar solo localización si no hay JSON
            for skill_id, skill_name in skill_id_to_name.items():
                if skill_id in VANILLA_CAMP_SKILL_IDS:
                    vanilla_skills.append(skill_name)
                else:
                    custom_skills.append(skill_name)
                    custom_skill_id_to_name[skill_id] = skill_name
        
        return custom_skills, vanilla_skills, custom_skill_id_to_name
    
    def get_trinkets(self) -> List[str]:
        """Obtiene la lista de trinkets específicos de la clase."""
        localization_path = self.mod_path / 'localization'
        trinkets = []
        
        if not localization_path.exists():
            print(f"✗ No se encontró carpeta de localización: {localization_path}")
            return trinkets
        
        # Buscar TODOS los archivos .xml en localization
        for file in localization_path.glob('*.xml'):
            # Solo procesar archivos que contengan 'string_table' y sean en inglés
            # o archivos _exp/_dexp sin sufijo de idioma
            filename_lower = file.stem.lower()
            
            # Filtrar archivos que NO son en inglés (contienen idiomas como brazilian, czech, etc.)
            skip_languages = ['brazilian', 'czech', 'french', 'german', 'italian', 
                            'japanese', 'koreana', 'polish', 'russian', 
                            'schinese', 'spanish', 'tchinese']
            
            if any(lang in filename_lower for lang in skip_languages):
                continue
            
            # Procesar si es un archivo string_table
            if 'string_table' in filename_lower:
                print(f"  Procesando archivo: {file.name}")
                entries = self.parse_string_table(file)
                
                for entry_id, text in entries.items():
                    # Buscar trinkets con diferentes patrones
                    if ('str_inventory_title_trinket' in entry_id.lower() and 
                        text and 
                        text.strip()):
                        # Evitar duplicados
                        if text not in trinkets:
                            trinkets.append(text)
                            print(f"    ✓ Trinket encontrado: {text}")
        
        return trinkets
    
    def get_trinkets_for_hero(self, hero_class: str, internal_id: str = None) -> List[str]:
        """
        Obtiene trinkets para un héroe específico.
        Por ahora, retorna todos los trinkets del mod ya que es difícil
        determinar a qué héroe pertenece cada trinket.
        
        Args:
            hero_class: Nombre de la carpeta del héroe
            internal_id: ID interno del héroe
        """
        return self.get_trinkets()
    
    def copy_trinket_images_for_hero(self, hero_class: str, internal_id: str = None, output_path: Path = None):
        """
        Copia las imágenes de trinkets para un héroe específico.
        Por ahora, copia todos los trinkets del mod.

        Args:
            hero_class: Nombre de la carpeta del héroe
            internal_id: ID interno del héroe
            output_path: Ruta de salida (sobreescribe self.modded_output_path)
        """
        self.copy_trinket_images(output_path=output_path)
    
    def get_hero_class_display_name(self, hero_class: str, internal_id: str = None) -> str:
        """
        Obtiene el nombre legible de la clase desde los string tables.
        
        Args:
            hero_class: Nombre de la carpeta del héroe
            internal_id: ID interno del héroe (puede ser diferente)
        """
        localization_path = self.mod_path / 'localization'
        
        if not localization_path.exists():
            return hero_class.replace('_', ' ').title()
        
        # IDs a buscar (primero internal_id, luego hero_class)
        search_ids = [internal_id.lower(), hero_class.lower()] if internal_id else [hero_class.lower()]
        
        # Buscar en archivos .xml que contengan string_table
        for file in localization_path.glob('*.xml'):
            if 'string_table' in file.stem.lower():
                # Forzar parseo si el archivo contiene el nombre del héroe
                force = hero_class.lower() in file.stem.lower()
                if internal_id:
                    force = force or internal_id.lower() in file.stem.lower()
                entries = self.parse_string_table(file, force_parse=force)
                
                for search_id in search_ids:
                    # Buscar el nombre de la clase con diferentes patrones
                    for entry_id, text in entries.items():
                        # Patron 1: hero_name_<id>
                        if f'hero_name_{search_id}' == entry_id and text:
                            return text
                        # Patron 2: hero_class_name_<id>
                        if f'hero_class_name_{search_id}' == entry_id and text:
                            return text
        
        # Si no se encuentra, convertir el nombre de la clase
        return hero_class.replace('_', ' ').title()
    
    def copy_hero_portrait(self, hero_class: str, output_path: Path = None):
        """Copia el retrato del héroe a la carpeta de salida."""
        out = Path(output_path) if output_path else self.modded_output_path
        if not out:
            print("✗ No se proporcionó ruta de salida para retrato")
            return

        # Buscar el retrato en la carpeta del héroe
        hero_folders = list((self.mod_path / 'heroes' / hero_class.lower()).glob(f'{hero_class.lower()}_?'))

        if hero_folders:
            # Usar la primera variante encontrada (A, B, C, D)
            portrait_path = hero_folders[0] / f'{hero_class.lower()}_portrait_roster.png'

            if portrait_path.exists():
                # Crear nombre de salida sanitizado
                sanitized_name = self.sanitize_filename(hero_class.lower())
                output_name = f'{sanitized_name}.png'
                dest = out / 'heroes' / output_name
                dest.parent.mkdir(parents=True, exist_ok=True)

                shutil.copy2(portrait_path, dest)
                print(f"✓ Copiado retrato: {output_name}")
            else:
                print(f"✗ No se encontró retrato en {portrait_path}")
    
    def sanitize_filename(self, filename: str) -> str:
        r"""
        Sanitiza un nombre de archivo eliminando caracteres no válidos y especiales.
        
        Elimina:
        - Caracteres no válidos en Windows: < > : " / \ | ? *
        - Caracteres especiales: ' ! ` ~ @ # $ % ^ & ( ) + = { } [ ] ; ,
        - Caracteres acentuados/unicode: ä ö ü á é í ó ú ñ etc.
        - Emoji y caracteres de control
        
        Args:
            filename: Nombre de archivo a sanitizar
            
        Returns:
            Nombre de archivo válido con solo caracteres ASCII alfanuméricos
        """
        import unicodedata
        
        # Normalizar caracteres Unicode (ä -> a, é -> e, etc.)
        filename = unicodedata.normalize('NFKD', filename)
        filename = filename.encode('ASCII', 'ignore').decode('ASCII')
        
        # Lista de caracteres a eliminar (además de los no-ASCII ya eliminados)
        # Incluye puntos porque "...and" se vuelve problemático
        chars_to_remove = '<>:"/\\|?*\'!`~@#$%^&()+={}[];,.。！？'
        
        for char in chars_to_remove:
            filename = filename.replace(char, '')
        
        # Reemplazar caracteres especiales restantes
        # Solo permitir: letras, números, espacios, guiones, guiones bajos
        filename = re.sub(r'[^\w\s\-_]', '', filename)
        
        # Eliminar espacios múltiples y espacios al inicio/final
        filename = ' '.join(filename.split())
        filename = filename.strip()
        
        return filename
    
    def copy_skill_images(self, hero_class: str, skills: List[str], output_path: Path = None):
        """Copia las imágenes de habilidades a la carpeta de salida."""
        out = Path(output_path) if output_path else self.modded_output_path
        if not out:
            print("✗ No se proporcionó ruta de salida para skills")
            return

        hero_path = self.mod_path / 'heroes' / hero_class.lower()

        # Números en palabras y dígitos para mapear con los archivos
        number_words = ['one', 'two', 'three', 'four', 'five', 'six', 'seven']
        number_digits = ['1', '2', '3', '4', '5', '6', '7']

        for idx, skill_name in enumerate(skills):
            if idx < len(number_words):
                # Intentar primero con palabras (one, two, three...)
                skill_file = hero_path / f'{hero_class.lower()}.ability.{number_words[idx]}.png'

                # Si no existe, intentar con dígitos (1, 2, 3...)
                if not skill_file.exists():
                    skill_file = hero_path / f'{hero_class.lower()}.ability.{number_digits[idx]}.png'

                if skill_file.exists():
                    # Convertir nombre de skill a formato de archivo
                    skill_filename = self.sanitize_filename(skill_name.lower())
                    skill_filename = skill_filename.replace(' ', '_')
                    output_name = f'{self.mod_id}_{skill_filename}.png'
                    dest = out / 'skills' / output_name
                    dest.parent.mkdir(parents=True, exist_ok=True)

                    shutil.copy2(skill_file, dest)
                    print(f"✓ Copiada habilidad: {output_name}")
                else:
                    print(f"✗ No se encontró imagen de habilidad: {skill_file}")
    
    def copy_camp_skill_images(self, hero_class: str, camp_skills: List[str],
                                skill_id_to_name: Dict[str, str] = None, output_path: Path = None):
        """
        Copia las imágenes de camp skills a la carpeta de salida.
        Usa el mapeo skill_id -> nombre para renombrar los archivos con nombres legibles.

        Args:
            hero_class: Nombre de la clase del héroe
            camp_skills: Lista de nombres de camp skills
            skill_id_to_name: Mapeo de ID interno -> nombre legible
            output_path: Ruta de salida (sobreescribe self.modded_output_path)
        """
        out = Path(output_path) if output_path else self.modded_output_path
        if not out:
            print("✗ No se proporcionó ruta de salida para camp skills")
            return

        camp_skills_path = self.mod_path / 'raid' / 'camping' / 'skill_icons'

        if not camp_skills_path.exists():
            print(f"✗ No se encontró carpeta de camp skills: {camp_skills_path}")
            return

        if skill_id_to_name is None:
            skill_id_to_name = {}

        # Crear mapeo inverso: nombre_archivo -> nombre_legible
        # Los archivos suelen ser camp_skill_<skill_id>.png
        all_files = list(camp_skills_path.glob('*.png'))

        print("\n  Copiando imágenes de camp skills:")
        copied_count = 0

        for skill_file in all_files:
            # Obtener el skill_id del nombre del archivo
            filename = skill_file.stem

            # Eliminar prefijo camp_skill_ si existe para obtener el ID
            if filename.startswith('camp_skill_'):
                skill_id = filename.replace('camp_skill_', '', 1)
            else:
                skill_id = filename

            # Buscar el nombre legible en el mapeo
            skill_id_lower = skill_id.lower()
            if skill_id_lower in skill_id_to_name:
                # Usar el nombre legible para el archivo de salida
                display_name = skill_id_to_name[skill_id_lower]
                output_filename = self.sanitize_filename(display_name.lower()).replace(' ', '_')
                output_name = f'{self.mod_id}_{output_filename}.png'
            else:
                # Mantener el nombre original si no está en el mapeo
                output_filename = self.sanitize_filename(skill_id)
                output_name = f'{self.mod_id}_{output_filename}.png'

            dest = out / 'camp_skills' / output_name
            dest.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(skill_file, dest)
            print(f"    ✓ {skill_file.name} → {output_name}")
            copied_count += 1

        print(f"\n  Total de imágenes de camp skills copiadas: {copied_count}")
    
    def copy_trinket_images(self, output_path: Path = None):
        """Copia las imágenes de trinkets a la carpeta de salida (class_specific subfolder)."""
        out = Path(output_path) if output_path else self.modded_output_path
        if not out:
            print("✗ No se proporcionó ruta de salida para trinkets")
            return

        trinkets_path = self.mod_path / 'panels' / 'icons_equip' / 'trinket'

        if not trinkets_path.exists():
            print(f"✗ No se encontró carpeta de trinkets: {trinkets_path}")
            return

        for trinket_file in trinkets_path.glob('inv_trinket*.png'):
            # Obtener el nombre del archivo sin extensión
            filename = trinket_file.stem

            # Eliminar todos los posibles prefijos:
            # inv_trinket+cc_
            # inv_trinket+com_
            # inv_trinket+
            filename = re.sub(r'^inv_trinket\+(?:cc_|com_)?', '', filename)

            # Sanitizar el nombre del archivo
            filename = self.sanitize_filename(filename)

            output_name = f'{self.mod_id}_{filename}.png'
            dest = out / 'trinkets' / output_name
            dest.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(trinket_file, dest)
            print(f"✓ Copiado trinket: {output_name}")
    
    def update_modded_heroes_js(self, hero_display_name: str, skills: List[str],
                                camp_skills: List[str], vanilla_camp_skills: List[str],
                                trinkets: List[str], hero_class: str = None,
                                js_path: str = None):
        """
        Actualiza el archivo modded_heroes.js con el nuevo héroe.

        Args:
            hero_display_name: Nombre a mostrar del héroe
            skills: Lista de habilidades de combate
            camp_skills: Lista de camp skills custom
            vanilla_camp_skills: Lista de camp skills vanilla
            trinkets: Lista de trinkets
            hero_class: Nombre de la carpeta del héroe (para mods multi-héroe)
            js_path: Ruta al archivo modded_heroes.js (sobreescribe self.modded_heroes_path)
        """
        js_file = Path(js_path) if js_path else self.modded_heroes_path
        if not js_file:
            print("✗ No se proporcionó ruta para modded_heroes.js")
            return
        try:
            # Leer el archivo existente, intentando diferentes encodings
            content = None
            for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
                try:
                    with open(js_file, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                print(f"✗ No se pudo leer el archivo modded_heroes.js")
                return
            
            # Verificar si ya existe una entrada con el mismo nombre pero diferente modId
            existing_pattern = rf"'{re.escape(hero_display_name)}': \{{\s*modId: '(\d+)'"
            existing_match = re.search(existing_pattern, content)
            
            display_name_to_use = hero_display_name
            if existing_match:
                existing_mod_id = existing_match.group(1)
                if existing_mod_id != self.mod_id:
                    # Hay otro mod con el mismo nombre, usar nombre de carpeta como alternativa
                    # Usar el hero_class pasado como parámetro si está disponible
                    folder_name = hero_class or self.find_hero_class_name()
                    if folder_name and folder_name.lower() != hero_display_name.lower():
                        display_name_to_use = folder_name.replace('_', ' ').title()
                        print(f"  ⚠ Ya existe '{hero_display_name}' con modId {existing_mod_id}")
                        print(f"    Usando nombre alternativo: '{display_name_to_use}'")
            
            # Crear la nueva entrada del héroe
            new_hero_entry = f"""  '{display_name_to_use}': {{
    modId: '{self.mod_id}',
    skills: [
{self._format_array_items(skills)}
    ],
    campSkills: [
{self._format_array_items(camp_skills)}
    ],
    vanillaCampSkills: [
{self._format_array_items(vanilla_camp_skills)}
    ],
    image: '{self.mod_id}.png',
    classSpecificTrinkets: [
{self._format_array_items(trinkets)}
    ]
  }},"""
            
            # Verificar si este héroe específico (por modId) ya existe y eliminarlo
            existing_entry_pattern = rf"  '[^']+': \{{\s*modId: '{self.mod_id}'[^}}]+\}}\}},"
            if re.search(existing_entry_pattern, content, re.DOTALL):
                content = re.sub(existing_entry_pattern + r'\n?', '', content, flags=re.DOTALL)
                print(f"  (Reemplazando entrada existente del mod {self.mod_id})")
            
            # Buscar el final del objeto MODDED_HERO_CLASSES
            # Insertar antes del cierre del objeto
            insert_pattern = r'(\};[\s\n]*// Trinkets generales)'
            
            if re.search(insert_pattern, content):
                content = re.sub(
                    insert_pattern,
                    new_hero_entry + '\n\\1',
                    content
                )
            else:
                # Si no se encuentra el patrón, insertar antes del último }
                content = content.rstrip()
                if content.endswith('};'):
                    content = content[:-2] + ',\n' + new_hero_entry + '\n};'
            
            # Escribir el archivo actualizado
            with open(js_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"\n✓ Actualizado modded_heroes.js con '{display_name_to_use}'")
            
        except Exception as e:
            print(f"✗ Error actualizando modded_heroes.js: {e}")
    
    def _format_array_items(self, items: List[str], indent: int = 6) -> str:
        """Formatea items de un array para JavaScript."""
        if not items:
            return ''
        
        indent_str = ' ' * indent
        formatted = []
        for item in items:
            # Escapar comillas simples para JavaScript
            escaped_item = item.replace("'", "\\'")
            formatted.append(f"{indent_str}'{escaped_item}'")
        
        return ',\n'.join(formatted)
    
    def run(self, images_output_path: str = None, js_output_path: str = None):
        """
        Ejecuta el proceso completo de scraping para todos los héroes del mod.

        Args:
            images_output_path: Ruta base para imágenes (sobreescribe constructor)
            js_output_path: Ruta al modded_heroes.js (sobreescribe constructor)
        """
        print(f"\n{'='*60}")
        print(f"Iniciando scraping del mod: {self.mod_id}")
        print(f"{'='*60}\n")

        # 1. Encontrar todas las clases de héroes válidas del mod
        hero_classes = self.find_all_hero_classes()
        if not hero_classes:
            print("✗ No se pudo encontrar ninguna clase de héroe válida")
            return

        if len(hero_classes) > 1:
            print(f"⚠ Mod multi-héroe detectado: {len(hero_classes)} héroes encontrados")
            print(f"  Héroes: {', '.join(hero_classes)}")

        # Procesar cada héroe
        for i, hero_class in enumerate(hero_classes):
            if len(hero_classes) > 1:
                print(f"\n{'─'*40}")
                print(f"Procesando héroe {i+1}/{len(hero_classes)}: {hero_class}")
                print(f"{'─'*40}")
            else:
                print(f"Clase del héroe (carpeta): {hero_class}")

            self._process_single_hero(hero_class, images_output_path, js_output_path)

        print(f"\n{'='*60}")
        print("✓ Scraping completado exitosamente!")
        print(f"{'='*60}\n")

    def _process_single_hero(self, hero_class: str, images_output_path: str = None,
                             js_output_path: str = None):
        """
        Procesa un único héroe del mod.

        Args:
            hero_class: Nombre de la carpeta del héroe
            images_output_path: Ruta base para imágenes
            js_output_path: Ruta al modded_heroes.js
        """
        # 2. Encontrar el ID interno del héroe (puede ser diferente a la carpeta)
        internal_id = self.find_hero_internal_id(hero_class)
        if internal_id != hero_class:
            print(f"ID interno del héroe: {internal_id}")
        
        # 3. Obtener nombre legible de la clase
        hero_display_name = self.get_hero_class_display_name(hero_class, internal_id)
        print(f"Nombre de visualización: {hero_display_name}")
        
        # 4. Extraer información
        print("\nExtrayendo información del mod...")
        skills = self.get_combat_skills(hero_class, internal_id)
        custom_camp_skills, vanilla_camp_skills, camp_skill_id_map = self.get_camp_skills(hero_class)
        trinkets = self.get_trinkets_for_hero(hero_class, internal_id)
        
        # Combinar todas las camp skills (vanilla + custom) para campSkills
        all_camp_skills = vanilla_camp_skills + custom_camp_skills
        
        print(f"  - Habilidades de combate: {len(skills)}")
        print(f"  - Camp skills: {len(all_camp_skills)} ({len(vanilla_camp_skills)} vanilla + {len(custom_camp_skills)} custom)")
        print(f"  - Trinkets: {len(trinkets)}")
        
        # 5. Copiar archivos
        print("\nCopiando archivos...")
        self.copy_hero_portrait(hero_class, output_path=images_output_path)
        self.copy_skill_images(hero_class, skills, output_path=images_output_path)
        self.copy_camp_skill_images(hero_class, all_camp_skills, camp_skill_id_map, output_path=images_output_path)
        self.copy_trinket_images_for_hero(hero_class, internal_id, output_path=images_output_path)

        # 6. Actualizar modded_heroes.js
        print("\nActualizando modded_heroes.js...")
        self.update_modded_heroes_js(
            hero_display_name, skills, all_camp_skills,
            vanilla_camp_skills, trinkets, hero_class,
            js_path=js_output_path
        )
