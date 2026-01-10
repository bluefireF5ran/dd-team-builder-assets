# DD Team Builder - Assets

Este repositorio contiene los assets gráficos para [DD Team Builder](https://github.com/bluefireF5ran/dd-team-builder).

## Estructura de carpetas

```
images/
├── heroes/                    # Portraits de héroes vanilla (17)
│   ├── abomination.png
│   ├── antiquarian.png
│   ├── arbalest.png
│   └── ...
│
├── skills/                    # Iconos de skills de combate vanilla
│   ├── absolution.png
│   ├── beast_bile.png
│   └── ...
│
├── camp_skills/               # Iconos de camp skills vanilla
│   ├── bandage.png
│   ├── encourage.png
│   └── ...
│
├── trinkets/                  # Iconos de trinkets vanilla
│   ├── ancestors_bottle.png
│   └── ...
│
├── backer_trinkets/           # Trinkets de backers de Kickstarter
│   └── ...
│
├── quirks/                    # Iconos de quirks (opcional)
│   └── ...
│
├── portraits/                 # Portraits alternativos (opcional)
│   └── ...
│
├── bg/                        # Fondos por localización
│   ├── ruins.png
│   ├── warrens.png
│   ├── weald.png
│   ├── cove.png
│   ├── courtyard.png
│   ├── farmstead.png
│   └── darkest_dungeon.png
│
└── modded/                    # Assets de mods
    ├── heroes/                # Portraits de héroes modded
    │   ├── lamia.png
    │   └── ...
    │
    ├── skills/                # Skills modded (prefijo: modId_skillname.png)
    │   ├── lamia_venomous_kiss.png
    │   └── ...
    │
    ├── camp_skills/           # Camp skills modded (prefijo: modId_skillname.png)
    │   └── ...
    │
    └── trinkets/              # Trinkets modded
        ├── class_specific/    # Trinkets de clase (prefijo: modId_trinketname.png)
        └── general/           # Trinkets generales modded
```

## Convención de nombres

- Todo en **minúsculas**
- Espacios reemplazados por **guiones bajos** `_`
- Apóstrofes eliminados
- Caracteres especiales eliminados
- Formato: **PNG**

### Ejemplos:
| Nombre en juego | Nombre de archivo |
|-----------------|-------------------|
| Crusader | `crusader.png` |
| Man-at-Arms | `manatarms.png` |
| Rallying Flare | `rallying_flare.png` |
| Ancestor's Bottle | `ancestors_bottle.png` |

## Cómo contribuir

1. Fork este repositorio
2. Añade las imágenes siguiendo la estructura
3. Asegúrate de que los nombres siguen la convención
4. Crea un Pull Request

## Notas sobre derechos de autor

Las imágenes de Darkest Dungeon pertenecen a **Red Hook Studios**. 
Este repositorio es solo para uso educativo y de fans.
