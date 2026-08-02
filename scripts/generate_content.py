#!/usr/bin/env python3
"""Build the checked-in Eidpfad content catalogs from curated design tables.

The generated JSON and SVG files are runtime assets, not test fixtures. Keeping
the production rules here makes balancing changes reproducible and prevents the
catalog, the client art paths and the server implementation from drifting apart.
"""

from __future__ import annotations

import colorsys
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
CLIENT_ASSETS = ROOT / "client" / "assets"
RARITIES = ("normal", "rare", "enhanced", "exceptional", "legendary", "unique")
RARITY_LABELS = {
    "normal": "gewöhnliche",
    "rare": "seltene",
    "enhanced": "verbesserte",
    "exceptional": "außergewöhnliche",
    "legendary": "legendäre",
    "unique": "einzigartige",
}
SCHOOL_LABELS = {
    "dual_blades": "Zwillingsklingen",
    "axe": "Axt",
    "bow": "Langbogen",
    "crossbow": "Armbrust",
    "longsword": "Langschwert",
}
STATUS_LABELS = {
    "aimed": "Fokus",
    "arcane_link": "Arkanes Band",
    "bleeding": "Blutung",
    "bound": "Gebunden",
    "burning": "Brennen",
    "coordinated": "Abgestimmt",
    "exposed": "Entblößt",
    "final_oath": "Letzter Eid",
    "fury": "Kampfrausch",
    "last_oath": "Letzter Schwur",
    "marked": "Markiert",
    "oath_power": "Eidkraft",
    "weakened": "Geschwächt",
}
BONUS_LABELS = {
    "attack_dice": "Angriffswürfel",
    "block_break": "Blockbruch",
    "block_dice": "Blockwürfel",
    "critical_min": "kritische Treffer",
    "damage_per_hit": "Trefferschaden",
    "hit_threshold_modifier": "Trefferchance",
}


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stable_colors(identifier: str) -> tuple[str, str, str]:
    digest = hashlib.sha256(identifier.encode()).digest()
    hue = digest[0] / 255
    secondary_hue = (hue + 0.10 + digest[1] / 850) % 1
    first = colorsys.hsv_to_rgb(hue, 0.52, 0.48)
    second = colorsys.hsv_to_rgb(secondary_hue, 0.62, 0.77)
    accent = colorsys.hsv_to_rgb((hue + 0.48) % 1, 0.40, 0.94)
    convert = lambda rgb: "#%02x%02x%02x" % tuple(round(channel * 255) for channel in rgb)
    return convert(first), convert(second), convert(accent)


def icon_svg(identifier: str, category: str, ratio: str = "square") -> str:
    width, height = (512, 704) if ratio == "card" else (512, 512)
    primary, secondary, accent = stable_colors(identifier)
    digest = hashlib.sha256((category + identifier).encode()).digest()
    sides = 3 + digest[0] % 6
    rotation = digest[1] % 40 - 20
    ring = 108 + digest[2] % 52
    spikes = " ".join(
        f'{256 + int((ring + (index % 2) * 28) * __import__("math").cos(index * 6.283 / (sides * 2)))}'
        f',{height // 2 + int((ring + (index % 2) * 28) * __import__("math").sin(index * 6.283 / (sides * 2)))}'
        for index in range(sides * 2)
    )
    frame_y = 76 if ratio == "card" else 54
    frame_h = height - frame_y * 2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <radialGradient id="bg"><stop stop-color="{secondary}"/><stop offset="1" stop-color="{primary}"/></radialGradient>
    <linearGradient id="metal" x2="0" y2="1"><stop stop-color="{accent}"/><stop offset=".48" stop-color="{secondary}"/><stop offset="1" stop-color="{primary}"/></linearGradient>
    <filter id="shadow"><feGaussianBlur stdDeviation="10"/></filter>
  </defs>
  <rect width="{width}" height="{height}" rx="34" fill="#101619"/>
  <rect x="22" y="22" width="468" height="{height - 44}" rx="26" fill="url(#bg)" stroke="{accent}" stroke-opacity=".55" stroke-width="4"/>
  <circle cx="256" cy="{height // 2 + 16}" r="{ring + 46}" fill="#050708" opacity=".40" filter="url(#shadow)"/>
  <g transform="rotate({rotation} 256 {height // 2})">
    <polygon points="{spikes}" fill="url(#metal)" stroke="{accent}" stroke-width="7" stroke-linejoin="round"/>
    <circle cx="256" cy="{height // 2}" r="74" fill="#11181b" stroke="{accent}" stroke-width="6"/>
    <path d="M214 {height // 2 + 42} L256 {height // 2 - 62} L298 {height // 2 + 42} L256 {height // 2 + 18} Z" fill="{accent}" opacity=".88"/>
  </g>
  <rect x="54" y="{frame_y}" width="404" height="{frame_h}" rx="18" fill="none" stroke="{accent}" stroke-opacity=".24" stroke-width="3"/>
  <circle cx="76" cy="68" r="10" fill="{accent}"/><circle cx="436" cy="68" r="10" fill="{accent}"/>
