#!/usr/bin/env python3
"""Generate Eidpfad's semantic 2D art and self-contained low-poly GLB library.

The generated files are deliberately deterministic.  Raster key art remains
hand-/model-generated, while icons and gameplay models can be rebuilt after a
content change without silently losing coverage.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "client" / "assets"
SHARED = ROOT / "shared"

RARITY_COLORS = {
    "normal": "#a8b0b3",
    "rare": "#5f93b5",
    "enhanced": "#69a96e",
    "exceptional": "#9a72bd",
    "legendary": "#d09245",
    "unique": "#bd5260",
}
PHASE_COLORS = {
    "attack": "#a94742",
    "defense": "#4f8295",
    "magic": "#775ca2",
    "utility": "#9b814d",
}
SCHOOL_COLORS = {
    "dual_blades": "#b15050", "axe": "#9c6c43", "bow": "#66865e", "crossbow": "#70848a", "longsword": "#8d846f",
    "rune": "#65a5b4", "ember": "#c66a3f", "veil": "#78699e", "blood": "#a43f54",
    "universal": "#a68e60",
}
COUNTRY_COLORS = {
    "nebelmark": ("#40574c", "#8aa391"), "sonnenbruch": ("#9a6537", "#d9b66a"),
    "frostreiche": ("#587b91", "#b8d8de"), "splitterinseln": ("#3f7180", "#84b8bd"),
    "aschenlande": ("#653d35", "#d06c48"), "dornwall": ("#4f673e", "#a35b67"),
    "glassteppe": ("#61749a", "#a58bc1"), "tiefenwald": ("#36543e", "#7c9b62"),
    "kupferkueste": ("#75573c", "#b87b4e"), "knochental": ("#756f62", "#c7bea4"),
    "nachtkrone": ("#3e405f", "#8c82b2"), "sturmmarsch": ("#485a67", "#8ab2c0"),
    "versunkener_bund": ("#315d5c", "#64a69a"), "weltennaht": ("#563d5e", "#c06f87"),
}
COUNTRY_BIOMES = {
    "nebelmark": "moor", "sonnenbruch": "desert", "frostreiche": "frost",
    "splitterinseln": "coast", "aschenlande": "ash", "dornwall": "thorn",
    "glassteppe": "crystal", "tiefenwald": "forest", "kupferkueste": "coast",
    "knochental": "bone", "nachtkrone": "night", "sturmmarsch": "storm",
    "versunkener_bund": "sunken", "weltennaht": "rift",
}


def read_catalog(name: str) -> dict[str, Any]:
    return json.loads((SHARED / f"{name}.json").read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def rgb(hex_color: str, alpha: float = 1.0) -> list[float]:
    value = hex_color.lstrip("#")
    return [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)] + [alpha]


def shade(hex_color: str, factor: float) -> str:
    value = rgb(hex_color)
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(channel * 255 * factor))) for channel in value[:3])


def write_svg(path: Path, body: str, width: int = 512, height: int = 512, kind: str = "icon") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" data-asset-kind="{kind}">\n{body}\n</svg>\n',
        encoding="utf-8",
    )


SYMBOLS = {
    "attack": '<path d="M182 356 326 212l-26-26 34-72 64 64-72 34-26-26-144 144z"/><path d="m160 300 52 52-58 58-52-52z"/>',
    "defense": '<path d="M256 92 390 144v102c0 86-54 142-134 174-80-32-134-88-134-174V144zm0 58-74 29v67c0 52 27 89 74 113 47-24 74-61 74-113v-67z" fill-rule="evenodd"/>',
    "magic": '<path d="m256 84 31 93 97-20-72 69 67 73-96-25-27 95-27-95-96 25 67-73-72-69 97 20z"/><circle cx="256" cy="226" r="46"/>',
    "utility": '<path d="M144 112h224v46l-78 91v92h54v58H168v-58h54v-92l-78-91zm64 46 48 56 48-56z" fill-rule="evenodd"/>',
    "dual_blades": '<path d="m122 376 78-26 76-180 38-38 22 22-30 45-77 181-73 51zm234 0-78-26-76-180-38-38-22 22 30 45 77 181 73 51z"/>',
    "axe": '<path d="m236 414 32-4-4-183 55-17 70-72-26-48-104 28-27 66zm28-222 72-21-36 56z"/>',
    "bow": '<path d="M160 84c122 66 122 278 0 344l-26-42c85-48 85-212 0-260zm4 22 208 300-18 12-208-300z"/>',
    "crossbow": '<path d="M104 130c104 42 200 42 304 0l18 48c-62 26-114 38-148 39v199h-44V217c-34-1-86-13-148-39zm64 85h176v40H168z"/>',
    "longsword": '<path d="m238 80h36l-8 238 72 18v32h-72v72h-36v-72h-72v-32l72-18z"/>',
    "rune": '<path d="M164 390V122h54v86l76-86h68l-94 103 106 165h-67l-77-123-12 13v110z"/>',
    "ember": '<path d="M262 76c18 82-59 92-32 168 18-28 38-44 43-82 78 76 106 141 57 211-39 56-129 62-169 5-42-59-6-120 35-157-9 69 25 91 45 105-17-73 68-111 21-250z"/>',
    "veil": '<path d="M256 96c82 0 148 66 148 148s-66 148-148 148S108 326 108 244 174 96 256 96zm0 58c-50 0-90 40-90 90s40 90 90 90c-49-36-48-144 0-180z" fill-rule="evenodd"/>',
    "blood": '<path d="M256 74c54 88 122 155 122 235 0 68-55 123-122 123s-122-55-122-123c0-80 68-147 122-235zm-37 246c0 35 22 59 61 64-70 31-111-50-61-116z" fill-rule="evenodd"/>',
    "armor": '<path d="m171 104 56 32h58l56-32 64 72-50 54v184H157V230l-50-54zm56 32 29 75 29-75z"/>',
    "talisman": '<circle cx="256" cy="278" r="112" fill="none" stroke="currentColor" stroke-width="36"/><path d="m224 88 32-34 32 34-32 96zm32 116 31 55 62 12-44 45 8 63-57-28-57 28 8-63-44-45 62-12z"/>',
    "alchemy": '<path d="M204 76h104v48h-18v75l75 124c31 52-6 111-66 111h-86c-60 0-97-59-66-111l75-124v-75h-18zm6 238-21 35c-9 15 2 33 24 33h86c22 0 33-18 24-33l-21-35z" fill-rule="evenodd"/>',
    "relic": '<path d="m256 62 112 86-42 238-70 64-70-64-42-238zm0 68-46 45 46 187 46-187z" fill-rule="evenodd"/>',
    "offhand": '<path d="M256 86 396 146v92c0 96-57 159-140 196-83-37-140-100-140-196v-92zm-20 76v200h40V162z"/>',
}


def card_svg(card: dict[str, Any]) -> str:
    phase = card["phase"]
    school = card["school"]
    rarity = card["rarity"]
    accent = RARITY_COLORS[rarity]
    phase_color = PHASE_COLORS[phase]
    school_color = SCHOOL_COLORS.get(school, SCHOOL_COLORS["universal"])
    mark = digest(card["id"])[0] % 8
    symbol = SYMBOLS.get(school, SYMBOLS[phase])
    effect_symbol = SYMBOLS[phase]
    return f'''<defs>
  <linearGradient id="bg" x2="0" y2="1"><stop stop-color="{shade(school_color, .52)}"/><stop offset="1" stop-color="#0c1114"/></linearGradient>
  <linearGradient id="rim"><stop stop-color="{accent}"/><stop offset=".5" stop-color="{phase_color}"/><stop offset="1" stop-color="{accent}"/></linearGradient>
  <radialGradient id="glow"><stop stop-color="{school_color}" stop-opacity=".55"/><stop offset="1" stop-color="{school_color}" stop-opacity="0"/></radialGradient>
</defs>
<rect width="512" height="704" rx="34" fill="#080d10"/>
<rect x="19" y="19" width="474" height="666" rx="27" fill="url(#bg)" stroke="url(#rim)" stroke-width="6"/>
<path d="M47 122h418M47 578h418" stroke="{accent}" stroke-opacity=".5" stroke-width="3"/>
<circle cx="256" cy="337" r="176" fill="url(#glow)"/>
<g fill="{school_color}" opacity=".14" transform="translate(0 {mark * 3 - 10}) scale(1.15) translate(-34 -38)">{symbol}</g>
<g fill="{accent}" stroke="#080d10" stroke-width="8" stroke-linejoin="round" transform="translate(91 100) scale(.64)">{effect_symbol}</g>
<circle cx="76" cy="72" r="25" fill="{phase_color}" stroke="{accent}" stroke-width="4"/>
<path d="M76 57v30M61 72h30" stroke="#f4ead6" stroke-width="6" transform="rotate({mark * 22.5} 76 72)"/>
<path d="M70 616h372l-28 36H98z" fill="{shade(accent,.48)}" stroke="{accent}" stroke-width="3"/>
<g fill="#f2e9d6" opacity=".92" transform="translate(192 587) scale(.25)">{symbol}</g>'''


def item_svg(item: dict[str, Any]) -> str:
    rarity = item["rarity"]
    accent = RARITY_COLORS[rarity]
    slot = item["slot"]
    school = item.get("weapon_school", slot)
    symbol = SYMBOLS.get(str(school), SYMBOLS.get(slot, SYMBOLS["relic"]))
    glow = SCHOOL_COLORS.get(str(school), "#7f8c82")
    turn = digest(item["id"])[0] % 18 - 9
    return f'''<defs><radialGradient id="g"><stop stop-color="{glow}" stop-opacity=".52"/><stop offset="1" stop-color="#10171a"/></radialGradient></defs>
<rect width="512" height="512" rx="38" fill="#090e11"/>
<path d="M64 24h384l40 40v384l-40 40H64l-40-40V64z" fill="url(#g)" stroke="{accent}" stroke-width="7"/>
<circle cx="256" cy="256" r="168" fill="#070b0d" fill-opacity=".48" stroke="{accent}" stroke-opacity=".35" stroke-width="3"/>
<g fill="{accent}" stroke="#050809" stroke-width="7" stroke-linejoin="round" transform="rotate({turn} 256 256)">{symbol}</g>
<path d="M72 426h368" stroke="{accent}" stroke-width="5"/>
<circle cx="86" cy="86" r="18" fill="{accent}"/><circle cx="426" cy="86" r="8" fill="{accent}"/>'''


ROLE_SYMBOL = {
    "skirmisher": "dual_blades", "brute": "axe", "defender": "defense", "hexer": "magic",
    "marksman": "bow", "assassin": "dual_blades", "beast": "attack", "controller": "rune",
    "elite": "armor", "boss": "relic",
}


def enemy_svg(enemy: dict[str, Any]) -> str:
    primary, accent = COUNTRY_COLORS[enemy["country_id"]]
    role = enemy["role"]
    symbol = SYMBOLS[ROLE_SYMBOL[role]]
    horns = 18 + digest(enemy["id"])[0] % 32
    crown = '<path d="m158 152 42-68 56 56 56-56 42 68-32 25H190z"/>' if enemy["boss"] else ""
    return f'''<defs><radialGradient id="bg"><stop stop-color="{primary}"/><stop offset="1" stop-color="#080d10"/></radialGradient></defs>
<rect width="512" height="512" rx="36" fill="#080c0f"/>
<rect x="20" y="20" width="472" height="472" rx="28" fill="url(#bg)" stroke="{accent}" stroke-width="5"/>
<circle cx="256" cy="258" r="171" fill="#050809" fill-opacity=".46"/>
<path d="M150 414c12-99 50-144 106-144s94 45 106 144z" fill="{shade(primary,.66)}" stroke="{accent}" stroke-width="6"/>
<path d="M185 245c0-75 29-126 71-126s71 51 71 126l-28 42h-86z" fill="{shade(accent,.72)}" stroke="#0b1012" stroke-width="8"/>
<path d="m{185-horns} 230 {horns} -88 34 94m108-6 {horns} -88-34 94" fill="none" stroke="{accent}" stroke-width="10" stroke-linecap="round"/>
<circle cx="226" cy="228" r="10" fill="{accent}"/><circle cx="286" cy="228" r="10" fill="{accent}"/>
<g fill="{accent}" opacity=".85" transform="translate(205 303) scale(.20)">{symbol}</g>{crown}
<path d="M72 450h368" stroke="{accent}" stroke-opacity=".55" stroke-width="4"/>'''


BIOME_SYMBOL = {
    "moor": '<path d="M126 370c44-36 74-31 112 0 44-62 89-62 148 0M152 302c37-44 69-44 105 0 37-44 69-44 105 0" fill="none" stroke="currentColor" stroke-width="28"/>',
    "desert": '<path d="M76 363c89-103 164-87 214-4 43-64 88-53 146 4z"/><circle cx="354" cy="160" r="66"/>',
    "frost": '<path d="M256 80v352M103 168l306 176M409 168 103 344M256 80l-34 58m34-58 34 58M103 168l68 2m-68-2 32 60M409 168l-68 2m68-2-32 60" fill="none" stroke="currentColor" stroke-width="24"/>',
    "coast": '<path d="M74 340c57-58 106-58 163 0s106 58 201 0v64H74zm172-23 42-204 53 204z"/>',
    "ash": SYMBOLS["ember"],
    "thorn": '<path d="M108 404c134-84 44-222 250-298-64 74-11 136-94 198 54-7 91 10 124 47-85-18-111 60-204 48z"/><path d="m161 305-65-34 78-12m91-44 70-58-20 90" fill="none" stroke="currentColor" stroke-width="24"/>',
    "crystal": '<path d="m256 62 112 133-47 240H191l-47-240zm0 0v373m-112-240 112 76 112-76" fill="none" stroke="currentColor" stroke-width="22"/>',
    "forest": '<path d="m256 58 96 132h-54l89 113h-68l73 104H120l73-104h-68l89-113h-54z"/>',
    "bone": '<path d="M106 215c0-44 52-61 81-28l138 138c33 29 16 81-28 81-21 0-36-12-43-29L116 239c-17-7-29-22-29-43m319 29c0-44-52-61-81-28L187 335c-29 33-81 16-81-28 0-21 12-36 29-43l138-138c7-17 22-29 43-29"/>',
    "night": '<path d="M354 105c-84 5-148 76-148 161 0 77 53 141 124 157-22 8-46 12-71 12-112 0-202-90-202-202S147 31 259 31c35 0 68 9 95 25z"/><path d="m370 152 14 34 37 3-29 23 9 36-31-20-32 20 10-36-29-23 36-3z"/>',
    "storm": '<path d="M294 54 132 287h107l-32 171 173-248H270z"/>',
    "sunken": '<path d="M256 68v257m-89-176c0 56 89 85 89 85s89-29 89-85M120 314c32 87 240 87 272 0M170 397l-35 45m207-45 35 45" fill="none" stroke="currentColor" stroke-width="28"/>',
    "rift": '<path d="m249 40 69 118-45 75 72 63-84 176-19-129-75-53 62-79-47-65z"/>',
}


def country_svg(country: str) -> str:
    primary, accent = COUNTRY_COLORS[country]
    biome = COUNTRY_BIOMES[country]
    symbol = BIOME_SYMBOL[biome]
    return f'''<defs><radialGradient id="g"><stop stop-color="{primary}"/><stop offset="1" stop-color="#080d10"/></radialGradient></defs>
<circle cx="256" cy="256" r="232" fill="#080c0f" stroke="{accent}" stroke-width="9"/>
<circle cx="256" cy="256" r="202" fill="url(#g)" stroke="{accent}" stroke-opacity=".45" stroke-width="4"/>
<g color="{accent}" fill="{accent}" transform="translate(52 52) scale(.8)">{symbol}</g>
<path d="M118 430c90-26 186-26 276 0" fill="none" stroke="{accent}" stroke-width="8"/>
<circle cx="256" cy="52" r="13" fill="{accent}"/>'''


UI_SYMBOLS = {
    **{key: SYMBOLS[key] for key in ("attack", "defense", "magic", "utility", "armor")},
    "action_point": '<path d="m272 52-146 242h113l-5 166 152-256H272z"/>',
    "health": '<path d="M256 434 84 260c-85-92 51-215 132-124l40 45 40-45c81-91 217 32 132 124z"/>',
    "ward": SYMBOLS["rune"], "loot": '<path d="M91 181h330v236H91zM69 117h374v86H69zm139 0c-70-55-18-116 48-33 66-83 118-22 48 33z"/>',
    "server": '<ellipse cx="256" cy="112" rx="150" ry="58"/><path d="M106 112v104c0 32 67 58 150 58s150-26 150-58V112M106 216v104c0 32 67 58 150 58s150-26 150-58V216M106 320v80c0 32 67 58 150 58s150-26 150-58v-80" fill="none" stroke="currentColor" stroke-width="34"/>',
    "settings": '<path d="m256 58 29 48 55-2 9 54 51 24-21 51 35 42-40 37 14 53-54 17-16 53-54-9-38 40-38-40-54 9-16-53-54-17 14-53-40-37 35-42-21-51 51-24 9-54 55 2zm0 122a76 76 0 1 0 0 152 76 76 0 0 0 0-152z" fill-rule="evenodd"/>',
    "campaign": '<path d="M88 86h336v340H88zm54 62v216h228V148zM185 198h142v35H185zm0 72h142v35H185z" fill-rule="evenodd"/>',
    "connection": '<path d="M76 182c101-97 259-97 360 0l-43 44c-77-73-197-73-274 0zm74 74c59-57 153-57 212 0l-44 44c-35-32-89-32-124 0zm62 73c25-24 63-24 88 0l-44 51z"/>',
    "ready": '<path d="m91 268 91 92 240-241 43 44-283 284L48 312z"/>',
    "reaction": '<path d="M83 238 212 109v78h74c91 0 151 57 151 151 0 31-8 61-24 87-4-101-48-157-127-157h-74v78z"/>',
    "cooperation": '<path d="M169 257a74 74 0 1 0 0-148 74 74 0 0 0 0 148zm174 0a74 74 0 1 0 0-148 74 74 0 0 0 0 148zM46 422c8-93 52-140 123-140 42 0 76 17 98 51 22-34 55-51 98-51 70 0 114 47 123 140z"/>',
    "threat": '<path d="m256 52 205 366H51zm0 112-25 142h50zm0 196a25 25 0 1 0 0 50 25 25 0 0 0 0-50z" fill-rule="evenodd"/>',
    "oath_power": SYMBOLS["relic"],
    "legacy": '<path d="M89 92h253l81 81v247H89zm64 64v200h206V203l-47-47zM197 214h118v44H197zm0 76h118v44H197z" fill-rule="evenodd"/>',
    "new_game_plus": '<path d="M256 70a186 186 0 1 0 174 120h-68a123 123 0 1 1-36-31l-71 71h190V41l-72 72A184 184 0 0 0 256 70z"/>',
    "objective": '<path d="M256 54a202 202 0 1 0 0 404 202 202 0 0 0 0-404zm0 66a136 136 0 1 1 0 272 136 136 0 0 1 0-272zm0 70a66 66 0 1 1 0 132 66 66 0 0 1 0-132z" fill-rule="evenodd"/>',
}


def ui_svg(name: str) -> str:
    symbol = UI_SYMBOLS[name]
    return f'''<circle cx="256" cy="256" r="230" fill="#10171b" stroke="#867657" stroke-width="8"/>
<g color="#d7c49a" fill="#d7c49a" stroke-linejoin="round">{symbol}</g>'''


@dataclass(frozen=True)
class Material:
    name: str
    color: str
    metallic: float = 0.0
    roughness: float = 0.75
    emissive: str | None = None


def _rotate_vector(vector: tuple[float, float, float], quaternion: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Rotate a vector by an x/y/z/w quaternion without external dependencies."""

    x, y, z = vector
    qx_value, qy_value, qz_value, qw_value = quaternion
    tx = 2.0 * (qy_value * z - qz_value * y)
    ty = 2.0 * (qz_value * x - qx_value * z)
    tz = 2.0 * (qx_value * y - qy_value * x)
    return (
        x + qw_value * tx + (qy_value * tz - qz_value * ty),
        y + qw_value * ty + (qz_value * tx - qx_value * tz),
        z + qw_value * tz + (qx_value * ty - qy_value * tx),
    )


