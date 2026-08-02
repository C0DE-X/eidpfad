#!/usr/bin/env python3
"""Fail fast when game content, generated worlds or client assets drift."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import wave
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.content import CardCatalog, EnemyCatalog, ItemCatalog, PHASES, RARITIES  # noqa: E402
from app.world_generator import CAMPAIGN_COUNTRY_COUNTS, generate_world  # noqa: E402


class ValidationFailure(AssertionError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def local_asset(resource_path: str) -> Path:
    require(resource_path.startswith("res://"), f"Not a Godot resource path: {resource_path}")
    return ROOT / "client" / resource_path.removeprefix("res://")


def validate_svg(path: Path) -> None:
    require(path.exists() and path.stat().st_size > 300, f"Missing or empty SVG: {path}")
    root = ET.parse(path).getroot()
    require(root.tag.endswith("svg"), f"Invalid SVG root: {path}")
    require(root.get("data-asset-kind") is not None, f"SVG lacks semantic asset kind: {path}")


def glb_document(path: Path) -> dict[str, Any]:
    require(path.exists() and path.stat().st_size > 1_000, f"Missing or empty GLB: {path}")
    payload = path.read_bytes()
    require(len(payload) >= 28, f"Truncated GLB: {path}")
    magic, version, total_length = struct.unpack_from("<4sII", payload, 0)
    require(magic == b"glTF" and version == 2 and total_length == len(payload), f"Invalid GLB header: {path}")
    json_length, chunk_type = struct.unpack_from("<I4s", payload, 12)
    require(chunk_type == b"JSON" and 20 + json_length <= len(payload), f"Invalid GLB JSON chunk: {path}")
    try:
        document = json.loads(payload[20:20 + json_length].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationFailure(f"Invalid GLB JSON in {path}: {exc}") from exc
    binary_offset = 20 + json_length
    require(binary_offset + 8 <= len(payload), f"Missing GLB binary chunk: {path}")
    binary_length, binary_type = struct.unpack_from("<I4s", payload, binary_offset)
    require(binary_type == b"BIN\0" and binary_offset + 8 + binary_length == len(payload), f"Invalid GLB binary chunk: {path}")
    require(document.get("asset", {}).get("version") == "2.0", f"Unsupported GLB version: {path}")
    require(document.get("scenes") and document.get("nodes") and document.get("meshes"), f"GLB has no renderable scene: {path}")
    require(document.get("materials") and document.get("accessors") and document.get("bufferViews"), f"GLB misses materials or geometry: {path}")
    require(document.get("buffers", [{}])[0].get("byteLength", 0) <= binary_length, f"GLB buffer length mismatch: {path}")
    return document


def rendered_triangles(document: dict[str, Any]) -> int:
    mesh_triangles = [
        sum(int(document["accessors"][primitive["indices"]]["count"]) // 3 for primitive in mesh["primitives"])
        for mesh in document["meshes"]
    ]
    return sum(mesh_triangles[int(node["mesh"])] for node in document["nodes"] if "mesh" in node)


def png_size(path: Path) -> tuple[int, int]:
    require(path.exists() and path.stat().st_size > 10_000, f"Missing or empty PNG: {path}")
    with path.open("rb") as handle:
        require(handle.read(8) == b"\x89PNG\r\n\x1a\n", f"Invalid PNG signature: {path}")
        length = struct.unpack(">I", handle.read(4))[0]
        require(handle.read(4) == b"IHDR" and length == 13, f"Invalid PNG header: {path}")
        return struct.unpack(">II", handle.read(8))


def distribution(entries: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(entry.get(key, "none")) for entry in entries).items()))


def validate(report_path: Path | None) -> dict[str, Any]:
    cards = CardCatalog()
    items = ItemCatalog()
    enemies = EnemyCatalog()
    card_entries = list(cards.cards.values())
    item_entries = list(items.items.values())
    enemy_entries = list(enemies.enemies.values())

    require(len(card_entries) >= 120, "At least 120 cards are required")
    require(len(item_entries) >= 120, "At least 120 items are required")
    require(len(enemy_entries) >= 10 * len(enemies._by_country), "Every country needs ten enemies")
    require(len({entry["name"] for entry in card_entries}) == len(card_entries), "Card names must be unique")
    require(len({entry["name"] for entry in item_entries}) == len(item_entries), "Item names must be unique")

    for entry in card_entries + item_entries + enemy_entries:
        validate_svg(local_asset(entry["art"]))
    for entry in item_entries + enemy_entries:
        model = glb_document(local_asset(entry["model"]))
        require(model.get("animations"), f"Gameplay model lacks embedded animation: {entry['model']}")
    require(len({entry["art"] for entry in card_entries + item_entries + enemy_entries}) == len(card_entries + item_entries + enemy_entries), "Every catalog entry needs unique 2D art")
    require(len({entry["model"] for entry in item_entries + enemy_entries}) == len(item_entries + enemy_entries), "Every item and enemy needs a unique 3D model")

    for weapon in ("dual_blades", "axe", "bow", "crossbow"):
        for magic in ("rune", "ember", "veil", "blood"):
            deck = cards.starter_deck(weapon, magic)
            require(len(deck) == 18, f"Starter deck {weapon}/{magic} needs 18 cards")
            require({cards.get(card_id)["phase"] for card_id in deck} == set(PHASES), f"Starter deck {weapon}/{magic} misses a phase")

    body_families = {"humanoid", "quadruped", "serpent", "arthropod", "harpy", "spirit", "swarm", "giant"}
    for enemy in enemy_entries:
        require(enemy.get("body_family") in body_families, f"Enemy {enemy['id']} has no semantic body family")
        require(enemy.get("rig_id") and enemy.get("animation_set") and enemy.get("voice_profile"), f"Enemy {enemy['id']} lacks presentation metadata")
    require(len({enemy["voice_profile"] for enemy in enemy_entries if enemy["boss"]}) == 14, "Every boss needs an individual voice profile")

    worlds: dict[str, Any] = {}
    backgrounds: set[str] = set()
    world_models: set[str] = set()
    for length, country_count in CAMPAIGN_COUNTRY_COUNTS.items():
        world = generate_world(20260801, length, 3, enemies)
        require(world == generate_world(20260801, length, 3, enemies), f"{length} is not deterministic")
        require(len(world["countries"]) == country_count and len(world["route"]) == country_count * 3, f"{length} size mismatch")
        require(world["route"][-1]["is_final"], f"{length} does not end at the final boss")
        used_by_country: dict[str, list[str]] = {}
        for scenario in world["route"]:
            encounter_ids = scenario["encounters"]
            require(2 <= len(encounter_ids) <= 3, f"{scenario['id']} needs two or three encounters")
            require(len(encounter_ids) == len(set(encounter_ids)), f"{scenario['id']} repeats an enemy")
            require(all(enemies.get(enemy_id)["country_id"] == scenario["country_id"] for enemy_id in encounter_ids), f"{scenario['id']} has a foreign enemy")
            used_by_country.setdefault(scenario["country_id"], []).extend(encounter_ids)
            backgrounds.add(scenario["background"])
            world_models.add(scenario["landmark_model"])
            require(len(scenario["prop_models"]) == 2, f"{scenario['id']} needs two scene props")
            world_models.update(scenario["prop_models"])
        for country, used in used_by_country.items():
            require(len(used) == len(set(used)), f"World route repeats an enemy inside {country}")
        worlds[length] = {"countries": len(world["countries"]), "scenarios": len(world["route"]), "encounters": sum(len(s["encounters"]) for s in world["route"])}

    for path in backgrounds | {
        "res://assets/backgrounds/main_menu.png",
        "res://assets/backgrounds/character_select.png",
        "res://assets/backgrounds/loot_reveal.png",
    }:
        width, height = png_size(local_asset(path))
        require(width / height > 1.6, f"Background is not landscape: {path}")
    for name in ("vanguard", "pathfinder", "duelist", "arbalist"):
        width, height = png_size(ROOT / "client" / "assets" / "portraits" / f"{name}.png")
        require(height > width, f"Portrait is not vertical: {name}")

    manifest_path = ROOT / "client" / "assets" / "asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("version", 0) >= 2, "Asset manifest is outdated")
    required_assets = manifest.get("required", {})
    require(required_assets and manifest.get("rendering_decisions"), "Asset manifest lacks required classes or rendering decisions")
    manifest_paths: set[str] = set()
    for category, paths in required_assets.items():
        require(isinstance(paths, list) and paths, f"Manifest category {category} is empty")
        require(len(paths) == len(set(paths)), f"Manifest category {category} contains duplicates")
        require(manifest.get("counts", {}).get(category) == len(paths), f"Manifest count mismatch for {category}")
        for resource_path in paths:
            asset_path = local_asset(resource_path)
            require(asset_path.is_file(), f"Manifest references missing asset: {resource_path}")
            manifest_paths.add(resource_path)
    figure_clips = {"idle","combat_idle","walk","run","attack","heavy_attack","cast","guard","dodge","hit","stagger","defeat","spawn","victory"}
    for model_path in required_assets["character_models"] + required_assets["enemy_models"]:
        document = glb_document(local_asset(model_path))
        clips = {animation.get("name") for animation in document.get("animations", [])}
        require(figure_clips <= clips, f"Figure model misses animation clips: {model_path}")
        require(rendered_triangles(document) >= 4_000, f"Figure model is below the high-detail runtime budget: {model_path}")
        require(document.get("skins") and len(document["skins"][0].get("joints", [])) >= 7, f"Figure model has no semantic skeleton/skin: {model_path}")
        require(document.get("images") and document.get("textures"), f"Figure model has no embedded PBR texture: {model_path}")
        require("MSFT_lod" in document.get("extensionsUsed", []), f"Figure model has no runtime LOD: {model_path}")
        joint_nodes = set(document["skins"][0]["joints"])
        require(any(channel.get("target", {}).get("node") in joint_nodes for animation in document["animations"] for channel in animation.get("channels", [])), f"Figure clips do not animate skeleton joints: {model_path}")
    for model_path in required_assets["item_models"]:
        clips = {animation.get("name") for animation in glb_document(local_asset(model_path)).get("animations", [])}
        require({"loot_hover", "reveal"} <= clips, f"Loot model misses reveal animations: {model_path}")
    for model_path in required_assets["country_models"] + required_assets["prop_models"]:
        clips = {animation.get("name") for animation in glb_document(local_asset(model_path)).get("animations", [])}
        require("ambient" in clips, f"Environment model lacks ambient animation: {model_path}")
    dice_clips = {animation.get("name") for animation in glb_document(local_asset(required_assets["dice_models"][0])).get("animations", [])}
    require("roll" in dice_clips, "D12 model lacks roll animation")
    animation_profile = json.loads(local_asset(required_assets["animation_profiles"][0]).read_text(encoding="utf-8"))
    require(
        figure_clips | {"loot_hover"} <= set(animation_profile.get("clips", {})),
        "Animation profile does not cover all gameplay states",
    )
    require(world_models <= set(required_assets["country_models"] + required_assets["prop_models"]), "Generated worlds reference models outside the manifest")

    generated_svgs = list((ROOT / "client" / "assets").rglob("*.svg"))
    generated_pngs = list((ROOT / "client" / "assets").rglob("*.png"))
    generated_glbs = list((ROOT / "client" / "assets" / "models").rglob("*.glb"))
    generated_wavs = list((ROOT / "client" / "assets" / "audio").glob("*.wav"))
    require(len(generated_glbs) >= 299, "The complete 3D gameplay library needs at least 299 models")
    actual_glb_resources = {"res://" + str(path.relative_to(ROOT / "client")) for path in generated_glbs}
    manifest_glbs = {path for paths in required_assets.values() for path in paths if path.endswith(".glb")}
    require(actual_glb_resources == manifest_glbs, "GLB library contains missing or orphaned files")
    require(len(generated_wavs) >= 29, "Core cues, regional ambience and six music beds are required")
    require(len(list((ROOT / "client" / "assets" / "audio").glob("ambience_*.wav"))) >= 13, "Every biome needs ambience")
    require(len(list((ROOT / "client" / "assets" / "audio").glob("music_*.wav"))) >= 6, "Six dynamic music beds are required")
    for path in generated_wavs:
        with wave.open(str(path), "rb") as source:
            expected_channels = 2 if path.name.startswith(("music_", "ambience_")) else 1
            require(source.getnchannels() == expected_channels and source.getframerate() == 44_100 and source.getnframes() > 4_000, f"Invalid audio cue: {path}")

    voice_manifest = json.loads((ROOT / "shared" / "narrative" / "voice_manifest.de-DE.json").read_text(encoding="utf-8"))
    voice_lines = voice_manifest.get("lines", [])
    require(len(voice_lines) == 336 and len({line["id"] for line in voice_lines}) == 336, "German voice manifest must contain 336 unique lines")
    voice_paths: set[str] = set()
    for line in voice_lines:
        path = local_asset(line["asset"])
        require(path.is_file() and int(line.get("duration_ms", 0)) > 250, f"Voice line is missing or has no duration: {line['id']}")
        with wave.open(str(path), "rb") as source:
            duration_ms = round(source.getnframes() / source.getframerate() * 1000)
            require(source.getnchannels() == 1 and source.getframerate() == 22_050, f"Invalid voice format: {path}")
            require(abs(duration_ms - int(line["duration_ms"])) <= 30, f"Voice duration mismatch: {line['id']}")
        voice_paths.add(line["asset"])
    require(voice_paths == set(required_assets["voice"]), "Voice manifest and asset manifest drift")

    cinematic_doc = json.loads((ROOT / "shared" / "narrative" / "cinematics.json").read_text(encoding="utf-8"))
    cinematics = cinematic_doc.get("cinematics", [])
    require(len(cinematics) == 48 and len({entry["id"] for entry in cinematics}) == 48, "Exactly 48 cinematic definitions are required")
    line_ids = {line["id"] for line in voice_lines}
    for cinematic in cinematics:
        require(cinematic.get("shots") and set(cinematic.get("required_lines", [])) <= line_ids, f"Cinematic is incomplete: {cinematic.get('id')}")
        for shot in cinematic["shots"]:
            plate = str(shot.get("plate", ""))
            if plate.startswith("res://"):
                require(local_asset(plate).is_file(), f"Cinematic plate is missing: {plate}")

    runtime_contracts = {
        ROOT / "client" / "scripts" / "main.gd": ("_drain_presentation_queue", "_present_event", "_add_equipment_menu", "_show_gameplay", "CinematicPlayer", "VoiceDirector"),
        ROOT / "client" / "scripts" / "world_diorama_3d.gd": ("_play_clip", "FIGURE_PROFILE_PATH", "_apply_team_variant", "enemy_spawned", "boss_phase_changed", "CHARACTER_MODELS"),
        ROOT / "client" / "scripts" / "cinematic_player.gd": ("play_authoritative", "LOCALE_PATH", "_play_line", "ÜBERSPRINGEN", "Voice"),
        ROOT / "client" / "scripts" / "voice_director.gd": ("play_event", "enemy_", "bark_", "Voice"),
        ROOT / "client" / "scripts" / "audio_bus.gd": ("set_voice_active", "Music", "Ambience", "SFX"),
    }
    for path, markers in runtime_contracts.items():
        source = path.read_text(encoding="utf-8")
        require(all(marker in source for marker in markers), f"Runtime integration is incomplete: {path.name}")
    migration_contracts = {
        ROOT / "server" / "alembic.ini": ("script_location", "migrations"),
        ROOT / "server" / "app" / "migrate.py": ("command.upgrade", "command.stamp", "Base.metadata.create_all"),
        ROOT / "server" / "migrations" / "versions" / "0001_initial_schema.py": ("profiles", "campaigns", "campaign_members", "profile_recovery"),
        ROOT / "server" / "entrypoint.sh": ("app.migrate", "app"),
    }
    for path, markers in migration_contracts.items():
        require(path.is_file(), f"Migration file is missing: {path}")
        source = path.read_text(encoding="utf-8")
        require(all(marker in source for marker in markers), f"Migration integration is incomplete: {path.name}")
    project_settings = (ROOT / "client" / "project.godot").read_text(encoding="utf-8")
    require('renderer/rendering_method="forward_plus"' in project_settings, "Windows client must use the high-quality Forward+ renderer")
    raster_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in generated_pngs]
    require(len(raster_hashes) == len(set(raster_hashes)), "Raster library contains duplicate images")
    report = {
        "content_versions": {"cards": cards.content_version, "items": items.content_version, "enemies": enemies.content_version},
        "counts": {"cards": len(card_entries), "items": len(item_entries), "enemies": len(enemy_entries), "cinematics": len(cinematics), "voice_lines": len(voice_lines), "svg_assets": len(generated_svgs), "png_assets": len(generated_pngs), "glb_assets": len(generated_glbs), "audio_assets": len(generated_wavs), "manifest_references": len(manifest_paths)},
        "cards_by_phase": distribution(card_entries, "phase"),
        "cards_by_rarity": distribution(card_entries, "rarity"),
        "items_by_slot": distribution(item_entries, "slot"),
        "items_by_rarity": distribution(item_entries, "rarity"),
        "enemies_by_role": distribution(enemy_entries, "role"),
        "enemies_per_country": {country: len(entries) for country, entries in sorted(enemies._by_country.items())},
        "worlds": worlds,
        "asset_manifest": manifest["counts"],
        "rendering_decisions": manifest["rendering_decisions"],
        "status": "complete",
    }
    require(set(report["cards_by_rarity"]) == set(RARITIES), "Cards must cover all six rarities")
    require(set(report["items_by_rarity"]) == set(RARITIES), "Items must cover all six rarities")
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.report)
    print(json.dumps(report["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
