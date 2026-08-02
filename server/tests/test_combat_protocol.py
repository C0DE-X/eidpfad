import unittest

from pydantic import ValidationError

from app.combat_protocol import CooperationResponseMessage, PlayCardMessage, ReactionMessage, parse_combat_message


class CombatProtocolTests(unittest.TestCase):
    def test_play_card_accepts_legacy_single_target_and_normalizes_it(self) -> None:
        message = parse_combat_message(
            {"type": "play_card", "protocol_version": 2, "card_id": "kreuzschnitt", "target_id": "enemy:a"}
        )
        self.assertIsInstance(message, PlayCardMessage)
        self.assertEqual(message.target_ids, ["enemy:a"])

    def test_play_card_supports_up_to_three_unique_targets(self) -> None:
        message = parse_combat_message(
            {
                "type": "play_card",
                "protocol_version": 2,
                "card_id": "pfeilregen",
                "target_ids": ["enemy:a", "enemy:b", "enemy:c"],
            }
        )
        self.assertEqual(message.target_ids, ["enemy:a", "enemy:b", "enemy:c"])
        with self.assertRaises(ValidationError):
            parse_combat_message(
                {"type": "play_card", "protocol_version": 2, "card_id": "pfeilregen", "target_ids": ["x", "x"]}
            )

    def test_reaction_pass_and_card_are_distinct_valid_messages(self) -> None:
        passed = parse_combat_message({"type": "react", "protocol_version": 2, "card_id": None})
        played = parse_combat_message(
            {"type": "react", "protocol_version": 2, "card_id": "wachposten", "target_ids": []}
        )
        self.assertIsInstance(passed, ReactionMessage)
        self.assertIsInstance(played, ReactionMessage)
        with self.assertRaises(ValidationError):
            parse_combat_message(
                {"type": "react", "protocol_version": 2, "card_id": None, "target_ids": ["p1"]}
            )

    def test_cooperation_confirmation_requires_explicit_boolean(self) -> None:
        message = parse_combat_message(
            {"type": "confirm_cooperation", "protocol_version": 2, "accepted": True}
        )
        self.assertIsInstance(message, CooperationResponseMessage)
        with self.assertRaises(ValidationError):
            parse_combat_message({"type": "confirm_cooperation", "protocol_version": 2})

    def test_unknown_and_extra_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            parse_combat_message({"type": "react", "protocol_version": 2, "card_id": None, "ready": True})


if __name__ == "__main__":
    unittest.main()
