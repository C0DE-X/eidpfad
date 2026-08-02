from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .errors import ContentViolation, RuleViolation


CONTENT_ROOT = Path(__file__).resolve().parents[2] / "shared"
PHASES = ("attack", "defense", "magic", "utility")
RARITIES = ("normal", "rare", "enhanced", "exceptional", "legendary", "unique")
RARITY_RANK = {rarity: index for index, rarity in enumerate(RARITIES)}
SUPPORTED_EFFECTS = {
    "add_block_dice_all", "add_block_dice_ally", "add_block_dice_self", "apply_weapon_coating",
    "armor_break", "cleanse", "dice_attack", "dice_magic_damage", "draw_cards", "enemy_status",
    "exhaust", "gain_action_points", "guard_self", "heal_all", "heal_ally", "heal_self",
    "regeneration", "self_damage", "self_status", "set_trap", "team_status",
}
SUPPORTED_BONUSES = {
    "attack_dice", "block_break", "block_dice", "block_threshold", "critical_min", "damage_per_hit",
    "healing", "hit_threshold_modifier", "last_oath", "magic_dice", "ward_dice",
}


def _load_entries(path: Path, collection_key: str) -> tuple[int, list[dict[str, Any]]]:
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentViolation(f"Cannot load {path}: {exc}") from exc
    entries = content.get(collection_key)
    if not isinstance(entries, list):
        raise ContentViolation(f"{path.name}: '{collection_key}' must be an array")
    identifiers = [entry.get("id") for entry in entries if isinstance(entry, dict)]
    if len(identifiers) != len(entries) or len(set(identifiers)) != len(identifiers):
        raise ContentViolation(f"{path.name}: every entry needs a unique id")
    return int(content.get("content_version", 0)), entries


class CardCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.content_version, entries = _load_entries(path or CONTENT_ROOT / "cards.json", "cards")
        self.cards = {entry["id"]: entry for entry in entries}
        self._validate()

    def get(self, card_id: str) -> dict[str, Any]:
        try:
            return self.cards[card_id]
        except KeyError as exc:
            raise RuleViolation(f"Unknown card: {card_id}") from exc

    def starter_deck(self, weapon: str, magic: str, size: int = 18) -> list[str]:
        eligible = [
            card for card in self.cards.values()
            if card["school"] in {weapon, magic, "universal"} and card.get("starter", False)
        ]
        deck: list[str] = []
        for phase in PHASES:
            candidates = sorted(
                (card for card in eligible if card["phase"] == phase),
                key=lambda card: (card.get("unlock_level", 1), RARITY_RANK[card["rarity"]]),
            )
            if not candidates:
                raise RuleViolation(f"The selected loadout has no {phase} cards")
            deck.extend(card["id"] for card in candidates[:3])
        remaining = sorted(
            (card for card in eligible if card["id"] not in deck),
            key=lambda card: (card.get("unlock_level", 1), card["id"]),
        )
        deck.extend(card["id"] for card in remaining[: max(0, size - len(deck))])
        while len(deck) < size:
            deck.append(deck[len(deck) % max(1, len(deck))])
        return deck[:size]

    def _validate(self) -> None:
        required = {"id", "name", "kind", "school", "phase", "action_point_cost", "rarity", "effects", "art"}
        for card in self.cards.values():
            missing = required - card.keys()
            if missing:
                raise ContentViolation(f"Card {card.get('id', '?')} misses {sorted(missing)}")
            if card["phase"] not in PHASES or card["rarity"] not in RARITY_RANK:
                raise ContentViolation(f"Card {card['id']} has an invalid phase or rarity")
            if not 0 <= int(card["action_point_cost"]) <= 5 or not card["effects"]:
                raise ContentViolation(f"Card {card['id']} has invalid costs or no effects")
            unknown = {effect.get("type") for effect in card["effects"]} - SUPPORTED_EFFECTS
            if unknown:
                raise ContentViolation(f"Card {card['id']} uses unsupported effects: {sorted(unknown)}")


class ItemCatalog:
    STARTING_WEAPONS = {
        "dual_blades": "worn_dual_blades", "axe": "worn_axe", "bow": "worn_bow", "crossbow": "worn_crossbow",
    }

    def __init__(self, path: Path | None = None) -> None:
        self.content_version, entries = _load_entries(path or CONTENT_ROOT / "items.json", "items")
        self.items = {entry["id"]: entry for entry in entries}
        self._validate()

    def get(self, item_id: str) -> dict[str, Any]:
        try:
            return self.items[item_id]
        except KeyError as exc:
            raise RuleViolation(f"Unknown item: {item_id}") from exc

    def candidates(self, minimum_rarity: str = "normal") -> Iterable[dict[str, Any]]:
        minimum = RARITY_RANK[minimum_rarity]
        return (item for item in self.items.values() if RARITY_RANK[item["rarity"]] >= minimum)

    def _validate(self) -> None:
        required = {"id", "name", "slot", "rarity", "bonuses", "art", "model"}
        for item in self.items.values():
            if required - item.keys() or item["rarity"] not in RARITY_RANK:
                raise ContentViolation(f"Item {item.get('id', '?')} is malformed")
            unknown = set(item["bonuses"]) - SUPPORTED_BONUSES
            if unknown:
                raise ContentViolation(f"Item {item['id']} uses unsupported bonuses: {sorted(unknown)}")
        required_starters = set(self.STARTING_WEAPONS.values()) | {"travel_leathers"}
        if missing := required_starters - self.items.keys():
            raise ContentViolation(f"Missing starter items: {sorted(missing)}")


class EnemyCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.content_version, entries = _load_entries(path or CONTENT_ROOT / "enemies.json", "enemies")
        self.enemies = {entry["id"]: entry for entry in entries}
        self._by_country: dict[str, list[dict[str, Any]]] = {}
        for enemy in entries:
            self._by_country.setdefault(enemy["country_id"], []).append(enemy)
        self._validate()

    def get(self, enemy_id: str) -> dict[str, Any]:
        try:
            return self.enemies[enemy_id]
        except KeyError as exc:
            raise RuleViolation(f"Unknown enemy: {enemy_id}") from exc

    def for_country(self, country_id: str, *, bosses: bool | None = None) -> list[dict[str, Any]]:
        entries = list(self._by_country.get(country_id, ()))
        if bosses is not None:
            entries = [entry for entry in entries if bool(entry["boss"]) is bosses]
        return entries

    def _validate(self) -> None:
        required = {"id", "name", "country_id", "role", "boss", "stats", "traits", "intents", "art", "model"}
        required_stats = {"hp", "armor", "block_dice", "block_threshold", "ward_dice", "ward_threshold", "attack_dice", "hit_threshold", "damage_per_hit"}
        for enemy in self.enemies.values():
            if required - enemy.keys() or required_stats - enemy["stats"].keys():
                raise ContentViolation(f"Enemy {enemy.get('id', '?')} is malformed")
        for country, enemies in self._by_country.items():
            if len(enemies) < 10 or not any(enemy["boss"] for enemy in enemies):
                raise ContentViolation(f"Country {country} needs at least ten enemies and a boss")


class ContentBundle:
    def __init__(self) -> None:
        self.cards = CardCatalog()
        self.items = ItemCatalog()
        self.enemies = EnemyCatalog()