def _normalise(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / length for value in vector)


class GlbBuilder:
    """Dependency-free glTF 2.0 writer with embedded runtime animations."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.binary = bytearray()
        self.buffer_views: list[dict[str, Any]] = []
        self.accessors: list[dict[str, Any]] = []
        self.materials: list[dict[str, Any]] = []
        self.material_cache: dict[Material, int] = {}
        self.meshes: list[dict[str, Any]] = []
        self.mesh_cache: dict[tuple[str, int], int] = {}
        self.mesh_sources: dict[int, tuple[str, Material]] = {}
        self.nodes: list[dict[str, Any]] = [{"name": f"{name}_root", "children": []}]
        self.scene_roots: list[int] = [0]
        self.node_names: dict[str, list[int]] = {}
        self.animations: list[dict[str, Any]] = []
        self.skins: list[dict[str, Any]] = []
        self.rig_root: int | None = None
        self.extensions_used: list[str] = []
        self.images: list[dict[str, Any]] = []
        self.textures: list[dict[str, Any]] = []
        self.samplers: list[dict[str, Any]] = []
        self._install_embedded_texture()

    def _append(self, data: bytes, target: int | None) -> int:
        while len(self.binary) % 4:
            self.binary.append(0)
        index = len(self.buffer_views)
        view = {"buffer": 0, "byteOffset": len(self.binary), "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.buffer_views.append(view)
        self.binary.extend(data)
        return index

    def _accessor(self, values: Iterable[Any], component: int, kind: str, target: int | None) -> int:
        flat: list[float | int] = []
        rows = list(values)
        for row in rows:
            flat.extend(row if isinstance(row, (list, tuple)) else [row])
        fmt = {5126: "f", 5125: "I", 5123: "H"}[component]
        view = self._append(struct.pack("<" + fmt * len(flat), *flat), target)
        result: dict[str, Any] = {"bufferView": view, "componentType": component, "count": len(rows), "type": kind}
        if component == 5126 and rows and kind == "VEC3":
            result["min"] = [min(float(row[i]) for row in rows) for i in range(3)]
            result["max"] = [max(float(row[i]) for row in rows) for i in range(3)]
        elif component == 5126 and rows and kind == "SCALAR":
            result["min"] = [min(float(value) for value in rows)]
            result["max"] = [max(float(value) for value in rows)]
        index = len(self.accessors)
        self.accessors.append(result)
        return index

    def material(self, value: Material) -> int:
        if value in self.material_cache:
            return self.material_cache[value]
        base = rgb(value.color)
        definition: dict[str, Any] = {
            "name": value.name,
            "pbrMetallicRoughness": {"baseColorFactor": base, "baseColorTexture": {"index": 0}, "metallicFactor": value.metallic, "roughnessFactor": value.roughness},
        }
        if value.emissive:
            definition["emissiveFactor"] = rgb(value.emissive)[:3]
        index = len(self.materials)
        self.materials.append(definition)
        self.material_cache[value] = index
        return index

    def mesh(self, primitive: str, material: Material) -> int:
        mat = self.material(material)
        key = (primitive, mat)
        if key in self.mesh_cache:
            return self.mesh_cache[key]
        positions, normals, indices = primitive_mesh(primitive)
        position_accessor = self._accessor(positions, 5126, "VEC3", 34962)
        normal_accessor = self._accessor(normals, 5126, "VEC3", 34962)
        texcoords = [((position[0] + 1.0) * .5, (position[2] + 1.0) * .5) for position in positions]
        texcoord_accessor = self._accessor(texcoords, 5126, "VEC2", 34962)
        index_accessor = self._accessor(indices, 5125, "SCALAR", 34963)
        index = len(self.meshes)
        self.meshes.append({"name": primitive, "primitives": [{"attributes": {"POSITION": position_accessor, "NORMAL": normal_accessor, "TEXCOORD_0": texcoord_accessor}, "indices": index_accessor, "material": mat}]})
        self.mesh_sources[index] = (primitive, material)
        self.mesh_cache[key] = index
        return index

    def shape(
        self, primitive: str, name: str, material: Material, position: tuple[float, float, float],
        scale: tuple[float, float, float], rotation: tuple[float, float, float, float] | None = None,
    ) -> int:
        node: dict[str, Any] = {"name": name, "mesh": self.mesh(primitive, material), "translation": list(position), "scale": list(scale)}
        if rotation:
            node["rotation"] = list(rotation)
        index = len(self.nodes)
        self.nodes.append(node)
        self.nodes[0]["children"].append(index)
        self.node_names.setdefault(name, []).append(index)
        return index

    def matching_nodes(self, fragments: tuple[str, ...]) -> list[int]:
        return [index for name, indices in self.node_names.items() if any(fragment in name for fragment in fragments) for index in indices]

    def add_animation(self, name: str, tracks: list[tuple[int, str, list[float], list[Any]]]) -> None:
        samplers: list[dict[str, Any]] = []
        channels: list[dict[str, Any]] = []
        for node, target_path, times, values in tracks:
            value_kind = "VEC4" if target_path == "rotation" else "VEC3"
            input_accessor = self._accessor(times, 5126, "SCALAR", None)
            output_accessor = self._accessor(values, 5126, value_kind, None)
            sampler_index = len(samplers)
            samplers.append({"input": input_accessor, "output": output_accessor, "interpolation": "LINEAR"})
            channels.append({"sampler": sampler_index, "target": {"node": node, "path": target_path}})
        self.animations.append({"name": name, "samplers": samplers, "channels": channels})

    def add_basic_rig(self) -> None:
        """Bind every visible body part to a small semantic glTF skeleton."""

        joint_names = ("rig_root", "rig_spine", "rig_head", "rig_arm_l", "rig_arm_r", "rig_leg_l", "rig_leg_r")
        joint_translations = (
            (0.0, 0.0, 0.0), (0.0, 1.05, 0.0), (0.0, 1.0, 0.0),
            (-0.65, 0.5, 0.0), (0.65, 0.5, 0.0),
            (-0.28, 0.55, 0.0), (0.28, 0.55, 0.0),
        )
        joints: list[int] = []
        for name, translation in zip(joint_names, joint_translations):
            index = len(self.nodes)
            node: dict[str, Any] = {"name": name}
            if translation != (0.0, 0.0, 0.0):
                node["translation"] = list(translation)
            self.nodes.append(node)
            self.node_names.setdefault(name, []).append(index)
            joints.append(index)
        self.nodes[0]["children"].append(joints[0])
        self.nodes[joints[0]]["children"] = [joints[1], joints[5], joints[6]]
        self.nodes[joints[1]]["children"] = [joints[2], joints[3], joints[4]]
        global_joint_positions = (
            (0.0, 0.0, 0.0), (0.0, 1.05, 0.0), (0.0, 2.05, 0.0),
            (-0.65, 1.55, 0.0), (0.65, 1.55, 0.0),
            (-0.28, 0.55, 0.0), (0.28, 0.55, 0.0),
        )
        inverse_bind_matrices = [
            (1,0,0,0, 0,1,0,0, 0,0,1,0, -x,-y,-z,1)
            for x, y, z in global_joint_positions
        ]
        inverse_accessor = self._accessor(inverse_bind_matrices, 5126, "MAT4", None)
        self.skins.append({"name": f"{self.name}_skin", "joints": joints, "skeleton": joints[0], "inverseBindMatrices": inverse_accessor})
        self.rig_root = joints[0]

        def joint_for(node_name: str) -> int:
            lowered = node_name.lower()
            if any(value in lowered for value in ("head", "helm", "horn", "crown")):
                return 2
            if any(value in lowered for value in ("left_arm", "arm_l", "blade", "bow_", "crossbow_")):
                return 3
            if any(value in lowered for value in ("right_arm", "arm_r", "axe_", "shield")):
                return 4
            if "left_leg" in lowered or "leg_l" in lowered:
                return 5
            if "right_leg" in lowered or "leg_r" in lowered:
                return 6
            if any(value in lowered for value in ("torso", "body", "chest", "spine")):
                return 1
            return 0

        # Skinned mesh nodes must be scene roots without local TRS. Bake the shape
        # transform into its vertices and use inverse bind matrices for the rest pose.
        original_node_indices = list(range(1, joints[0]))
        for node_index in original_node_indices:
            node = self.nodes[node_index]
            if "mesh" not in node:
                continue
            source_mesh = int(node["mesh"])
            primitive_kind, material = self.mesh_sources[source_mesh]
            positions, normals, indices = primitive_mesh(primitive_kind)
            scale = tuple(float(value) for value in node.get("scale", (1.0, 1.0, 1.0)))
            translation = tuple(float(value) for value in node.get("translation", (0.0, 0.0, 0.0)))
            rotation = tuple(float(value) for value in node.get("rotation", (0.0, 0.0, 0.0, 1.0)))
            baked_positions = [
                tuple(a + b for a, b in zip(_rotate_vector(tuple(value * scale[i] for i, value in enumerate(position)), rotation), translation))
                for position in positions
            ]
            baked_normals = [_normalise(_rotate_vector(normal, rotation)) for normal in normals]
            position_accessor = self._accessor(baked_positions, 5126, "VEC3", 34962)
            normal_accessor = self._accessor(baked_normals, 5126, "VEC3", 34962)
            texcoords = [((position[0] + 1.0) * .5, (position[2] + 1.0) * .5) for position in positions]
            texcoord_accessor = self._accessor(texcoords, 5126, "VEC2", 34962)
            index_accessor = self._accessor(indices, 5125, "SCALAR", 34963)
            ordinal = joint_for(str(node.get("name", "")))
            joints_accessor = self._accessor([(ordinal, 0, 0, 0)] * len(positions), 5123, "VEC4", 34962)
            weights_accessor = self._accessor([(1.0, 0.0, 0.0, 0.0)] * len(positions), 5126, "VEC4", 34962)
            node["mesh"] = len(self.meshes)
            node["skin"] = 0
            for key in ("translation", "scale", "rotation"):
                node.pop(key, None)
            self.meshes.append({
                "name": f"{primitive_kind}_skinned_{len(self.meshes)}",
                "primitives": [{
                    "attributes": {
                        "POSITION": position_accessor, "NORMAL": normal_accessor,
                        "TEXCOORD_0": texcoord_accessor, "JOINTS_0": joints_accessor,
                        "WEIGHTS_0": weights_accessor,
                    },
                    "indices": index_accessor,
                    "material": self.material(material),
                }],
            })
            self.scene_roots.append(node_index)
        self.nodes[0]["children"] = [joints[0]]

        # A compact proxy is referenced through the standardized Microsoft LOD extension.
        proxy_mesh = self.mesh("cube", Material("lod_proxy", "#394247", .05, .96))
        proxy_node = len(self.nodes)
        self.nodes.append({"name": f"{self.name}_lod1", "mesh": proxy_mesh, "scale": [.45, 1.0, .32]})
        self.nodes[0].setdefault("extensions", {})["MSFT_lod"] = {"ids": [proxy_node]}
        self.extensions_used.append("MSFT_lod")
        self._prune_unused_meshes()

    def _prune_unused_meshes(self) -> None:
        used = sorted({int(node["mesh"]) for node in self.nodes if "mesh" in node})
        remap = {old: new for new, old in enumerate(used)}
        self.meshes = [self.meshes[index] for index in used]
        for node in self.nodes:
            if "mesh" in node:
                node["mesh"] = remap[int(node["mesh"])]
        self.mesh_cache.clear()
        self.mesh_sources.clear()

    def _install_embedded_texture(self) -> None:
        # 4x4 neutral weave. Base-color factors retain each material's palette.
        rows = bytearray()
        for y in range(4):
            rows.append(0)
            for x in range(4):
                value = 210 if (x + y) % 2 == 0 else 176
                rows.extend((value, value, value, 255))
        raw = bytes(rows)
        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
        view = self._append(png, None)
        self.images = [{"name": "embedded_weave", "bufferView": view, "mimeType": "image/png"}]
        self.samplers = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
        self.textures = [{"sampler": 0, "source": 0}]

    def save(self, path: Path) -> None:
        document = {
            "asset": {"version": "2.0", "generator": "Eidpfad visual asset pipeline"},
            "scene": 0, "scenes": [{"name": self.name, "nodes": self.scene_roots}],
            "nodes": self.nodes, "meshes": self.meshes, "materials": self.materials,
            "accessors": self.accessors, "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.binary)}],
        }
        if self.skins:
            document["skins"] = self.skins
        if self.images:
            document["images"] = self.images
            document["textures"] = self.textures
            document["samplers"] = self.samplers
        if self.extensions_used:
            document["extensionsUsed"] = sorted(set(self.extensions_used))
        if self.animations:
            document["animations"] = self.animations
        json_bytes = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
        binary = bytes(self.binary) + b"\0" * ((4 - len(self.binary) % 4) % 4)
        total = 12 + 8 + len(json_bytes) + 8 + len(binary)
        payload = bytearray(struct.pack("<4sII", b"glTF", 2, total))
        payload.extend(struct.pack("<I4s", len(json_bytes), b"JSON"))
        payload.extend(json_bytes)
        payload.extend(struct.pack("<I4s", len(binary), b"BIN\0"))
        payload.extend(binary)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def primitive_mesh(kind: str) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[int]]:
    if kind == "cube":
        positions: list[tuple[float, float, float]] = []
        normals: list[tuple[float, float, float]] = []
        indices: list[int] = []
        faces = [
            ((1, 0, 0), [(1,-1,-1),(1,1,-1),(1,1,1),(1,-1,1)]), ((-1,0,0), [(-1,-1,1),(-1,1,1),(-1,1,-1),(-1,-1,-1)]),
            ((0,1,0), [(-1,1,-1),(-1,1,1),(1,1,1),(1,1,-1)]), ((0,-1,0), [(-1,-1,1),(-1,-1,-1),(1,-1,-1),(1,-1,1)]),
            ((0,0,1), [(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]), ((0,0,-1), [(1,-1,-1),(-1,-1,-1),(-1,1,-1),(1,1,-1)]),
        ]
        for normal, corners in faces:
            start = len(positions); positions.extend(corners); normals.extend([normal] * 4); indices.extend([start,start+1,start+2,start,start+2,start+3])
        return positions, normals, indices
    if kind == "d12":
        phi = 1.61803398875; inv = 1 / phi
        vertices = [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),(1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1),(0,-inv,-phi),(0,-inv,phi),(0,inv,-phi),(0,inv,phi),(-inv,-phi,0),(-inv,phi,0),(inv,-phi,0),(inv,phi,0),(-phi,0,-inv),(-phi,0,inv),(phi,0,-inv),(phi,0,inv)]
        faces = [(17,16,0,12,1),(10,8,0,16,2),(14,12,0,8,4),(3,17,1,9,11),(5,9,1,12,14),(3,13,2,16,17),(6,10,2,13,15),(15,13,3,11,7),(5,14,4,18,19),(6,18,4,8,10),(11,9,5,19,7),(19,18,6,15,7)]
        p: list[tuple[float,float,float]]=[]; n: list[tuple[float,float,float]]=[]; idx: list[int]=[]
        for face in faces:
            center = tuple(sum(vertices[v][axis] for v in face)/5 for axis in range(3)); length=math.sqrt(sum(v*v for v in center)); normal=tuple(v/length for v in center)
            start=len(p); p.append(center); n.append(normal)
            for v in face: p.append(vertices[v]); n.append(normal)
            for i in range(5): idx.extend([start,start+1+i,start+1+(i+1)%5])
        return p,n,idx
    if kind == "sphere":
        latitudes, longitudes = 18, 32
        p=[]; n=[]; idx=[]
        for lat in range(latitudes + 1):
            theta = math.pi * lat / latitudes
            for lon in range(longitudes + 1):
                angle = math.tau * lon / longitudes
                normal = (math.sin(theta)*math.cos(angle), math.cos(theta), math.sin(theta)*math.sin(angle))
                p.append(normal); n.append(normal)
        for lat in range(latitudes):
            for lon in range(longitudes):
                a=lat*(longitudes+1)+lon; b=a+longitudes+1
                idx.extend([a,b,a+1,a+1,b,b+1])
        return p,n,idx
    segments = 24
    top_radius = 0.0 if kind == "cone" else 1.0
    p=[]; n=[]; idx=[]
    for side in range(segments):
        a=math.tau*side/segments; b=math.tau*(side+1)/segments
        normal_a=(math.cos(a),0,math.sin(a)); normal_b=(math.cos(b),0,math.sin(b)); start=len(p)
        p.extend([(math.cos(a),-1,math.sin(a)),(math.cos(b),-1,math.sin(b)),(math.cos(b)*top_radius,1,math.sin(b)*top_radius),(math.cos(a)*top_radius,1,math.sin(a)*top_radius)])
        n.extend([normal_a,normal_b,normal_b,normal_a]); idx.extend([start,start+1,start+2,start,start+2,start+3])
    for y, radius, normal, reverse in [(-1,1,(0,-1,0),True),(1,top_radius,(0,1,0),False)]:
        if radius == 0: continue
        center=len(p); p.append((0,y,0)); n.append(normal)
        for side in range(segments):
            a=math.tau*side/segments; p.append((math.cos(a)*radius,y,math.sin(a)*radius)); n.append(normal)
        for side in range(segments):
            a=center+1+side; b=center+1+(side+1)%segments
            idx.extend([center,b,a] if reverse else [center,a,b])
    return p,n,idx


def qz(degrees: float) -> tuple[float, float, float, float]:
    value = math.radians(degrees) / 2
    return (0.0, 0.0, math.sin(value), math.cos(value))


def qx(degrees: float) -> tuple[float, float, float, float]:
    value = math.radians(degrees) / 2
    return (math.sin(value), 0.0, 0.0, math.cos(value))


def qy(degrees: float) -> tuple[float, float, float, float]:
    value = math.radians(degrees) / 2
    return (0.0, math.sin(value), 0.0, math.cos(value))


def add_figure_animations(builder: GlbBuilder) -> None:
    """Embed in-place clips that Godot imports as AnimationPlayer animations."""
    root = builder.rig_root
    if root is None:
        raise RuntimeError("Figure animations require a skin rig")
    rig_spine = builder.matching_nodes(("rig_spine",))[0]
    rig_head = builder.matching_nodes(("rig_head",))[0]
    rig_arm_l = builder.matching_nodes(("rig_arm_l",))[0]
    rig_arm_r = builder.matching_nodes(("rig_arm_r",))[0]
    arms = [rig_arm_l, rig_arm_r]
    focus = [rig_head, rig_spine]
    builder.add_animation("idle", [
        (root, "translation", [0.0, 1.4, 2.8], [(0,0,0),(0,.035,0),(0,0,0)]),
        (root, "rotation", [0.0, 1.4, 2.8], [qy(-1.8), qy(1.8), qy(-1.8)]),
        (rig_spine, "rotation", [0.0, 1.4, 2.8], [qz(-.7), qz(.7), qz(-.7)]),
        (rig_head, "rotation", [0.0, 1.4, 2.8], [qy(1.2), qy(-1.2), qy(1.2)]),
    ])
    builder.add_animation("combat_idle", [
        (root, "translation", [0.0,.55,1.1], [(0,0,0),(0,.025,-.015),(0,0,0)]),
        (root, "rotation", [0.0,.55,1.1], [qz(-.8),qz(.8),qz(-.8)]),
    ])
    builder.add_animation("walk", [
        (root, "translation", [0.0,.25,.5,.75,1.0], [(0,0,0),(0,.045,-.07),(0,0,-.14),(0,.045,-.21),(0,0,-.28)]),
        (root, "rotation", [0.0,.25,.5,.75,1.0], [qz(-1.5),qz(1.5),qz(-1.5),qz(1.5),qz(-1.5)]),
    ])
    builder.add_animation("run", [
        (root, "translation", [0.0,.18,.36,.54,.72], [(0,0,0),(0,.07,-.13),(0,0,-.26),(0,.07,-.39),(0,0,-.52)]),
        (root, "rotation", [0.0,.18,.36,.54,.72], [qz(-2.5),qz(2.5),qz(-2.5),qz(2.5),qz(-2.5)]),
    ])
    attack_tracks: list[tuple[int,str,list[float],list[Any]]] = [
        (root, "translation", [0.0,.12,.25,.42], [(0,0,0),(0,.02,-.08),(0,.03,-.34),(0,0,0)]),
        (root, "rotation", [0.0,.18,.30,.42], [qy(-4),qy(7),qy(-8),qy(0)]),
    ]
    for node in arms[:8]:
        rest = tuple(builder.nodes[node].get("rotation", (0.0,0.0,0.0,1.0)))
        attack_tracks.append((node, "rotation", [0.0,.16,.30,.42], [rest,qz(42),qz(-72),rest]))
    builder.add_animation("attack", attack_tracks)
    builder.add_animation("heavy_attack", [
        (root, "translation", [0.0,.28,.52,.78], [(0,0,0),(0,.06,.06),(0,.03,-.46),(0,0,0)]),
        (root, "rotation", [0.0,.28,.52,.78], [qy(-10),qy(16),qy(-14),qy(0)]),
    ] + [(node,"rotation",[0.0,.28,.52,.78],[tuple(builder.nodes[node].get("rotation",(0.0,0.0,0.0,1.0))),qz(68),qz(-96),tuple(builder.nodes[node].get("rotation",(0.0,0.0,0.0,1.0)))]) for node in arms[:8]])
    builder.add_animation("cast", [
        (root, "translation", [0.0,.4,.8,1.15], [(0,0,0),(0,.08,0),(0,.05,-.05),(0,0,0)]),
        (root, "rotation", [0.0,.4,.8,1.15], [qy(0),qy(-6),qy(6),qy(0)]),
    ] + [(node,"scale",[0.0,.45,.8,1.15],[(1,1,1),(1.12,1.20,1.12),(1.04,1.08,1.04),(1,1,1)]) for node in focus[:4]])
    builder.add_animation("guard", [
        (root, "translation", [0.0,.18,.62], [(0,0,0),(0,-.04,.08),(0,0,0)]),
        (root, "rotation", [0.0,.18,.62], [qy(0),qy(-8),qy(0)]),
    ])
    builder.add_animation("dodge", [(root,"translation",[0.0,.18,.38,.62],[(0,0,0),(-.42,.03,.05),(-.70,0,.1),(0,0,0)]),(root,"rotation",[0.0,.3,.62],[qz(0),qz(12),qz(0)])])
    builder.add_animation("hit", [(root,"translation",[0.0,.08,.16,.30],[(0,0,0),(.13,.02,.12),(-.08,0,.06),(0,0,0)]),(root,"rotation",[0.0,.10,.20,.30],[qz(0),qz(-9),qz(5),qz(0)])])
    builder.add_animation("stagger", [(root,"translation",[0.0,.18,.42,.72],[(0,0,0),(0,0,.22),(.08,-.03,.30),(0,0,0)]),(root,"rotation",[0.0,.25,.52,.72],[qz(0),qz(-14),qz(8),qz(0)])])
    builder.add_animation("defeat", [(root,"translation",[0.0,.35,.8,1.25],[(0,0,0),(0,-.08,.08),(-.18,-.38,.16),(-.28,-.75,.2)]),(root,"rotation",[0.0,.35,.8,1.25],[qz(0),qz(-12),qz(-58),qz(-82)]),(root,"scale",[0.0,.9,1.25],[(1,1,1),(1,1,1),(.92,.92,.92)])])
    builder.add_animation("spawn", [(root,"scale",[0.0,.22,.48,.72],[(.05,.05,.05),(1.12,.72,1.12),(.94,1.08,.94),(1,1,1)]),(root,"translation",[0.0,.35,.72],[(0,-.45,0),(0,.08,0),(0,0,0)])])
    builder.add_animation("victory", [(root,"translation",[0.0,.35,.7,1.2],[(0,0,0),(0,.16,0),(0,.04,0),(0,0,0)]),(root,"rotation",[0.0,.35,.7,1.2],[qy(0),qy(-12),qy(15),qy(0)])])


def add_hover_animations(builder: GlbBuilder) -> None:
    builder.add_animation("loot_hover", [(0,"translation",[0.0,1.6,3.2],[(0,0,0),(0,.10,0),(0,0,0)]),(0,"rotation",[0.0,.8,1.6,2.4,3.2],[qy(0),qy(90),qy(180),qy(270),qy(0)])])
    builder.add_animation("reveal", [(0,"scale",[0.0,.24,.55],[(.05,.05,.05),(1.18,1.18,1.18),(1,1,1)]),(0,"rotation",[0.0,.55],[qy(-90),qy(0)])])


def add_environment_animation(builder: GlbBuilder) -> None:
    builder.add_animation("ambient", [(0,"translation",[0.0,2.5,5.0],[(0,0,0),(0,.025,0),(0,0,0)]),(0,"rotation",[0.0,2.5,5.0],[qy(-1),qy(1),qy(-1)])])


def materials(primary: str, accent: str) -> tuple[Material, Material, Material, Material]:
    return (
        Material("cloth", primary, 0.0, .92), Material("accent", accent, .08, .66),
        Material("metal", "#7b8588", .78, .38), Material("dark", "#171d20", .18, .82),
    )


def add_weapon(builder: GlbBuilder, school: str, x: float, y: float, palette: tuple[Material, Material, Material, Material], mirrored: bool = False) -> None:
    _, accent, metal, dark = palette
    direction = -1 if mirrored else 1
    if school == "axe":
        builder.shape("cylinder", "axe_handle", dark, (x, y, 0), (.035, .62, .035), qz(-12*direction))
        builder.shape("cube", "axe_head", metal, (x + .13*direction, y+.52, 0), (.25, .13, .07), qz(-12*direction))
        builder.shape("cone", "axe_edge", accent, (x + .32*direction, y+.52, 0), (.13, .20, .06), qz(-90*direction))
    elif school == "bow":
        builder.shape("cylinder", "bow_upper", accent, (x, y+.30, 0), (.025, .38, .025), qz(-22*direction))
        builder.shape("cylinder", "bow_lower", accent, (x, y-.30, 0), (.025, .38, .025), qz(22*direction))
        builder.shape("cylinder", "bow_string", metal, (x+.14*direction, y, 0), (.008, .70, .008))
    elif school == "crossbow":
        builder.shape("cylinder", "crossbow_stock", dark, (x, y, 0), (.04, .52, .04), qz(-8*direction))
        builder.shape("cube", "crossbow_limbs", accent, (x+.04*direction, y+.22, 0), (.38, .035, .04), qz(-8*direction))
        builder.shape("cylinder", "crossbow_bolt", metal, (x, y+.20, .05), (.012, .34, .012), qz(-8*direction))
    elif school == "longsword":
        builder.shape("cube", "longsword_blade", metal, (x, y+.18, 0), (.075, .64, .045), qz(-8*direction))
        builder.shape("cone", "longsword_point", metal, (x+.09*direction, y+.80, 0), (.075, .18, .045), qz(-8*direction))
        builder.shape("cube", "longsword_guard", accent, (x-.02*direction, y-.43, 0), (.25, .035, .055), qz(-8*direction))
        builder.shape("cylinder", "longsword_grip", dark, (x-.08*direction, y-.60, 0), (.04, .18, .04), qz(-8*direction))
    else:
        for offset in (-.08,.08):
            builder.shape("cube", "blade", metal, (x+offset*direction, y+.24, 0), (.045, .48, .055), qz((-12 if offset < 0 else 12)*direction))
            builder.shape("cube", "blade_grip", dark, (x+offset*direction, y-.24, 0), (.055, .15, .065), qz((-12 if offset < 0 else 12)*direction))


def add_humanoid(builder: GlbBuilder, palette: tuple[Material, Material, Material, Material], role: str, seed: int, boss: bool = False, weapon: str | None = None) -> None:
    cloth, accent, metal, dark = palette
    heavy = 1.18 if role in {"brute", "elite", "boss"} else .92 if role in {"assassin", "marksman"} else 1.0
    builder.shape("cylinder", "left_boot", dark, (-.18, .43, 0), (.10, .43, .11), qz(-3))
    builder.shape("cylinder", "right_boot", dark, (.18, .43, 0), (.10, .43, .11), qz(3))
    builder.shape("cylinder", "torso", cloth, (0, 1.22, 0), (.34*heavy, .48, .23))
    builder.shape("sphere", "shoulders", accent if role in {"defender","elite","boss"} else cloth, (0,1.52,0), (.48*heavy,.20,.28))
    builder.shape("sphere", "head", accent, (0, 1.94, 0), (.20, .23, .19))
    builder.shape("sphere", "left_eye", Material("eye_glow", "#d8c887", .0, .25, "#8fa9a3"), (-.072,1.98,.176),(.025,.018,.018))
    builder.shape("sphere", "right_eye", Material("eye_glow", "#d8c887", .0, .25, "#8fa9a3"), (.072,1.98,.176),(.025,.018,.018))
    builder.shape("cylinder", "belt", dark, (0,1.03,0),(.35*heavy,.055,.245))
    builder.shape("cube", "belt_buckle", metal, (0,1.03,.245),(.075,.065,.028))
    builder.shape("sphere", "left_knee", metal, (-.18,.72,.075),(.12,.10,.10))
    builder.shape("sphere", "right_knee", metal, (.18,.72,.075),(.12,.10,.10))
    builder.shape("cube", "cape", cloth, (0,1.32,-.25),(.34*heavy,.55,.035), qx(-8))
    helmet = role in {"defender", "elite", "boss"}
    if helmet:
        builder.shape("sphere", "helmet", metal, (0, 2.02, 0), (.23, .20, .22))
        builder.shape("cube", "visor", dark, (0,1.98,.18),(.20,.035,.04))
    for side in (-1,1):
        builder.shape("cylinder", "arm", cloth, (.43*side*heavy,1.25,0),(.075,.38,.075), qz(15*side))
        builder.shape("sphere", "glove", dark, (.52*side*heavy,.91,.015),(.10,.11,.09))
        builder.shape("sphere", "pauldron", metal if role in {"defender","elite","boss"} else accent, (.39*side*heavy,1.55,0),(.18,.14,.18))
    if role == "beast":
        builder.shape("cone", "left_horn", accent, (-.17,2.20,0),(.07,.25,.07), qz(22))
        builder.shape("cone", "right_horn", accent, (.17,2.20,0),(.07,.25,.07), qz(-22))
    if role in {"hexer", "controller", "boss"}:
        glow = Material("magic", accent.color, .1, .3, accent.color)
        builder.shape("sphere", "focus", glow, (.52,1.58,.10),(.12,.12,.12))
    if role in {"defender", "elite", "boss"}:
        builder.shape("cylinder", "shield", metal, (-.48,1.25,.08),(.34,.07,.34), qx(90))
    if boss:
        for side in (-1, 0, 1):
            builder.shape("cone", "crown_spike", accent, (.16*side,2.28,0),(.06,.20+.05*(side==0),.06))
        for side in (-1, 1):
            builder.shape("sphere", "oath_orb", Material("boss_glow", accent.color,.1,.22,accent.color), (.72*side,1.78,-.08),(.11,.11,.11))
    chosen = weapon or {"marksman":"bow", "brute":"axe", "assassin":"dual_blades", "skirmisher":"dual_blades"}.get(role, "axe")
    add_weapon(builder, chosen, .48, 1.12, palette)


def add_beast(builder: GlbBuilder, palette: tuple[Material, Material, Material, Material], seed: int, boss: bool = False) -> None:
    cloth, accent, _, dark = palette
    builder.shape("cylinder", "beast_body", cloth, (0, .84, 0), (.38, .65, .30), qz(90))
    builder.shape("sphere", "beast_head", accent, (.68, .92, 0), (.29, .31, .27))
    builder.shape("sphere", "beast_chest", cloth, (.28,.84,0),(.34,.39,.32))
    builder.shape("sphere", "beast_haunch", cloth, (-.34,.78,0),(.36,.34,.33))
    for x in (-.34,.34):
        for z in (-.18,.18):
            builder.shape("cylinder", "beast_leg", dark, (x,.37,z),(.075,.36,.075), qz(-8 if x<0 else 8))
            builder.shape("sphere", "beast_paw", accent, (x,.08,z),(.11,.07,.14))
    builder.shape("cone", "muzzle", dark, (.92,.86,0),(.16,.28,.15),qz(-90))
    for z in (-.13,.13): builder.shape("cone", "horn", accent, (.67,1.25,z),(.065,.28,.065),qz(-20 if z<0 else 20))
    builder.shape("cone", "left_ear", dark, (.55,1.25,-.17),(.07,.18,.07),qz(18))
    builder.shape("cone", "right_ear", dark, (.55,1.25,.17),(.07,.18,.07),qz(-18))
    eye = Material("beast_eye","#e3b75b",0,.18,"#e3b75b")
    builder.shape("sphere", "left_eye", eye, (.89,1.02,-.18),(.03,.03,.02))
    builder.shape("sphere", "right_eye", eye, (.89,1.02,.18),(.03,.03,.02))
    builder.shape("cone", "tail", accent, (-.76,.82,0),(.10,.46,.10),qz(72))
    if boss: builder.shape("sphere", "boss_crest", Material("glow", accent.color,.1,.25,accent.color), (.25,1.08,0),(.18,.18,.18))


def add_serpent(builder: GlbBuilder, palette: tuple[Material, Material, Material, Material], seed: int, boss: bool = False) -> None:
    cloth, accent, metal, dark = palette
    for index in range(9):
        x = -.78 + index * .19
        y = .42 + math.sin(index * .72) * .12
        z = math.cos(index * .55) * .12
        radius = .22 - abs(index - 5) * .012
        builder.shape("sphere", "serpent_segment", cloth if index % 2 else accent, (x,y,z),(radius,.18,radius))
    builder.shape("sphere", "serpent_head", accent, (.92,.64,0),(.33,.25,.28))
    builder.shape("sphere", "serpent_eye_left", Material("eye","#f1bd55",0,.2,"#f1bd55"),(.99,.72,.20),(.035,.035,.025))
    builder.shape("sphere", "serpent_eye_right", Material("eye","#f1bd55",0,.2,"#f1bd55"),(.99,.72,-.20),(.035,.035,.025))
    for side in (-1,1):
        builder.shape("cone", "fang", metal, (1.17,.55,.10*side),(.035,.14,.035),qx(180))
    if boss:
        builder.shape("sphere", "boss_crest", Material("glow",accent.color,.1,.2,accent.color),(.62,.92,0),(.22,.18,.24))


def add_arthropod(builder: GlbBuilder, palette: tuple[Material, Material, Material, Material], seed: int, boss: bool = False) -> None:
    cloth, accent, metal, dark = palette
    builder.shape("sphere", "carapace", cloth, (0,.72,0),(.55,.32,.44))
    builder.shape("sphere", "thorax", accent, (.52,.68,0),(.38,.28,.35))
    builder.shape("sphere", "head", dark, (.88,.68,0),(.24,.22,.28))
    for side in (-1,1):
        for index in range(4):
            z = side * (.18 + index * .12)
            builder.shape("cylinder", "leg_upper", metal, (.05 + index*.08,.46,z),(.045,.38,.045),qz((58+index*6)*side))
            builder.shape("cylinder", "leg_lower", dark, (.35 + index*.09,.18,z*1.5),(.035,.34,.035),qz((112+index*4)*side))
        builder.shape("cone", "claw", accent, (1.08,.55,.30*side),(.16,.32,.14),qz(-76))
    builder.shape("cone", "tail_sting", accent, (-.68,1.0,0),(.12,.45,.12),qz(32))
    if boss:
        builder.shape("sphere", "boss_crest", Material("glow",accent.color,.1,.2,accent.color),(0,1.02,0),(.28,.12,.28))


def add_harpy(builder: GlbBuilder, palette: tuple[Material, Material, Material, Material], seed: int, boss: bool = False) -> None:
    add_humanoid(builder, palette, "assassin", seed, boss, "dual_blades")
    _cloth, accent, metal, _dark = palette
    for side in (-1,1):
        for index in range(5):
            builder.shape("cone", "wing_feather", accent if index % 2 else metal, ((.48+index*.18)*side,1.48-index*.05,-.12),(.13,.48+index*.10,.075),qz((68+index*5)*side))


def add_spirit(builder: GlbBuilder, palette: tuple[Material, Material, Material, Material], seed: int, boss: bool = False) -> None:
    cloth, accent, _metal, dark = palette
    glow = Material("spirit_glow",accent.color,.05,.18,accent.color)
    builder.shape("cone", "spectral_body", cloth, (0,.92,0),(.46,.92,.36))
    builder.shape("sphere", "spectral_head", glow, (0,1.82,0),(.27,.31,.25))
    builder.shape("cube", "torn_veil", dark, (0,1.05,-.22),(.48,.70,.025),qx(-12))
    for index in range(5 if boss else 3):
        angle = math.tau * index / (5 if boss else 3)
        builder.shape("sphere", "wisp", glow, (math.cos(angle)*.62,1.20+index*.12,math.sin(angle)*.42),(.10,.10,.10))
    builder.shape("sphere", "left_eye", glow, (-.08,1.87,.23),(.035,.025,.02))
    builder.shape("sphere", "right_eye", glow, (.08,1.87,.23),(.035,.025,.02))


def add_swarm(builder: GlbBuilder, palette: tuple[Material, Material, Material, Material], seed: int, boss: bool = False) -> None:
    cloth, accent, _metal, dark = palette
    count = 18 if boss else 12
    for index in range(count):
        angle = index * 2.399963
        radius = .18 + (index % 5) * .13
        builder.shape("sphere", "swarm_body", accent if index % 3 else cloth, (math.cos(angle)*radius,.55+index*.07,math.sin(angle)*radius),(.09+(index%3)*.025,.07,.11))
        builder.shape("cone", "swarm_wing", dark, (math.cos(angle)*radius,.62+index*.07,math.sin(angle)*radius),(.08,.14,.035),qz(35 if index%2 else -35))


def add_giant(builder: GlbBuilder, palette: tuple[Material, Material, Material, Material], seed: int, boss: bool = False) -> None:
    add_humanoid(builder, palette, "boss" if boss else "brute", seed, boss, "axe")
    _cloth, accent, metal, _dark = palette
    for side in (-1,1):
        builder.shape("sphere", "giant_guard", metal, (.52*side,1.20,.02),(.26,.32,.22))
    builder.shape("d12", "giant_core", Material("core",accent.color,.15,.22,accent.color),(0,1.33,.26),(.16,.20,.08))


def make_character_models() -> list[str]:
    specs = [
        ("vanguard", "#4a2f2b", "#a26f45", "axe", "defender"),
        ("pathfinder", "#293f38", "#6d8d75", "bow", "marksman"),
        ("duelist", "#472d36", "#a85b68", "dual_blades", "assassin"),
        ("arbalist", "#343c40", "#6d8f98", "crossbow", "marksman"),
    ]
    paths=[]
    for name, primary, accent, weapon, role in specs:
        builder=GlbBuilder(name); add_humanoid(builder, materials(primary,accent), role, digest(name)[0], weapon=weapon)
        builder.add_basic_rig()
        add_figure_animations(builder)
        path=ASSETS/"models"/"characters"/f"{name}.glb"; builder.save(path); paths.append(path.as_posix())
    return paths


def make_enemy_model(enemy: dict[str, Any]) -> str:
    primary, accent = COUNTRY_COLORS[enemy["country_id"]]
    builder=GlbBuilder(enemy["id"]); palette=materials(shade(primary,.78),accent); seed=digest(enemy["id"])[0]
    family = str(enemy.get("body_family", "quadruped" if enemy["role"] == "beast" else "humanoid"))
    builders = {
        "quadruped": add_beast, "serpent": add_serpent, "arthropod": add_arthropod,
        "harpy": add_harpy, "spirit": add_spirit, "swarm": add_swarm, "giant": add_giant,
    }
    if family in builders:
        builders[family](builder,palette,seed,enemy["boss"])
    else:
        add_humanoid(builder,palette,enemy["role"],seed,enemy["boss"])
    builder.add_basic_rig()
    add_figure_animations(builder)
    path=ASSETS/"models"/"enemies"/f"{enemy['id']}.glb"; builder.save(path)
    return f"res://assets/models/enemies/{enemy['id']}.glb"


def make_item_model(item: dict[str, Any]) -> str:
    accent=RARITY_COLORS[item["rarity"]]; palette=materials("#3b3430",accent); builder=GlbBuilder(item["id"])
    cloth, bright, metal, dark=palette; slot=item["slot"]
    if slot == "weapon": add_weapon(builder,str(item.get("weapon_school","dual_blades")),0,0.75,palette)
    elif slot == "armor":
        builder.shape("cylinder","armor_body",cloth,(0,.85,0),(.44,.60,.24)); builder.shape("sphere","pauldrons",metal,(0,1.40,0),(.62,.20,.28)); builder.shape("cube","chest_rune",bright,(0,.92,.25),(.13,.22,.025))
    elif slot == "talisman":
        builder.shape("cylinder","chain",metal,(0,1.15,0),(.22,.035,.22),qx(90)); builder.shape("d12","gem",bright,(0,.70,0),(.22,.22,.12)); builder.shape("cylinder","link",metal,(0,.91,0),(.03,.20,.03))
    elif slot == "alchemy":
        builder.shape("sphere","flask",bright,(0,.65,0),(.30,.38,.25)); builder.shape("cylinder","neck",metal,(0,1.02,0),(.10,.20,.10)); builder.shape("cube","stopper",dark,(0,1.23,0),(.13,.08,.13))
    elif slot == "offhand":
        builder.shape("cylinder","shield",metal,(0,.75,0),(.52,.10,.52),qx(90)); builder.shape("d12","shield_rune",bright,(0,.75,.13),(.20,.20,.08))
    else:
        builder.shape("d12","relic_core",bright,(0,.78,0),(.38,.52,.30)); builder.shape("cylinder","relic_base",metal,(0,.22,0),(.42,.18,.42)); builder.shape("cone","relic_crown",dark,(0,1.35,0),(.26,.34,.26))
    add_hover_animations(builder)
    model_directory = "items/longsword" if item.get("weapon_school") == "longsword" else "items"
    path=ASSETS/"models"/model_directory/f"{item['id']}.glb"; builder.save(path)
    return f"res://assets/models/{model_directory}/{item['id']}.glb"


def make_country_models() -> list[str]:
    paths=[]
    for country, biome in COUNTRY_BIOMES.items():
        primary, accent=COUNTRY_COLORS[country]; builder=GlbBuilder(country); base=Material("earth",shade(primary,.62),0,.96); glow=Material("accent",accent,.12,.48,accent if biome in {"crystal","rift","night"} else None); stone=Material("stone","#5a5c59",.05,.92)
        builder.shape("cylinder","country_base",base,(0,-.12,0),(1.35,.18,1.35))
        if biome in {"forest","thorn","moor"}:
            builder.shape("cylinder","trunk",stone,(0,.72,0),(.20,.72,.20));
            for x,y,z,s in [(-.55,1.35,0,.62),(.45,1.45,.12,.68),(0,1.72,-.05,.76)]: builder.shape("sphere","crown",glow,(x,y,z),(s,.48,s))
        elif biome in {"frost","crystal"}:
            for x,h,z in [(-.55,1.0,.1),(0,1.45,0),(.58,.82,-.1)]: builder.shape("cone","spire",glow,(x,h*.55,z),(.28,h*.55,.28))
        elif biome in {"coast","sunken"}:
            builder.shape("cylinder","tower",stone,(0,.72,0),(.42,.75,.42)); builder.shape("cone","roof",glow,(0,1.62,0),(.58,.36,.58)); builder.shape("sphere","beacon",glow,(0,1.92,0),(.16,.16,.16))
        elif biome in {"desert","bone","ash"}:
            for x,h,r in [(-.55,1.0,-18),(0,1.55,0),(.55,.9,16)]: builder.shape("cone","monolith",glow,(x,h*.52,0),(.32,h*.52,.32),qz(r))
        elif biome in {"night","storm"}:
            builder.shape("cylinder","observatory",stone,(0,.62,0),(.68,.62,.68)); builder.shape("sphere","dome",glow,(0,1.35,0),(.72,.40,.72)); builder.shape("cone","lightning_rod",glow,(0,1.95,0),(.08,.45,.08))
        else:
            for x,r in [(-.55,-12),(0,0),(.55,12)]: builder.shape("cube","rift_pillar",stone,(x,.82,0),(.22,.82,.28),qz(r)); builder.shape("d12","rift_core",glow,(0,1.35,.1),(.36,.52,.22))
        add_environment_animation(builder)
        path=ASSETS/"models"/"countries"/f"{country}.glb"; builder.save(path); paths.append(f"res://assets/models/countries/{country}.glb")
    return paths


def make_prop_models() -> list[str]:
    names=("barricade","barrel","bridge","campfire","caravan","chest","market_stall","oath_stone","ruin_arch","shrine","tree","watchtower","oath_gate","warden_memory","warden_promise","anchor_origin","anchor_bond","anchor_future","armor_crown","armor_cuirass","armor_gauntlet","armor_greaves")
    paths=[]
    for name in names:
        builder=GlbBuilder(name); wood=Material("wood","#5b3f2e",0,.95); iron=Material("iron","#687175",.75,.42); stone=Material("stone","#696964",0,.96); cloth=Material("cloth","#62413d",0,.9); glow=Material("oath_glow","#79aeb2",.1,.3,"#79aeb2")
        if name=="barrel": builder.shape("cylinder","barrel",wood,(0,.5,0),(.42,.5,.42)); builder.shape("cylinder","hoop",iron,(0,.55,0),(.44,.05,.44))
        elif name=="chest": builder.shape("cube","chest",wood,(0,.42,0),(.72,.42,.48)); builder.shape("cube","bands",iron,(0,.44,.49),(.12,.36,.035)); builder.shape("cube","lock",glow,(0,.42,.54),(.10,.12,.04))
        elif name=="tree": builder.shape("cylinder","trunk",wood,(0,.9,0),(.18,.9,.18)); [builder.shape("sphere","foliage",cloth,(x,y,z),(s,.55,s)) for x,y,z,s in [(-.45,1.65,0,.65),(.42,1.75,0,.7),(0,2.05,0,.8)]]
        elif name=="campfire": [builder.shape("cylinder","log",wood,(0,.16,0),(.07,.5,.07),qz(r)) for r in (-58,58)]; builder.shape("cone","flame",glow,(0,.55,0),(.27,.48,.27))
        elif name=="bridge": [builder.shape("cube","plank",wood,(x,.18,0),(.16,.08,.72)) for x in [-.8,-.4,0,.4,.8]]; [builder.shape("cylinder","rail",iron,(0,.62,z),(.035,1.0,.035),qz(90)) for z in (-.68,.68)]
        elif name=="barricade": [builder.shape("cube","beam",wood,(0,.48,z),(.95,.10,.10),qz(r)) for z,r in [(-.12,18),(.12,-18)]]; [builder.shape("cone","spike",iron,(x,.92,0),(.07,.35,.07)) for x in (-.7,0,.7)]
        elif name=="caravan": builder.shape("cube","wagon",wood,(0,.72,0),(.95,.45,.62)); [builder.shape("cylinder","wheel",iron,(x,.42,z),(.32,.08,.32),qx(90)) for x in (-.62,.62) for z in (-.65,.65)]; builder.shape("cube","canopy",cloth,(0,1.42,0),(.92,.16,.60))
        elif name=="market_stall": builder.shape("cube","counter",wood,(0,.65,0),(.9,.15,.42)); builder.shape("cube","awning",cloth,(0,1.58,0),(.98,.12,.62)); [builder.shape("cylinder","post",wood,(x,1.0,z),(.05,.85,.05)) for x in (-.82,.82) for z in (-.48,.48)]
        elif name=="watchtower": builder.shape("cylinder","tower",stone,(0,1.0,0),(.58,1.0,.58)); builder.shape("cone","roof",cloth,(0,2.23,0),(.78,.42,.78)); [builder.shape("cube","crenel",stone,(x,1.95,z),(.16,.24,.16)) for x,z in [(-.45,-.45),(.45,-.45),(-.45,.45),(.45,.45)]]
        elif name=="ruin_arch": [builder.shape("cube","pillar",stone,(x,.85,0),(.24,.85,.30)) for x in (-.82,.82)]; builder.shape("cube","lintel",stone,(0,1.75,0),(1.08,.20,.32))
        elif name=="shrine": builder.shape("cylinder","base",stone,(0,.22,0),(.65,.22,.65)); builder.shape("cube","altar",stone,(0,.72,0),(.48,.48,.36)); builder.shape("sphere","offering",glow,(0,1.30,0),(.18,.18,.18))
        elif name=="oath_gate":
            [builder.shape("cube","gate_pillar",stone,(x,1.15,0),(.34,1.15,.40)) for x in (-1.0,1.0)]; builder.shape("cube","gate_lintel",iron,(0,2.28,0),(1.35,.28,.45)); builder.shape("d12","gate_seal",glow,(0,1.25,.38),(.42,.58,.12))
        elif name.startswith("warden_"):
            builder.shape("cylinder","warden_body",iron,(0,1.0,0),(.46,1.0,.34)); builder.shape("sphere","warden_helm",stone,(0,2.05,0),(.48,.48,.42)); builder.shape("d12",name,glow,(0,1.15,.35),(.24,.34,.10))
        elif name.startswith("anchor_"):
            turn=(digest(name)[0] % 31)-15; builder.shape("cylinder","anchor_base",stone,(0,.20,0),(.66,.20,.66)); builder.shape("d12",name,glow,(0,1.10,0),(.48,.82,.34),qz(turn)); builder.shape("cylinder","anchor_ring",iron,(0,1.10,0),(.72,.06,.72),qx(90))
        elif name.startswith("armor_"):
            shape={"armor_crown":"cone","armor_cuirass":"cube","armor_gauntlet":"sphere","armor_greaves":"cylinder"}[name]; builder.shape(shape,name,iron,(0,.85,0),(.58,.78,.38)); builder.shape("d12","break_rune",glow,(0,.92,.40),(.20,.27,.08))
        else: builder.shape("cylinder","base",stone,(0,.20,0),(.62,.20,.62)); builder.shape("cube","stone",stone,(0,.92,0),(.38,.72,.26)); builder.shape("d12","rune",glow,(0,.97,.28),(.18,.30,.05))
        add_environment_animation(builder)
        path=ASSETS/"models"/"props"/f"{name}.glb"; builder.save(path); paths.append(f"res://assets/models/props/{name}.glb")
    return paths


def make_dice_model() -> str:
    builder=GlbBuilder("d12"); builder.shape("d12","d12",Material("oath_steel","#7f3438",.72,.34),(0,0,0),(.58,.58,.58))
    builder.add_animation("roll", [(0,"translation",[0.0,.25,.55,.85],[(0,0,0),(0,.42,-.2),(0,.12,-.5),(0,0,-.72)]),(0,"rotation",[0.0,.25,.55,.85],[qy(0),qz(120),qy(240),qz(0)])])
    path=ASSETS/"models"/"dice"/"d12.glb"; builder.save(path); return "res://assets/models/dice/d12.glb"


def make_vfx() -> list[str]:
    definitions={"hit":"attack","block":"defense","magic":"magic","heal":"health","burn":"ember","bleed":"blood","ward":"ward","loot":"loot"}
    paths=[]
    for name,symbol_name in definitions.items():
        symbol=UI_SYMBOLS.get(symbol_name,SYMBOLS.get(symbol_name,SYMBOLS["magic"])); color={"hit":"#d15a4e","block":"#6aa9bd","magic":"#9371c0","heal":"#79aa78","burn":"#d97644","bleed":"#b44558","ward":"#78aaa5","loot":"#d2a55a"}[name]
        body=f'<defs><radialGradient id="g"><stop stop-color="{color}" stop-opacity=".9"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient></defs><circle cx="256" cy="256" r="240" fill="url(#g)"/><g fill="#f4ead7" transform="translate(76 76) scale(.7)">{symbol}</g>'
        path=ASSETS/"vfx"/f"{name}.svg"; write_svg(path,body,kind="vfx"); paths.append(f"res://assets/vfx/{name}.svg")
    return paths


def generate() -> dict[str, Any]:
    cards_doc=read_catalog("cards"); items_doc=read_catalog("items"); enemies_doc=read_catalog("enemies")
    cards=cards_doc["cards"]; items=items_doc["items"]; enemies=enemies_doc["enemies"]
    for card in cards: write_svg(ASSETS/"cards"/f"{card['id']}.svg",card_svg(card),512,704,"card")
    for item in items:
        write_svg(ASSETS/"items"/f"{item['id']}.svg",item_svg(item),kind="item")
        item["model"]=make_item_model(item)
    for enemy in enemies:
        write_svg(ASSETS/"enemies"/f"{enemy['id']}.svg",enemy_svg(enemy),kind="enemy")
        enemy["model"]=make_enemy_model(enemy)
    for country in COUNTRY_COLORS: write_svg(ASSETS/"countries"/f"{country}.svg",country_svg(country),kind="country")
    for name in UI_SYMBOLS: write_svg(ASSETS/"ui"/f"{name}.svg",ui_svg(name),kind="ui")
    character_models=make_character_models(); country_models=make_country_models(); prop_models=make_prop_models(); dice_model=make_dice_model(); vfx=make_vfx()
    animation_profiles = {
        "version": 2,
        "clips": {
            "idle": {"loop": True, "duration": 2.8, "bob": 0.025, "sway_degrees": 2.0},
            "combat_idle": {"loop": True, "duration": 1.1},
            "walk": {"loop": True, "duration": 1.0},
            "run": {"loop": True, "duration": 0.72},
            "attack": {"loop": False, "duration": 0.36, "lunge": 0.32, "weapon_swing_degrees": 78.0},
            "heavy_attack": {"loop": False, "duration": 0.78},
            "cast": {"loop": False, "duration": 1.15},
            "guard": {"loop": False, "duration": 0.62},
            "dodge": {"loop": False, "duration": 0.62},
            "hit": {"loop": False, "duration": 0.21, "recoil": 0.18, "shake_count": 2},
            "stagger": {"loop": False, "duration": 0.72},
            "defeat": {"loop": False, "duration": 1.25, "fall_degrees": 82.0, "fade": True},
            "spawn": {"loop": False, "duration": 0.72},
            "victory": {"loop": False, "duration": 1.2},
            "loot_hover": {"loop": True, "duration": 3.2, "bob": 0.08, "rotation_degrees": 360.0},
        },
        "role_speed": {role: 0.88 + index * 0.035 for index, role in enumerate(("boss", "brute", "defender", "controller", "hexer", "elite", "beast", "marksman", "skirmisher", "assassin"))},
    }
    write_json(ASSETS/"animations"/"figure_profiles.json", animation_profiles)
    write_svg(ASSETS/"logo"/"eidpfad.svg",'<path d="M80 368 176 96h160l96 272-90-42-86 112-86-112zm176-204-48 144 48 62 48-62z" fill="#d4bd8a"/><path d="M112 410h288" stroke="#6d8f92" stroke-width="18"/>',kind="logo")
    items_doc["visual_version"]=2; enemies_doc["visual_version"]=2
    write_json(SHARED/"items.json",items_doc); write_json(SHARED/"enemies.json",enemies_doc)
    raster=[f"res://assets/backgrounds/{path.name}" for path in sorted((ASSETS/"backgrounds").glob("*.png"))]+[f"res://assets/portraits/{path.name}" for path in sorted((ASSETS/"portraits").glob("*.png"))]
    manifest={
        "version":3,
        "rendering_decisions":{
            "cards_items_ui":"2D SVG: sharp text-adjacent information and fast recognition",
            "portraits_backgrounds":"2D raster: cinematic identity and atmosphere without runtime geometry cost",
            "characters_enemies_equipment":"High-detail runtime GLB: dense procedural geometry and embedded named animation clips",
            "countries_props_dice":"3D GLB: 2.5D depth, lighting, reusable scenery and physical rolls",
            "effects":"2D SVG overlays combined with 3D lights/particles",
        },
        "required":{
            "card_icons":[card["art"] for card in cards], "item_icons":[item["art"] for item in items],
            "enemy_icons":[enemy["art"] for enemy in enemies], "item_models":[item["model"] for item in items],
            "enemy_models":[enemy["model"] for enemy in enemies], "character_models":[p.replace((ROOT/"client").as_posix()+"/","res://") for p in character_models],
            "country_icons":[f"res://assets/countries/{country}.svg" for country in COUNTRY_COLORS], "country_models":country_models,
            "prop_models":prop_models, "dice_models":[dice_model], "ui_icons":[f"res://assets/ui/{name}.svg" for name in UI_SYMBOLS],
            "vfx":vfx, "raster":raster, "logo":["res://assets/logo/eidpfad.svg"],
            "animation_profiles":["res://assets/animations/figure_profiles.json"],
            "audio":[f"res://assets/audio/{path.name}" for path in sorted((ASSETS/"audio").glob("*.wav"))],
            "voice":[f"res://assets/voice/de-DE/{path.parent.name}/{path.name}" for path in sorted((ASSETS/"voice"/"de-DE").glob("*/*.wav"))],
            "cinematic_plates":[f"res://assets/cinematics/{path.name}" for path in sorted((ASSETS/"cinematics").glob("*.png"))],
            "narrative_manifests":["res://assets/narrative/cinematics.json","res://assets/narrative/de-DE.json","res://assets/narrative/voice_manifest.de-DE.json"],
        },
    }
    manifest["counts"]={key:len(values) for key,values in manifest["required"].items()}
    write_json(ASSETS/"asset_manifest.json",manifest)
    return manifest


def main() -> None:
    manifest=generate(); total=sum(manifest["counts"].values()); models=sum(manifest["counts"][key] for key in ("item_models","enemy_models","character_models","country_models","prop_models","dice_models"))
    print(f"Generated {total} referenced visual/audio assets including {models} GLB models")


if __name__ == "__main__":
    main()
