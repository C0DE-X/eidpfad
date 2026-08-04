#!/usr/bin/env python3
"""Generate deterministic cinematic backgrounds and character portraits.

The raster library is rebuilt during CI and packaging.  Keeping the source
algorithm and the curated main-menu source in Git avoids external binary
storage while retaining unique, high-resolution key art for every scene.
"""

from __future__ import annotations

import hashlib
import math
import shutil
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "client" / "assets"
MAIN_MENU_SOURCE = ROOT / "assets" / "concepts" / "main_menu_background.png"

BACKGROUND_NAMES = (
    "ash", "bone", "character_select", "coast", "crystal", "desert", "forest",
    "frost", "loot_reveal", "main_menu", "moor", "night", "rift", "storm",
    "sunken", "thorn",
)
CINEMATIC_NAMES = ("ending_crossroads", "finale", "journey", "prologue", "world_echo")
PORTRAITS = {
    "vanguard": ("#4a2f2b", "#a26f45", "axe"),
    "pathfinder": ("#293f38", "#6d8d75", "bow"),
    "duelist": ("#472d36", "#a85b68", "dual_blades"),
    "arbalist": ("#343c40", "#6d8f98", "crossbow"),
    "swordmaster": ("#353832", "#a99a72", "longsword"),
}


def rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def mix(first: tuple[int, int, int], second: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * max(0.0, min(1.0, amount))) for a, b in zip(first, second))


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        rows.extend(pixels[y * stride:(y + 1) * stride])
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def palette(name: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    data = hashlib.sha256(f"eidpfad-raster:{name}".encode()).digest()
    dark = (12 + data[0] % 22, 17 + data[1] % 26, 20 + data[2] % 24)
    sky = (55 + data[3] % 70, 58 + data[4] % 72, 61 + data[5] % 68)
    accent = (130 + data[6] % 100, 105 + data[7] % 105, 80 + data[8] % 100)
    return dark, sky, accent


def render_landscape(name: str, path: Path) -> None:
    width, height = 1280, 720
    dark, sky, accent = palette(name)
    seed = hashlib.sha256(name.encode()).digest()
    horizon = 390 + seed[0] % 90
    sun_x, sun_y = 150 + seed[1] % 980, 90 + seed[2] % 190
    stars = {
        (
            int.from_bytes(hashlib.sha256(f"{name}:star-x:{index}".encode()).digest()[:2], "big") % width,
            int.from_bytes(hashlib.sha256(f"{name}:star-y:{index}".encode()).digest()[:2], "big") % max(1, horizon - 100),
        )
        for index in range(140)
    }
    pixels = bytearray(width * height * 3)
    for y in range(height):
        vertical = y / max(1, height - 1)
        base = mix(sky, dark, vertical * .92)
        for x in range(width):
            color = base
            distance = math.hypot(x - sun_x, (y - sun_y) * 1.15)
            if distance < 70:
                color = mix(color, accent, (1.0 - distance / 70) * .82)
            ridge = horizon + 42 * math.sin(x / (72 + seed[3] % 55)) + 25 * math.sin(x / (29 + seed[4] % 31))
            far_ridge = horizon - 78 + 24 * math.sin(x / (95 + seed[5] % 70))
            if y > far_ridge:
                color = mix(color, accent, .14)
            if y > ridge:
                color = mix(dark, accent, max(0.0, (y - ridge) / height) * .22)
            if (x, y) in stars:
                color = mix(color, (236, 222, 184), .78)
            offset = (y * width + x) * 3
            pixels[offset:offset + 3] = bytes(color)
    write_png(path, width, height, bytes(pixels))


def render_portrait(name: str, path: Path, primary_hex: str, accent_hex: str, weapon: str) -> None:
    width, height = 512, 704
    primary, accent = rgb(primary_hex), rgb(accent_hex)
    dark = (13, 18, 20)
    seed = int.from_bytes(hashlib.sha256(f"portrait:{name}".encode()).digest()[:4], "big")
    pixels = bytearray(width * height * 3)

    def grain(x: int, y: int) -> int:
        value = (x * 374_761_393 + y * 668_265_263 + seed * 982_451_653) & 0xFFFFFFFF
        value = ((value ^ (value >> 13)) * 1_274_126_177) & 0xFFFFFFFF
        return (value ^ (value >> 16)) & 255

    for y in range(height):
        for x in range(width):
            vignette = min(1.0, math.hypot((x - 256) / 330, (y - 330) / 500))
            color = mix(mix(primary, dark, y / height * .72), dark, vignette * .44)
            light = max(0.0, 1.0 - math.hypot((x - 170) / 360, (y - 130) / 460))
            color = mix(color, accent, light * .17)
            texture = (grain(x, y) - 128) / 255
            color = tuple(max(0, min(255, round(channel + texture * 18))) for channel in color)

            head = ((x - 256) / 92) ** 2 + ((y - 205) / 112) ** 2 <= 1
            torso_width = 70 + max(0, y - 320) * .38
            torso = y >= 300 and abs(x - 256) <= torso_width
            if torso:
                panel = .13 if ((x - 256) // 34) % 2 else .28
                color = mix(primary, accent, panel + max(0, 1 - abs(x - 224) / 260) * .12)
                if abs(x - 256) < 5 or abs(abs(x - 256) - torso_width + 8) < 4:
                    color = mix(color, (220, 202, 160), .38)
                if 420 < y < 434 or 548 < y < 562:
                    color = mix(color, dark, .38)
            if head:
                face_light = max(0.0, min(1.0, (330 - x) / 150))
                color = mix((117, 86, 70), (205, 166, 125), face_light)
                color = mix(color, accent, .10)
                if y < 166 + abs(x - 256) * .18:
                    color = mix(dark, primary, .48)
                if 188 < y < 208 and 198 < x < 314:
                    color = mix(dark, accent, .08)
                if 244 < y < 250 and 229 < x < 287:
                    color = mix(color, dark, .45)
            if 184 < y < 202 and (215 < x < 237 or 276 < x < 298):
                color = mix((220, 214, 178), accent, .28)

            steel = mix((198, 207, 204), accent, .24)
            if weapon in {"axe", "longsword"}:
                blade_x = 175 + round((y - 110) * (.13 if weapon == "axe" else .09))
                if 90 < y < 650 and abs(x - blade_x) < (6 if weapon == "axe" else 5):
                    color = steel
                if weapon == "axe" and 104 < y < 196 and blade_x - 42 < x < blade_x + 10:
                    color = mix(steel, (238, 226, 190), .22)
                if weapon == "longsword" and 500 < y < 514 and blade_x - 38 < x < blade_x + 39:
                    color = mix((126, 88, 55), accent, .30)
            elif weapon == "bow":
                curve_x = 350 + round(58 * math.sin((y - 105) / 510 * math.pi))
                if 105 < y < 615 and abs(x - curve_x) < 4:
                    color = mix((121, 77, 44), accent, .35)
                if 105 < y < 615 and abs(x - 350) < 2:
                    color = (206, 194, 157)
            elif weapon == "crossbow":
                if 370 < y < 382 and 305 < x < 472 or 300 < x < 312 and 330 < y < 590:
                    color = mix((121, 77, 44), accent, .42)
                if abs(y - (356 + abs(x - 388) * .18)) < 3 and 310 < x < 468:
                    color = steel
            else:
                for offset, slope in ((-78, .18), (72, -.18)):
                    blade_x = 256 + offset + round((y - 260) * slope)
                    if 180 < y < 630 and abs(x - blade_x) < 5:
                        color = steel

            emblem = (x - 256) ** 2 + (y - 390) ** 2
            if torso and 24 ** 2 < emblem < 31 ** 2:
                color = mix(accent, (236, 220, 178), .52)
            if y > 590 and abs(x - 256) < 206:
                color = mix(color, accent, .12)
            offset = (y * width + x) * 3
            pixels[offset:offset + 3] = bytes(color)
    write_png(path, width, height, bytes(pixels))


def main() -> None:
    for name in BACKGROUND_NAMES:
        destination = ASSETS / "backgrounds" / f"{name}.png"
        if name == "main_menu":
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(MAIN_MENU_SOURCE, destination)
        else:
            render_landscape(name, destination)
    for name in CINEMATIC_NAMES:
        render_landscape(f"cinematic-{name}", ASSETS / "cinematics" / f"{name}.png")
    for name, (primary, accent, weapon) in PORTRAITS.items():
        render_portrait(name, ASSETS / "portraits" / f"{name}.png", primary, accent, weapon)
    print(f"Generated {len(BACKGROUND_NAMES)} backgrounds, {len(CINEMATIC_NAMES)} cinematic plates and {len(PORTRAITS)} portraits")


if __name__ == "__main__":
    main()
