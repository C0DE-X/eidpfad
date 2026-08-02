import unittest

from app.game_state import PlayerState
from app.weather_rules import WEATHER_PROFILES, WeatherRules
from app.world_generator import WEATHER


class WeatherRulesTests(unittest.TestCase):
    def test_every_generated_weather_has_a_visible_mechanical_profile(self) -> None:
        generated = {value for values in WEATHER.values() for value in values}
        self.assertEqual(generated, set(WEATHER_PROFILES))
        for weather, profile in WEATHER_PROFILES.items():
            self.assertTrue(profile.get("text"), weather)
            self.assertTrue(any(key in profile for key in {"hit", "magic", "ward", "ranged", "enemy", "rune", "ember", "veil", "blood"}), weather)

    def test_modifiers_are_bounded_and_loadout_sensitive(self) -> None:
        archer = PlayerState("p1", "bow", "ember")
        self.assertEqual(WeatherRules.player_dice("Nebel", "hit", archer), -1)
        self.assertEqual(WeatherRules.player_dice("Ascheregen", "magic", archer), 1)
        self.assertLessEqual(abs(WeatherRules.enemy_dice("Zeitsturm")), 2)


if __name__ == "__main__":
    unittest.main()