</svg>'''


def effect_text(effect: dict[str, Any]) -> str:
    kind = effect["type"]
    amount = int(effect.get("amount", 0))
    if kind == "dice_attack":
        extra = f", bricht {effect['armor_per_success']} Rüstung" if effect.get("armor_per_success") else ""
        return f"{effect['count']} W12 auf {effect['threshold']}+; {effect['damage_per_success']} Schaden je Erfolg{extra}"
    if kind == "dice_magic_damage":
        status_name = STATUS_LABELS.get(str(effect.get("status", "")), str(effect.get("status", "")))
        status = f" und {status_name} {amount}" if effect.get("status") else ""
        return f"{effect['count']} Magie-W12 auf {effect['threshold']}+; {effect['damage_per_success']} Schaden je ungebanntem Erfolg{status}"
    labels = {
        "add_block_dice_self": f"+{amount} Block-W12 für dich",
        "add_block_dice_ally": f"+{amount} Block-W12 für deinen Partner",
        "add_block_dice_all": f"+{amount} Block-W12 für beide",
        "heal_self": f"heile dich um {amount}",
        "heal_ally": f"heile deinen Partner um {amount}",
        "heal_all": f"heile beide um {amount}",
        "self_damage": f"verliere {amount} Leben",
        "regeneration": f"Regeneration {amount} für {effect.get('rounds', 2)} Runden",
        "apply_weapon_coating": f"Ätzöl mit {amount} Ladungen",
        "set_trap": f"Falle mit {amount} W12",
        "draw_cards": f"ziehe {amount} Karten",
        "gain_action_points": f"erhalte {amount} AP",
        "guard_self": f"erhalte {amount} Schutz",
        "cleanse": "entferne einen negativen Zustand",
        "armor_break": f"zerbrich {amount} Rüstung",
        "enemy_status": f"verursache {STATUS_LABELS.get(str(effect.get('status', '')), 'Status')} {amount}",
        "self_status": f"erhalte {STATUS_LABELS.get(str(effect.get('status', '')), 'Status')} {amount}",
        "team_status": f"beide erhalten {STATUS_LABELS.get(str(effect.get('status', '')), 'Status')} {amount}",
        "exhaust": "erschöpfen",
    }
    return labels.get(kind, kind)


WEAPON_NAMES = {
    "dual_blades": [
        "Kreuzschnitt", "Sehnenhieb", "Roter Reigen", "Gekreuzte Klingen", "Klingenfokus", "Aderlass",
        "Schulter an Schulter", "Tausend Schnitte", "Ätzende Schneiden", "Schattenstich", "Wirbelparade",
        "Klingenfalle", "Tanz der Narben", "Letzter Herzschlag", "Blitzreflex", "Blutsbrüder",
    ],
    "axe": [
        "Eisenbrecher", "Schädelspalter", "Standhalten", "Urteil des Henkers", "Schwerer Atem", "Kniespalter",
        "Eiserner Wall", "Berserkersturm", "Schleifstein", "Riss im Panzer", "Gegenschlag", "Fallbeilfalle",
        "Sturm des Henkers", "Weltenriss", "Schildhaken", "Unbeugsamer Eid",
    ],
    "bow": [
        "Jagdschuss", "Durchbohrender Pfeil", "Deckungsfeuer", "Ruhige Hand", "Falkenblick", "Blutpfeil",
        "Gemeinsame Deckung", "Pfeilregen", "Harzspitze", "Schattenpfeil", "Abfangschuss", "Drahtfalle",
        "Sonnenhagel", "Schweigender Horizont", "Rückwärtsschritt", "Jägerbund",
    ],
    "crossbow": [
        "Bolzenhagel", "Schattenbolzen", "Stahlkolben-Parade", "Schnellladen", "Zielmechanik", "Widerhaken",
        "Mobile Barrikade", "Salve", "Säurebolzen", "Panzerbrecher", "Notkolben", "Sprengfalle",
        "Sturmspanner", "Schwarzer Donner", "Deckungssprung", "Synchronfeuer",
    ],
    "longsword": [
        "Gerader Hieb", "Halbschwert", "Klingenwacht", "Hohe Hut", "Mordschlag", "Blutrinne",
        "Schützender Stahl", "Zornhau", "Geölte Klinge", "Durchwechseln", "Kronparade", "Klingenwall",
        "Meisterhau", "Eidstahl", "Nachreisen", "Bund der Schwerter",
    ],
}

MAGIC_NAMES = {
    "rune": ["Runenkäfig", "Steinschrift", "Zwillingsbann", "Runenheilung", "Siegelbruch", "Eidopfer", "Frostglyphe", "Runenschild", "Lebenszeichen", "Sternenrune", "Wort des Ursprungs", "Gemeinsames Siegel"],
    "ember": ["Aschemal", "Glutlanze", "Flammenbund", "Wärmender Funke", "Feuersturm", "Aschenopfer", "Brandzeichen", "Glutpanzer", "Phönixatem", "Sonnenbrand", "Herz der Flamme", "Geteilte Glut"],
    "veil": ["Schattenfessel", "Nachtklinge", "Schleierbund", "Dämmerruhe", "Leerenriss", "Seelenzoll", "Blindmal", "Spiegelhaut", "Nebelheilung", "Mondlose Nacht", "Tor hinter dem Spiegel", "Zwillingsecho"],
    "blood": ["Blutschuld", "Herzstich", "Roter Bund", "Lebensraub", "Bluternte", "Aderopfer", "Gerinnungsmal", "Knochenpanzer", "Schwarzwurzel", "Purpurflut", "Erster Eid", "Geteiltes Herz"],
}

UNIVERSAL_NAMES = [
    "Feldverband", "Letzter Schwur", "Gegengift", "Wachposten", "Stählerner Wille", "Ablenkungsmanöver",
    "Kartenstudium", "Atem holen", "Gemeinsamer Plan", "Notration", "Rauchbombe", "Improvisierte Deckung",
    "Eidkraft", "Kampfrausch", "Söldnerehre", "Der letzte Eid",
]


def rarity_for(index: int) -> str:
    return ("normal", "normal", "rare", "rare", "enhanced", "exceptional", "legendary", "unique")[index % 8]


def weapon_card(school: str, index: int, name: str) -> dict[str, Any]:
    if school == "longsword":
        designs: list[tuple[str, str, int, list[dict[str, Any]]]] = [
            ("attack", "weapon", 1, [{"type": "dice_attack", "count": 3, "threshold": 7, "damage_per_success": 3}]),
            ("attack", "weapon", 2, [{"type": "dice_attack", "count": 2, "threshold": 6, "damage_per_success": 2, "armor_per_success": 1}]),
            ("defense", "defense", 1, [{"type": "add_block_dice_self", "amount": 2}, {"type": "guard_self", "amount": 1}]),
            ("defense", "defense", 1, [{"type": "add_block_dice_self", "amount": 3}]),
            ("utility", "utility", 1, [{"type": "self_status", "status": "aimed", "amount": 1}, {"type": "draw_cards", "amount": 1}]),
            ("attack", "weapon", 2, [{"type": "dice_attack", "count": 3, "threshold": 7, "damage_per_success": 2}, {"type": "enemy_status", "status": "bleeding", "amount": 2}]),
            ("defense", "defense", 1, [{"type": "add_block_dice_self", "amount": 2}, {"type": "guard_self", "amount": 2}]),
            ("attack", "weapon", 3, [{"type": "dice_attack", "count": 5, "threshold": 9, "damage_per_success": 4}, {"type": "exhaust"}]),
            ("utility", "utility", 2, [{"type": "apply_weapon_coating", "amount": 3}, {"type": "exhaust"}]),
            ("attack", "weapon", 2, [{"type": "dice_attack", "count": 3, "threshold": 6, "damage_per_success": 2}, {"type": "gain_action_points", "amount": 1}]),
            ("defense", "reaction", 1, [{"type": "add_block_dice_self", "amount": 4}, {"type": "exhaust"}]),
            ("utility", "utility", 2, [{"type": "set_trap", "amount": 3}, {"type": "guard_self", "amount": 2}]),
            ("attack", "weapon", 2, [{"type": "dice_attack", "count": 4, "threshold": 7, "damage_per_success": 3, "armor_per_success": 1}]),
            ("attack", "weapon", 3, [{"type": "dice_attack", "count": 4, "threshold": 7, "damage_per_success": 4}, {"type": "self_damage", "amount": 2}]),
            ("defense", "reaction", 1, [{"type": "add_block_dice_self", "amount": 2}, {"type": "draw_cards", "amount": 1}]),
            ("utility", "cooperation", 2, [{"type": "team_status", "status": "coordinated", "amount": 2}, {"type": "draw_cards", "amount": 2}]),
        ]
        phase, kind, cost, effects = designs[index]
        identifier = slug(name)
        return {
            "id": identifier, "name": name, "kind": kind, "school": school,
            "phase": phase, "action_point_cost": cost, "rarity": rarity_for(index),
            "starter": index in {0, 3, 4}, "unlock_level": 1 + index // 2,
            "text": "; ".join(effect_text(effect) for effect in effects).capitalize() + ".",
            "effects": effects, "art": f"res://assets/cards/{identifier}.svg",
            "keywords": sorted({effect.get("status", effect["type"]) for effect in effects}),
        }
    status = {"dual_blades": "bleeding", "axe": "exposed", "bow": "marked", "crossbow": "weakened", "longsword": "exposed"}[school]
    pattern = index % 16
    phase, kind, cost = "attack", "weapon", 1 + (index % 3 == 1)
    effects: list[dict[str, Any]]
    if pattern in {0, 1, 2, 5, 7, 9, 12, 13}:
        count = 2 + (pattern in {0, 5, 9}) + (pattern in {7, 12, 13}) * 2
        damage = 2 + (school in {"axe", "crossbow"}) + (pattern in {1, 12, 13})
        threshold = 7 + (pattern in {1, 7, 12, 13})
        effects = [{"type": "dice_attack", "count": count, "threshold": threshold, "damage_per_success": damage}]
        if pattern in {2, 9, 12}:
            effects[0]["armor_per_success"] = 1 + (school == "axe")
        if school == "axe" and pattern == 9:
            # Keep the standalone armor_break route represented in shipped content.
            effects[0].pop("armor_per_success", None)
            effects.append({"type": "armor_break", "amount": 2})
        if pattern in {5, 9}:
            effects.append({"type": "enemy_status", "status": status, "amount": 1 + (pattern == 5)})
        if pattern == 13:
            effects.append({"type": "exhaust"})
            cost = 3
    elif pattern in {3, 6, 10, 14}:
        phase, kind, cost = "defense", "defense" if pattern != 14 else "reaction", 1
        effects = [{"type": "add_block_dice_self", "amount": 2 + (pattern == 10)}]
        if pattern in {6, 10}:
            effects.append({"type": "add_block_dice_ally", "amount": 1})
    else:
        phase, kind, cost = "utility", "utility" if pattern != 15 else "cooperation", 1 + (pattern in {8, 11})
        effects = {
            4: [{"type": "self_status", "status": "aimed", "amount": 1}],
            8: [{"type": "apply_weapon_coating", "amount": 2}, {"type": "exhaust"}],
            11: [{"type": "set_trap", "amount": 2}, {"type": "exhaust"}],
            15: [{"type": "team_status", "status": "coordinated", "amount": 1}, {"type": "draw_cards", "amount": 1}],
        }[pattern]
    identifier = slug(name)
    return {
        "id": identifier, "name": name, "kind": kind, "school": school, "phase": phase,
        "action_point_cost": int(cost), "rarity": rarity_for(index),
        "starter": index in {0, 3, 4}, "unlock_level": 1 + index // 2,
        "text": "; ".join(effect_text(effect) for effect in effects).capitalize() + ".",
        "effects": effects, "art": f"res://assets/cards/{identifier}.svg",
        "keywords": sorted({effect.get("status", effect["type"]) for effect in effects}),
    }


def magic_card(school: str, index: int, name: str) -> dict[str, Any]:
    status = {"rune": "bound", "ember": "burning", "veil": "weakened", "blood": "bleeding"}[school]
    pattern = index % 12
    phase, kind, cost = "magic", "magic", 2
    if pattern in {0, 1, 4, 5, 6, 9, 10}:
        effects: list[dict[str, Any]] = []
        if pattern in {5}:
            effects.append({"type": "self_damage", "amount": 3})
            cost = 1
        effects.append({
            "type": "dice_magic_damage", "count": 2 + (pattern in {1, 4, 6}) + (pattern in {9, 10}) * 2,
            "threshold": 7 + (pattern in {4, 9, 10}), "damage_per_success": 2 + (pattern in {1, 9, 10}),
            "status": status, "amount": 1 + (pattern in {0, 6}),
        })
        if pattern == 10:
            effects.append({"type": "exhaust"})
            cost = 3
    elif pattern in {2, 7}:
        phase, kind, cost = "defense", "magic", 1 + (pattern == 2)
        effects = [{"type": "add_block_dice_all" if pattern == 2 else "add_block_dice_self", "amount": 2}]
    else:
        phase, kind, cost = "utility", "cooperation" if pattern == 11 else "magic", 2
        effects = {
            3: [{"type": "heal_all", "amount": 4}] if school == "rune" else [{"type": "heal_ally", "amount": 6}],
            8: [{"type": "regeneration", "amount": 2, "rounds": 3}],
            11: [{"type": "team_status", "status": "arcane_link", "amount": 1}, {"type": "draw_cards", "amount": 1}],
        }[pattern]
    identifier = slug(name)
    return {
        "id": identifier, "name": name, "kind": kind, "school": school, "phase": phase,
        "action_point_cost": int(cost), "rarity": rarity_for(index + 1),
        "starter": index in {0, 2, 3}, "unlock_level": 1 + index // 2,
        "text": "; ".join(effect_text(effect) for effect in effects).capitalize() + ".",
        "effects": effects, "art": f"res://assets/cards/{identifier}.svg",
        "keywords": sorted({effect.get("status", effect["type"]) for effect in effects}),
    }


def universal_card(index: int, name: str) -> dict[str, Any]:
    designs = [
        ("utility", "utility", 2, [{"type": "heal_ally", "amount": 6}]),
        ("defense", "defense", 2, [{"type": "self_status", "status": "last_oath", "amount": 1}, {"type": "exhaust"}]),
        ("utility", "utility", 1, [{"type": "cleanse", "amount": 1}]),
        ("defense", "reaction", 1, [{"type": "add_block_dice_all", "amount": 1}]),
        ("defense", "defense", 1, [{"type": "guard_self", "amount": 4}]),
        ("attack", "cooperation", 1, [{"type": "enemy_status", "status": "exposed", "amount": 1}]),
        ("utility", "utility", 1, [{"type": "draw_cards", "amount": 2}]),
        ("utility", "utility", 1, [{"type": "gain_action_points", "amount": 1}, {"type": "exhaust"}]),
        ("utility", "cooperation", 2, [{"type": "team_status", "status": "coordinated", "amount": 1}]),
        ("utility", "utility", 1, [{"type": "heal_self", "amount": 4}, {"type": "exhaust"}]),
        ("defense", "reaction", 1, [{"type": "add_block_dice_self", "amount": 3}, {"type": "exhaust"}]),
        ("defense", "defense", 1, [{"type": "add_block_dice_ally", "amount": 2}]),
        ("magic", "cooperation", 2, [{"type": "team_status", "status": "oath_power", "amount": 2}]),
        ("attack", "utility", 1, [{"type": "self_status", "status": "fury", "amount": 1}]),
        ("defense", "cooperation", 1, [{"type": "guard_self", "amount": 3}, {"type": "add_block_dice_ally", "amount": 1}]),
        ("attack", "cooperation", 5, [{"type": "team_status", "status": "final_oath", "amount": 1}, {"type": "dice_attack", "count": 8, "threshold": 7, "damage_per_success": 4}, {"type": "exhaust"}]),
    ]
    phase, kind, cost, effects = designs[index]
    identifier = slug(name)
    return {
        "id": identifier, "name": name, "kind": kind, "school": "universal", "phase": phase,
        "action_point_cost": cost, "rarity": "unique" if name == "Der letzte Eid" else rarity_for(index + 2), "starter": index in {0, 2, 3, 5},
        "unlock_level": 8 if name == "Der letzte Eid" else 1 + index // 2, "text": "; ".join(effect_text(e) for e in effects).capitalize() + ".",
        "effects": effects, "art": f"res://assets/cards/{identifier}.svg",
        "keywords": sorted({effect.get("status", effect["type"]) for effect in effects}),
    }


ITEM_NAMES = {
    "dual_blades": ["Abgenutzte Zwillingsklingen", "Krähenmesser", "Kupferzähne", "Moorhaken", "Dornschwestern", "Salzklingen", "Spiegelpaar", "Glutdolche", "Frostfang-Duo", "Sturmtänzer", "Wurzelreißer", "Nachtfinken", "Flutklingen", "Knochensicheln", "Sonnenzwillinge", "Aschenreigen", "Duellantenhaken", "Runenpaar", "Sternenschnitter", "Blutmondklingen", "Eidbrecher-Duo", "Schweigende Schwestern", "Weltennahtmesser", "Erste und Letzte Klinge"],
    "axe": ["Söldneraxt", "Krähenbeil", "Kupferhacke", "Moorspalter", "Dornbeißer", "Salzbeil", "Spiegelaxt", "Glutschneide", "Axt des Winterfürsten", "Donnerkeil", "Wurzelspalter", "Nachtbeil", "Fluthammer", "Knochenbrecher", "Sonnenaxt", "Aschenhenker", "Richtbeil", "Runenspalter", "Sternenfall", "Blutmondbeil", "Eidspalter", "Schweigende Axt", "Wegspalter", "Axt des ersten Namens"],
    "bow": ["Eschenbogen", "Krähenbogen", "Kupfersehne", "Moorweide", "Dornenbogen", "Salzläufer", "Spiegelbogen", "Glutsehne", "Frostweide", "Sturmbogen", "Wurzelbogen", "Nachtfeder", "Flutbogen", "Knochensehne", "Sonnenstecher", "Aschenbogen", "Jägerkönig", "Runenweide", "Sternenbogen", "Blutmondsehne", "Eidbogen", "Schweigende Sonne", "Horizontbrecher", "Bogen des ersten Lichts"],
    "crossbow": ["Feldarmbrust", "Krähenwerfer", "Kupferspanner", "Moorbolzer", "Dornspanner", "Salzwerfer", "Spiegelarmbrust", "Glutbolzer", "Frostspanner", "Sturmspanner", "Wurzelwerfer", "Nachtbolzen", "Flutspanner", "Knochenwerfer", "Sonnenarmbrust", "Aschenbolzer", "Belagerer", "Runenspanner", "Sternenwerfer", "Blutmondbolzer", "Eidarmbrust", "Schwarzer Donner", "Nahtspanner", "Armbrust des letzten Wortes"],
    "longsword": ["Abgenutztes Langschwert", "Krähenschwert", "Kupferklinge", "Moorschwert", "Dornenschneide", "Salzstahl", "Spiegelschwert", "Glutklinge", "Froststahl", "Sturmklinge", "Wurzelschwert", "Nachtschneide", "Flutstahl", "Knochenschwert", "Sonnenklinge", "Aschenschwert", "Fechtmeister", "Runenstahl", "Sternenschwert", "Blutmondklinge", "Eidschwert", "Schweigende Klinge", "Nahtschwert", "Langschwert des ersten Eids"],
}

COUNTRY_IDS = ("nebelmark", "sonnenbruch", "frostreiche", "splitterinseln", "aschenlande", "dornwall", "glassteppe", "tiefenwald", "kupferkueste", "knochental", "nachtkrone", "sturmmarsch", "versunkener_bund", "weltennaht")


def make_weapon_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for school, names in ITEM_NAMES.items():
        for index, name in enumerate(names):
            rarity = RARITIES[min(5, index // 4)]
            identifier = {
                ("dual_blades", 0): "worn_dual_blades", ("axe", 0): "worn_axe",
                ("bow", 0): "worn_bow", ("crossbow", 0): "worn_crossbow",
                ("longsword", 0): "worn_longsword",
                ("dual_blades", 16): "duelist_hooks", ("axe", 8): "winter_lord_axe",
                ("axe", 22): "worldsplitter", ("bow", 14): "sun_piercer",
                ("crossbow", 9): "storm_crossbow",
            }.get((school, index), slug(name))
            rank = RARITIES.index(rarity)
            bonuses: dict[str, int] = {"attack_dice": min(2, rank // 2), "damage_per_hit": (rank + index) % 3}
            if index % 4 == 1 and rank >= 1:
                bonuses["hit_threshold_modifier"] = -1
            if index % 4 == 2 and rank >= 2:
                bonuses["block_dice"] = 1
            if index % 4 == 3 and rank >= 3:
                bonuses["block_break"] = 1
            if rank >= 4:
                bonuses["critical_min"] = 11
            items.append({
                "id": identifier, "name": name, "slot": "weapon", "rarity": rarity,
                "weapon_school": school, "country_affinity": COUNTRY_IDS[index % len(COUNTRY_IDS)],
                "drop_weight": max(1, 10 - rank * 2), "bonuses": bonuses,
                "description": (
                    f"{name} ist eine {RARITY_LABELS[rarity]} {SCHOOL_LABELS[school]}-Waffe aus "
                    f"{COUNTRY_IDS[index % len(COUNTRY_IDS)].replace('_', ' ').title()}. "
                    f"Sie prägt den Kampfstil mit {', '.join(BONUS_LABELS[key] for key in sorted(bonuses))} und schaltet "
                    f"„{WEAPON_NAMES[school][index % 16]}“ frei."
                ),
                "granted_card": slug(WEAPON_NAMES[school][index % 16]),
                "art": f"res://assets/items/{identifier}.svg",
            })
    return items


def make_support_items() -> list[dict[str, Any]]:
    groups = {
        "armor": ["Reiseleder", "Moorwacht-Kettenhemd", "Dornplatten", "Salzschuppen", "Frostpanzer", "Glutmantel", "Spiegelharnisch", "Sturmbrigantine", "Wurzelrüstung", "Knochenpanzer", "Nachtwacht", "Flutmail", "Runenpanzer des Kolosses", "Mantel des letzten Atems", "Eidwall", "Rüstung ohne Namen"],
        "talisman": ["Blutglas-Amulett", "Krähenauge", "Sonnenmark", "Frostherz", "Sturmknoten", "Wurzelring"],
        "alchemy": ["Meisteralchemieset", "Glutdestille", "Moorretorte", "Reisender Mörser"],
        "relic": ["Herz der Aschenbestie", "Splitter der Krone", "Erster Wegstein", "Echo des Kartografen"],
        "offhand": ["Runenschild", "Jägerlaterne"],
    }
    result: list[dict[str, Any]] = []
    total_index = 0
    for slot, names in groups.items():
        for index, name in enumerate(names):
            rank = min(5, (index * 6) // max(1, len(names)))
            rarity = RARITIES[rank]
            identifier = {
                "Reiseleder": "travel_leathers", "Moorwacht-Kettenhemd": "moorwatch_chain",
                "Runenpanzer des Kolosses": "colossus_runemail", "Mantel des letzten Atems": "last_breath_cloak",
                "Blutglas-Amulett": "bloodglass_amulet",
            }.get(name, slug(name))
            if slot == "armor":
                bonuses = {"block_dice": 2 + min(3, rank), "block_threshold": max(5, 8 - rank // 2)}
                if rank >= 3:
                    bonuses["ward_dice"] = 1
                if identifier == "last_breath_cloak":
                    bonuses["last_oath"] = 1
            elif slot == "talisman":
                bonuses = {"healing": 1 + rank // 2, "magic_dice": min(2, rank // 3 + 1)}
            elif slot == "alchemy":
                bonuses = {"healing": 2 + rank, "ward_dice": rank // 3}
            elif slot == "relic":
                bonuses = {"magic_dice": 1 + rank // 2, "critical_min": max(10, 12 - rank // 2)}
            else:
                bonuses = {"block_dice": 1 + rank // 2, "ward_dice": 1}
            result.append({
                "id": identifier, "name": name, "slot": slot, "rarity": rarity,
                "country_affinity": COUNTRY_IDS[total_index % len(COUNTRY_IDS)],
                "drop_weight": max(1, 10 - rank * 2), "bonuses": bonuses,
                "description": f"{name} stärkt die kooperative Ausrüstung des Grauen Eids.",
                "art": f"res://assets/items/{identifier}.svg",
            })
            total_index += 1
    return result


ENEMY_NAMES = {
    "nebelmark": ["Moorläufer", "Krähenhexer", "Sumpfhund", "Nebelbogner", "Schlickbrut", "Ertrunkener Wächter", "Irrlichtschwarm", "Torfschlächter", "Graufenn-Hexe", "Moorfürst"],
    "sonnenbruch": ["Salzbandit", "Dünenhund", "Scherbenpriester", "Sonnenräuber", "Glasviper", "Karawanenbrecher", "Staubschütze", "Goldgrab-Plünderer", "Scherbenchampion", "Heiliger des Mittags"],
    "frostreiche": ["Eiswandler", "Frostwolf", "Runenjäger", "Schneeblinder", "Gletscherbrut", "Weißgrab-Ritter", "Reifhexer", "Kaltblut-Bär", "Eisgrat-Hüter", "Mutter unter dem Eis"],
    "splitterinseln": ["Wrackplünderer", "Sturmharpyie", "Riffkriecher", "Gezeitenrufer", "Salzgeist", "Klippenbogner", "Flutbestie", "Ertrunkener Kapitän", "Sturmbringer", "Herr der Brecher"],
    "aschenlande": ["Aschenpilger", "Gluthund", "Rauchhexer", "Schlackenritter", "Brandkriecher", "Kohlebogner", "Feuerzehrer", "Schwarztor-Wächter", "Phönixbrut", "Aschenheiliger"],
    "dornwall": ["Dornenknecht", "Rosenhexe", "Wolfsschrat", "Rankenbogner", "Giftblüte", "Heckenritter", "Wurzelhund", "Blutrose", "Dornenchampion", "Königin der Hecken"],
    "glassteppe": ["Spiegelstreuner", "Glaskorpion", "Singender Geist", "Sonnenwächter", "Prismenhexer", "Dünenspiegel", "Scherbenkoloss", "Lichtdieb", "Kristallherold", "Königin hinter dem Spiegel"],
    "tiefenwald": ["Moosläufer", "Hirschgeist", "Wurzelhexer", "Borkenwächter", "Pilzbrut", "Jagdschatten", "Astbrecher", "Grünfluch", "Uralter Hirsch", "Wurzelgebundener Koloss"],
    "kupferkueste": ["Hafenschläger", "Riffschütze", "Kupferkrabbe", "Schmugglerhexer", "Leuchtturmgeist", "Erzräuber", "Salzkanonier", "Küstenwürger", "Hafenmeister", "Kupferleviathan"],
    "knochental": ["Knochenknecht", "Grabwolf", "Totenrufer", "Bleicher Bogner", "Rippenbrut", "Riesenwächter", "Seelenräuber", "Markschlächter", "Grabchampion", "König im Riesengrab"],
    "nachtkrone": ["Mondstreuner", "Sternenhexer", "Rabengarde", "Dämmerbogner", "Traumfresser", "Turmwächter", "Nachtviper", "Schattenritter", "Sternenherold", "Bleicher Regent"],
    "sturmmarsch": ["Donnerknecht", "Windwolf", "Blitzrufer", "Himmelsbogner", "Wolkenbrut", "Sturmschild", "Heidedrache", "Böenjäger", "Donnerchampion", "Herr des ewigen Sturms"],
    "versunkener_bund": ["Algenknecht", "Glockengeist", "Tiefenjäger", "Nebelharpunier", "Korallenbrut", "Flutpriester", "Schlickriese", "Ertrunkene Braut", "Tiefenherold", "Herr der versunkenen Stimmen"],
    "weltennaht": ["Nahtwächter", "Eidbrecher", "Namenloser Bogner", "Weltenhexer", "Spaltenbrut", "Throngarde", "Echojäger", "Kronenriese", "Herold ohne Gesicht", "Krone ohne Namen"],
}

ROLES = ("skirmisher", "brute", "defender", "hexer", "marksman", "assassin", "beast", "controller", "elite", "boss")

REGIONAL_TRAITS = {
    "nebelmark": "bog_shroud", "sonnenbruch": "sun_scorch", "frostreiche": "frost_bite",
    "splitterinseln": "tidal_pressure", "aschenlande": "ember_skin", "dornwall": "thorn_rebuke",
    "glassteppe": "prismatic_ward", "tiefenwald": "root_bind", "kupferkueste": "salt_armor",
    "knochental": "grave_resolve", "nachtkrone": "moon_veil", "sturmmarsch": "storm_charge",
    "versunkener_bund": "drowned_hex", "weltennaht": "rift_shift",
}


def body_family(name: str, role: str) -> str:
    lowered = name.lower()
    if any(word in lowered for word in ("skorpion", "krabbe", "kriecher")):
        return "arthropod"
    if any(word in lowered for word in ("viper", "würger")):
        return "serpent"
    if any(word in lowered for word in ("harpyie", "phönix", "drache")):
        return "harpy"
    if any(word in lowered for word in ("geist", "irrlicht", "schatten", "spiegel", "braut")):
        return "spirit"
    if any(word in lowered for word in ("schwarm", "blüte", "pollen")):
        return "swarm"
    if any(word in lowered for word in ("hund", "wolf", "bär", "hirsch", "bestie")):
        return "quadruped"
    if any(word in lowered for word in ("riese", "koloss", "leviathan")):
        return "giant"
    return "humanoid"


def make_enemies() -> list[dict[str, Any]]:
    enemies: list[dict[str, Any]] = []
    for country_index, (country, names) in enumerate(ENEMY_NAMES.items()):
        for index, name in enumerate(names):
            role = ROLES[index]
            tier = 1 + index // 3
            boss = role == "boss"
            elite = role == "elite"
            identifier = f"{country}_{slug(name)}"
            attack = 2 + (role in {"brute", "assassin", "beast", "elite"}) + boss
            block = 1 + (role in {"defender", "elite"}) + boss
            ward = 1 + (role in {"hexer", "controller"}) + boss
            family = body_family(name, role)
            regional_trait = REGIONAL_TRAITS[country]
            enemies.append({
                "id": identifier, "name": name, "country_id": country, "role": role,
                "tier": tier, "elite": elite, "boss": boss, "final_boss": country == "weltennaht" and boss,
                "stats": {"hp": 20 + tier * 5 + elite * 12 + boss * 24, "armor": 1 + tier // 2 + (role == "defender") + boss,
                          "block_dice": block, "block_threshold": 8, "ward_dice": ward,
                          "ward_threshold": 9, "attack_dice": attack, "hit_threshold": 7,
                          "damage_per_hit": 1 + tier // 2 + boss},
                "traits": [role, regional_trait] + (["phase_shift"] if boss else []),
                "intents": ["strike", "pressure" if attack >= 3 else "guard", "hex" if ward >= 2 else "advance"],
                "body_family": family, "rig_id": f"rig_{family}", "animation_set": f"combat_{family}",
                "visual_variant": f"{country}_{index + 1:02d}", "material_set": country,
                "scale": 1.32 if family == "giant" else 1.15 if boss else 1.0,
                "entrance_animation": "spawn", "death_style": "dissolve" if family in {"spirit", "swarm"} else "fall",
                "voice_profile": f"boss_{country}" if boss else f"enemy_{role}",
                "art": f"res://assets/enemies/{identifier}.svg",
                "lore": f"{name} gehört zu den unverwechselbaren Gefahren von {country.replace('_', ' ').title()}.",
            })
    return enemies


def make_cards() -> list[dict[str, Any]]:
    cards = [weapon_card(school, index, name) for school, names in WEAPON_NAMES.items() for index, name in enumerate(names)]
    cards += [magic_card(school, index, name) for school, names in MAGIC_NAMES.items() for index, name in enumerate(names)]
    cards += [universal_card(index, name) for index, name in enumerate(UNIVERSAL_NAMES)]
    return cards


def write_assets(cards: list[dict[str, Any]], items: list[dict[str, Any]], enemies: list[dict[str, Any]]) -> None:
    for directory in ("cards", "items", "enemies", "countries", "ui"):
        (CLIENT_ASSETS / directory).mkdir(parents=True, exist_ok=True)
    for card in cards:
        (CLIENT_ASSETS / "cards" / f"{card['id']}.svg").write_text(icon_svg(card["id"], "card", "card"), encoding="utf-8")
    for item in items:
        (CLIENT_ASSETS / "items" / f"{item['id']}.svg").write_text(icon_svg(item["id"], "item"), encoding="utf-8")
    for enemy in enemies:
        (CLIENT_ASSETS / "enemies" / f"{enemy['id']}.svg").write_text(icon_svg(enemy["id"], "enemy"), encoding="utf-8")
    for country in COUNTRY_IDS:
        (CLIENT_ASSETS / "countries" / f"{country}.svg").write_text(icon_svg(country, "country"), encoding="utf-8")
    ui_icons = ("attack", "defense", "magic", "utility", "health", "action_point", "armor", "ward", "loot", "server")
    for name in ui_icons:
        (CLIENT_ASSETS / "ui" / f"{name}.svg").write_text(icon_svg(name, "ui"), encoding="utf-8")


def main() -> None:
    cards = make_cards()
    items = make_weapon_items() + make_support_items()
    enemies = make_enemies()
    assert len(cards) == 144, len(cards)
    assert len(items) == 152, len(items)
    assert len(enemies) == 140, len(enemies)
    assert len({entry["id"] for entry in cards}) == len(cards)
    assert len({entry["id"] for entry in items}) == len(items)
    assert len({entry["id"] for entry in enemies}) == len(enemies)
    write_json(SHARED / "cards.json", {"content_version": 3, "cards": cards})
    write_json(SHARED / "items.json", {"content_version": 2, "items": items})
    write_json(SHARED / "enemies.json", {"content_version": 2, "enemies": enemies})
    write_assets(cards, items, enemies)
    print(f"Generated {len(cards)} cards, {len(items)} items, {len(enemies)} enemies")


if __name__ == "__main__":
    main()
