from __future__ import annotations

"""Strict protocol payloads needed by the extended combat rules.

Kept separate from the shared REST schemas so the eventual discriminated WebSocket
union can import these models without turning every field optional.
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class _CombatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal[2] = 2


class PlayCardMessage(_CombatMessage):
    type: Literal["play_card"]
    card_id: str = Field(min_length=1)
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def normalize_legacy_target(self) -> PlayCardMessage:
        if self.target_id is not None and self.target_ids:
            raise ValueError("send target_id or target_ids, not both")
        if self.target_id is not None:
            self.target_ids = [self.target_id]
        if len(self.target_ids) != len(set(self.target_ids)):
            raise ValueError("target_ids must be unique")
        return self


class ReactionMessage(_CombatMessage):
    type: Literal["react"]
    card_id: str | None = None
    target_ids: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def pass_has_no_targets(self) -> ReactionMessage:
        if self.card_id is None and self.target_ids:
            raise ValueError("a passed reaction cannot have targets")
        if len(self.target_ids) != len(set(self.target_ids)):
            raise ValueError("target_ids must be unique")
        return self


class CooperationResponseMessage(_CombatMessage):
    type: Literal["confirm_cooperation"]
    accepted: bool


CombatClientMessage = Annotated[
    Union[PlayCardMessage, ReactionMessage, CooperationResponseMessage],
    Field(discriminator="type"),
]
COMBAT_MESSAGE_ADAPTER = TypeAdapter(CombatClientMessage)


def parse_combat_message(value: object) -> PlayCardMessage | ReactionMessage | CooperationResponseMessage:
    return COMBAT_MESSAGE_ADAPTER.validate_python(value)
