"""Complete, data-driven mechanics for every generated weather value."""

from __future__ import annotations

from typing import Any


# A modifier is intentionally small: weather changes tactical choices without deciding
# an encounter by itself. `purpose` is hit, magic or ward; filters are optional.
WEATHER_PROFILES: dict[str, dict[str, Any]] = {
    "Nebel": {"ranged": -1, "enemy": -1, "text": "Fernkampf und Gegnerangriffe verlieren 1 W12."},
    "Säureregen": {"hit": 1, "enemy": 1, "text": "Rüstung wird spröde: Angriffe und Gegner erhalten 1 W12."},
    "Sandsturm": {"ranged": -1, "enemy": 1, "text": "Fernkampf −1 W12, Gegnerangriffe +1 W12."},
    "Flimmerhitze": {"magic": -1, "hit": 1, "text": "Magie −1 W12, Nahkampfangriffe +1 W12."},
    "Schneefall": {"hit": -1, "ward": 1, "text": "Angriffe −1 W12, Bannwürfe +1 W12."},
    "Eiswind": {"enemy": 1, "magic": 1, "text": "Gegnerangriffe und Magie erhalten 1 W12."},
    "Sturmflut": {"enemy": 1, "ward": 1, "text": "Gegnerangriffe und Bannwürfe erhalten 1 W12."},
    "Salznebel": {"ranged": -1, "magic": 1, "text": "Fernkampf −1 W12, Magie +1 W12."},
    "Ascheregen": {"ranged": -1, "ember": 1, "text": "Fernkampf −1 W12, Glutmagie +1 W12."},
    "Glutwind": {"enemy": 1, "ember": 1, "text": "Gegnerangriffe und Glutmagie erhalten 1 W12."},
    "Rankenwuchs": {"hit": -1, "rune": 1, "text": "Angriffe −1 W12, Runenmagie +1 W12."},
    "Giftpollen": {"ward": 1, "enemy": 1, "text": "Bann- und Gegnerwürfe erhalten 1 W12."},
    "Prismenlicht": {"magic": 1, "enemy": -1, "text": "Magie +1 W12, Gegnerangriffe −1 W12."},
    "Scherbenwind": {"hit": 1, "ward": -1, "text": "Angriffe +1 W12, Bannwürfe −1 W12."},
    "Dämmerregen": {"veil": 1, "enemy": -1, "text": "Schleiermagie +1 W12, Gegnerangriffe −1 W12."},
    "Wurzelbeben": {"hit": -1, "magic": 1, "text": "Angriffe −1 W12, Magie +1 W12."},
    "Bleicher Wind": {"blood": 1, "ward": -1, "text": "Blutmagie +1 W12, Bannwürfe −1 W12."},
    "Seelenfrost": {"ward": 1, "magic": -1, "text": "Bannwürfe +1 W12, Magie −1 W12."},
    "Mondfinsternis": {"veil": 1, "enemy": 1, "text": "Schleiermagie und Gegnerangriffe erhalten 1 W12."},
    "Sternenfall": {"magic": 1, "hit": 1, "text": "Angriffs- und Magiewürfe erhalten 1 W12."},
    "Gewitter": {"ranged": -1, "enemy": 1, "text": "Fernkampf −1 W12, Gegnerangriffe +1 W12."},
    "Orkan": {"ranged": -1, "hit": -1, "enemy": -1, "text": "Alle physischen Angriffe verlieren 1 W12."},
    "Schwarze Flut": {"blood": 1, "enemy": 1, "text": "Blutmagie und Gegnerangriffe erhalten 1 W12."},
    "Glockennebel": {"rune": 1, "enemy": -1, "text": "Runenmagie +1 W12, Gegnerangriffe −1 W12."},
    "Nahtbruch": {"magic": 1, "ward": 1, "text": "Magie- und Bannwürfe erhalten 1 W12."},
    "Zeitsturm": {"hit": 1, "magic": -1, "enemy": 1, "text": "Angriffe +1, Magie −1 und Gegner +1 W12."},
}


class WeatherRules:
    @staticmethod
    def player_dice(weather: str, purpose: str, player: Any) -> int:
        profile = WEATHER_PROFILES.get(weather, {})
        result = int(profile.get(purpose, 0))
        if purpose == "hit" and player.weapon in {"bow", "crossbow"}:
            result += int(profile.get("ranged", 0))
        if purpose == "magic":
            result += int(profile.get(player.magic, 0))
        return max(-2, min(2, result))

    @staticmethod
    def enemy_dice(weather: str) -> int:
        return int(WEATHER_PROFILES.get(weather, {}).get("enemy", 0))

    @staticmethod
    def client_view(weather: str) -> dict[str, Any]:
        profile = WEATHER_PROFILES.get(weather)
        return {"weather": weather, **profile} if profile else {"weather": weather, "text": ""}
