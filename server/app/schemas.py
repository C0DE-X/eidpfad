from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .combat_protocol import CooperationResponseMessage, PlayCardMessage, ReactionMessage


Weapon = Literal["dual_blades", "axe", "bow", "crossbow", "longsword"]
Magic = Literal["rune", "ember", "veil", "blood"]
GameMode = Literal["singleplayer", "multiplayer"]
CampaignLength = Literal["expedition", "fieldzug", "saga"]
CampaignStatus = Literal["waiting", "playing", "paused", "completed"]


class ProfileCreate(BaseModel):
    display_name: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_ -]+$")


class ProfileCreated(BaseModel):
    profile_id: str
    display_name: str
    device_token: str
    recovery_code: str


class ProfileRecover(BaseModel):
    display_name: str = Field(min_length=3, max_length=40)
    recovery_code: str = Field(min_length=32, max_length=128)


class ProfileRecovered(ProfileCreated):
    pass


class DeviceTokenRotated(BaseModel):
    device_token: str


class RecoveryCodeRotated(BaseModel):
    recovery_code: str


class ProfileView(BaseModel):
    profile_id: str
    display_name: str


class CharacterChoice(BaseModel):
    weapon: Weapon = "dual_blades"
    magic: Magic = "rune"


class CampaignCreate(CharacterChoice):
    game_mode: GameMode = "multiplayer"
    campaign_length: CampaignLength = "fieldzug"
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class CampaignJoin(CharacterChoice):
    invite_code: str = Field(min_length=6, max_length=8)


class CampaignView(BaseModel):
    campaign_id: str
    invite_code: str
    status: CampaignStatus
    campaign_length: CampaignLength
    world_tier: int
    game_mode: GameMode
    members: list[str]


class ProtocolMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: int = 2


class ReadyMessage(ProtocolMessage):
    type: Literal["ready"]
    ready: bool


class PassPhaseMessage(ProtocolMessage):
    type: Literal["pass_phase"]


class ClaimLootMessage(ProtocolMessage):
    type: Literal["claim_loot"]
    item_id: str = Field(min_length=1)


class ChooseScenarioMessage(ProtocolMessage):
    type: Literal["choose_scenario"]
    scenario_id: str = Field(min_length=1)


class EquipItemMessage(ProtocolMessage):
    type: Literal["equip_item"]
    item_id: str = Field(min_length=1)


class ScenarioActionMessage(ProtocolMessage):
    type: Literal["scenario_action"]
    action: Literal["prepare_hunt"]


class CommitFinalOathMessage(ProtocolMessage):
    type: Literal["commit_final_oath"]


class EndingChoiceMessage(ProtocolMessage):
    type: Literal["ending_choice"]
    choice: Literal["seal", "destroy", "bind", "dominate"]


class SelectLegacyMessage(ProtocolMessage):
    type: Literal["select_legacy"]
    item_id: str = Field(min_length=1)


class ConfirmNewGamePlusMessage(ProtocolMessage):
    type: Literal["confirm_new_game_plus"]


class CinematicAckMessage(ProtocolMessage):
    type: Literal["cinematic_ack"]
    cinematic_id: str = Field(min_length=1)
    skipped: bool = False


ClientMessage = Annotated[
    ReadyMessage
    | PlayCardMessage
    | ReactionMessage
    | CooperationResponseMessage
    | PassPhaseMessage
    | ClaimLootMessage
    | ChooseScenarioMessage
    | EquipItemMessage
    | ScenarioActionMessage
    | CommitFinalOathMessage
    | EndingChoiceMessage
    | SelectLegacyMessage
    | ConfirmNewGamePlusMessage
    | CinematicAckMessage,
    Field(discriminator="type"),
]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
