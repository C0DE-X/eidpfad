from contextlib import asynccontextmanager
from ipaddress import ip_address
from secrets import randbelow

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from sqlalchemy import case, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from .auth import (
    create_device_token,
    get_current_profile,
    hash_token,
    rotate_device_token,
    rotate_recovery_code,
    verify_recovery_code,
)
from .config import get_settings
from .campaign_runtime import CampaignRuntime
from .content import ContentBundle
from .database import Base, SessionLocal, engine, get_db
from .game_engine import RuleViolation
from .lobby import lobbies
from .models import Campaign, CampaignMember, Profile, ProfileRecovery
from .schemas import (
    CampaignCreate,
    CampaignJoin,
    CampaignView,
    ClientMessage,
    DeviceTokenRotated,
    ProfileCreate,
    ProfileCreated,
    ProfileRecover,
    ProfileRecovered,
    ProfileView,
    RecoveryCodeRotated,
    client_message_adapter,
)


settings = get_settings()
content = ContentBundle()
runtime_games: dict[str, CampaignRuntime] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Production containers apply Alembic before the process starts. Tests and
    # direct development launches keep a disposable-schema convenience path.
    if not settings.production:
        Base.metadata.create_all(bind=engine)
    # Runtime connections and ready confirmations never survive a process
    # restart, so persisted matches must resume through the explicit pause gate.
    with SessionLocal() as db:
        db.execute(update(Campaign).where(Campaign.status == "playing").values(status="paused"))
        db.commit()
    yield


app = FastAPI(
    title="Eidpfad Server",
    version="0.5.0",
    lifespan=lifespan,
    docs_url=None if settings.production else "/docs",
    redoc_url=None if settings.production else "/redoc",
)


@app.middleware("http")
async def require_secure_transport(request: Request, call_next):
    """Reject clear-text production traffic unless it originates on loopback.

    Uvicorn's trusted proxy-header support turns Caddy's forwarded protocol into
    ``https``. The loopback exception keeps local health checks and development
    workflows usable without weakening remote bearer-token transport.
    """
    client_host = request.client.host if request.client else ""
    if settings.production and request.url.scheme != "https" and not _is_loopback_host(client_host):
        return JSONResponse(
            status_code=status.HTTP_426_UPGRADE_REQUIRED,
            content={"detail": "HTTPS is required"},
            headers={"Upgrade": "TLS/1.3"},
        )
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/health/ready")
def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.post("/api/v1/profiles", response_model=ProfileCreated, status_code=status.HTTP_201_CREATED)
def create_profile(request: ProfileCreate, db: Session = Depends(get_db)) -> ProfileCreated:
    token, token_hash = create_device_token()
    profile = Profile(display_name=request.display_name.strip(), token_hash=token_hash)
    db.add(profile)
    try:
        db.flush()
        recovery_code = rotate_recovery_code(db, profile)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Display name is already in use") from exc
    db.refresh(profile)
    return ProfileCreated(
        profile_id=profile.id,
        display_name=profile.display_name,
        device_token=token,
        recovery_code=recovery_code,
    )


@app.post("/api/v1/profiles/recover", response_model=ProfileRecovered)
def recover_profile(request: ProfileRecover, db: Session = Depends(get_db)) -> ProfileRecovered:
    profile = db.scalar(
        select(Profile)
        .where(Profile.display_name == request.display_name.strip())
        .with_for_update()
    )
    credential = db.get(ProfileRecovery, profile.id) if profile is not None else None
    stored_hash = credential.recovery_hash if credential is not None else "0" * 64
    recovery_matches = verify_recovery_code(stored_hash, request.recovery_code)
    if profile is None or credential is None or not recovery_matches:
        # Do not reveal whether the profile or recovery enrollment exists.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid recovery credentials")

    device_token = rotate_device_token(profile)
    recovery_code = rotate_recovery_code(db, profile)
    db.commit()
    return ProfileRecovered(
        profile_id=profile.id,
        display_name=profile.display_name,
        device_token=device_token,
        recovery_code=recovery_code,
    )


@app.get("/api/v1/profiles/me", response_model=ProfileView)
def read_profile(profile: Profile = Depends(get_current_profile)) -> ProfileView:
    return ProfileView(profile_id=profile.id, display_name=profile.display_name)


@app.post("/api/v1/profiles/me/token", response_model=DeviceTokenRotated)
def rotate_profile_token(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> DeviceTokenRotated:
    device_token = rotate_device_token(profile)
    db.commit()
    return DeviceTokenRotated(device_token=device_token)


@app.post("/api/v1/profiles/me/recovery-code", response_model=RecoveryCodeRotated)
def rotate_profile_recovery_code(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> RecoveryCodeRotated:
    recovery_code = rotate_recovery_code(db, profile)
    db.commit()
    return RecoveryCodeRotated(recovery_code=recovery_code)


@app.get("/api/v1/campaigns", response_model=list[CampaignView])
def list_campaigns(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[CampaignView]:
    campaigns = list(
        db.scalars(
            select(Campaign)
            .join(CampaignMember, CampaignMember.campaign_id == Campaign.id)
            .where(CampaignMember.profile_id == profile.id)
            .order_by(
                case(
                    (Campaign.status == "playing", 0),
                    (Campaign.status == "paused", 1),
                    (Campaign.status == "waiting", 2),
                    else_=3,
                ),
                Campaign.created_at.desc(),
            )
        )
    )
    return [_campaign_view(db, campaign) for campaign in campaigns]


@app.post("/api/v1/campaigns", response_model=CampaignView, status_code=status.HTTP_201_CREATED)
def create_campaign(
    request: CampaignCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> CampaignView:
    campaign = Campaign(
        invite_code=_new_invite_code(db),
        owner_profile_id=profile.id,
        seed=request.seed if request.seed is not None else randbelow(2**31),
        campaign_length=request.campaign_length,
        game_mode=request.game_mode,
    )
    db.add(campaign)
    db.flush()
    db.add(
        CampaignMember(
            campaign_id=campaign.id,
            profile_id=profile.id,
            weapon=request.weapon,
            magic=request.magic,
        )
    )
    db.commit()
    return _campaign_view(db, campaign)


@app.post("/api/v1/campaigns/join", response_model=CampaignView)
def join_campaign(
    request: CampaignJoin,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> CampaignView:
    code = request.invite_code.strip().upper()
    # Serialize concurrent joins so two clients cannot both observe the second
    # slot as free. PostgreSQL enforces this row lock in the VPS deployment.
    campaign = db.scalar(select(Campaign).where(Campaign.invite_code == code).with_for_update())
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.game_mode == "singleplayer":
        raise HTTPException(status_code=409, detail="Singleplayer campaigns cannot be joined")

    existing = db.scalar(
        select(CampaignMember).where(
            CampaignMember.campaign_id == campaign.id,
            CampaignMember.profile_id == profile.id,
        )
    )
    if existing is None:
        if campaign.status != "waiting":
            raise HTTPException(status_code=409, detail="Campaign has already started")
        member_count = db.scalar(
            select(func.count()).select_from(CampaignMember).where(CampaignMember.campaign_id == campaign.id)
        )
        if member_count >= 2:
            raise HTTPException(status_code=409, detail="Campaign already has two players")
        db.add(
            CampaignMember(
                campaign_id=campaign.id,
                profile_id=profile.id,
                weapon=request.weapon,
                magic=request.magic,
            )
        )
        db.commit()
    return _campaign_view(db, campaign)


@app.websocket("/ws/campaigns/{campaign_id}")
async def campaign_socket(websocket: WebSocket, campaign_id: str) -> None:
    client_host = websocket.client.host if websocket.client else ""
    if settings.production and websocket.url.scheme != "wss" and not _is_loopback_host(client_host):
        await websocket.close(code=4403, reason="WSS is required")
        return

    token = _bearer_from_header(websocket.headers.get("authorization"))
    if token is None:
        await websocket.close(code=4401, reason="Missing bearer token")
        return

    db = SessionLocal()
    profile = db.scalar(select(Profile).where(Profile.token_hash == hash_token(token)))
    member = None
    if profile is not None:
        member = db.scalar(
            select(CampaignMember).where(
                CampaignMember.campaign_id == campaign_id,
                CampaignMember.profile_id == profile.id,
            )
        )
    if profile is None or member is None:
        await websocket.close(code=4401, reason="Unauthorized")
        db.close()
        return

    await lobbies.connect(campaign_id, profile.id, websocket)
    try:
        async with lobbies.lock(campaign_id):
            await _initialize_connection(db, campaign_id, websocket, profile.id)
        while True:
            raw = await websocket.receive_json()
            try:
                current_token_hash = db.scalar(
                    select(Profile.token_hash).where(Profile.id == profile.id)
                )
                if current_token_hash != hash_token(token):
                    await websocket.close(code=4401, reason="Token was rotated")
                    break
                message = client_message_adapter.validate_python(raw)
                if message.protocol_version != settings.protocol_version:
                    raise RuleViolation("Unsupported protocol version")
                async with lobbies.lock(campaign_id):
                    await _handle_message(db, campaign_id, profile.id, message)
            except (RuleViolation, ValueError, ValidationError) as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        pass
    finally:
        disconnect_lock = lobbies.lock(campaign_id)
        async with disconnect_lock:
            removed = lobbies.disconnect(campaign_id, profile.id, websocket)
            if removed:
                await _finalize_disconnect(db, campaign_id)
        db.close()


async def _handle_message(db: Session, campaign_id: str, profile_id: str, message: ClientMessage) -> None:
    member_ids = list(
        db.scalars(select(CampaignMember.profile_id).where(CampaignMember.campaign_id == campaign_id))
    )
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise RuleViolation("Campaign no longer exists")

    if message.type == "ready":
        if campaign.status == "completed":
            raise RuleViolation("Completed campaigns cannot be readied or resumed")
        if message.ready and not _all_required_players_connected(campaign, member_ids):
            requirement = "the solo player" if campaign.game_mode == "singleplayer" else "both players"
            raise RuleViolation(f"Cannot ready until {requirement} are connected")

        changed = lobbies.set_ready(campaign_id, profile_id, message.ready)
        transition_payload: dict | None = None
        if not message.ready and changed and campaign.status == "playing":
            campaign.status = "paused"
            lobbies.clear_ready(campaign_id)
            db.commit()
            transition_payload = {
                "type": "state",
                "events": [{"type": "campaign_paused", "reason": "player_not_ready"}],
                "state": _load_existing_game(db, campaign).client_view(profile_id),
                "campaign_status": campaign.status,
            }
        elif message.ready and _all_required_players_ready(campaign, member_ids):
            if campaign.status == "waiting":
                game = _load_or_start_game(db, campaign)
                campaign.status = "playing"
                _persist_game(db, campaign, game)
                transition_payload = {"type": "game_started", "events": []}
            elif campaign.status == "paused":
                game = _load_existing_game(db, campaign)
                campaign.status = "playing"
                db.commit()
                transition_payload = {
                    "type": "state",
                    "events": [{"type": "campaign_resumed"}],
                    "state": game.client_view(profile_id),
                    "campaign_status": campaign.status,
                }
            # Repeated ready=true while already playing is deliberately a no-op.

        await _broadcast_lobby(db, campaign_id)
        if transition_payload is not None:
            await _broadcast_runtime_state(
                campaign_id, game if "game" in locals() else _load_existing_game(db, campaign),
                transition_payload.get("events", []), campaign.status,
                message_type=str(transition_payload["type"]),
            )
        return

    if campaign.status == "completed":
        raise RuleViolation("The campaign is completed")
    if campaign.status != "playing":
        raise RuleViolation("The campaign is paused or has not started")
    if not _all_required_players_ready(campaign, member_ids):
        raise RuleViolation("All required players must be connected and ready")

    game = runtime_games.get(campaign_id)
    if game is None:
        game = _load_existing_game(db, campaign) if campaign.live_state else None
    if game is None:
        raise RuleViolation("The game has not started")

    if message.type == "play_card":
        events = game.play_card(
            profile_id, message.card_id,
            target_id=message.target_id,
            target_ids=list(message.target_ids),
        )
    elif message.type == "pass_phase":
        events = game.pass_phase(profile_id)
    elif message.type == "react":
        events = game.react(profile_id, message.card_id, list(message.target_ids))
    elif message.type == "confirm_cooperation":
        events = game.confirm_cooperation(profile_id, message.accepted)
    elif message.type == "claim_loot":
        events = game.claim_loot(profile_id, message.item_id)
    elif message.type == "choose_scenario":
        events = game.choose_scenario(profile_id, message.scenario_id)
    elif message.type == "equip_item":
        events = game.equip_item(profile_id, message.item_id)
    elif message.type == "scenario_action":
        events = game.perform_scenario_action(profile_id, message.action)
    elif message.type == "commit_final_oath":
        events = game.commit_final_oath(profile_id)
    elif message.type == "ending_choice":
        events = game.submit_ending(profile_id, message.choice)
    elif message.type == "select_legacy":
        events = game.select_legacy(profile_id, message.item_id)
    elif message.type == "confirm_new_game_plus":
        events = game.confirm_new_game_plus(profile_id)
        if game.pending_new_game_plus:
            _persist_new_game_plus_meta(db, campaign, game)
            events.extend(game.start_new_game_plus())
    elif message.type == "cinematic_ack":
        events = game.cinematic_ack(profile_id, message.cinematic_id, message.skipped)
    else:
        raise RuleViolation("Unsupported message")

    _persist_game(db, campaign, game)
    await _broadcast_runtime_state(campaign_id, game, events, campaign.status)
    if campaign.status == "completed":
        lobbies.clear_ready(campaign_id)
        await _broadcast_lobby(db, campaign_id)


def _campaign_loadouts(db: Session, campaign_id: str) -> dict[str, dict[str, str]]:
    members = list(db.scalars(select(CampaignMember).where(CampaignMember.campaign_id == campaign_id)))
    return {
        member.profile_id: {"weapon": member.weapon, "magic": member.magic}
        for member in members
    }


def _load_or_start_game(db: Session, campaign: Campaign) -> CampaignRuntime:
    if campaign.id in runtime_games:
        return runtime_games[campaign.id]
    if campaign.live_state:
        game = CampaignRuntime.restore(
            campaign.id,
            campaign.live_state,
            cards=content.cards,
            items=content.items,
            enemies=content.enemies,
            fallback_loadouts=_campaign_loadouts(db, campaign.id),
            game_mode=campaign.game_mode,
        )
    else:
        game = CampaignRuntime.new(
            campaign_id=campaign.id,
            seed=campaign.seed,
            loadouts=_campaign_loadouts(db, campaign.id),
            cards=content.cards,
            items=content.items,
            enemies=content.enemies,
            campaign_length=campaign.campaign_length,
            world_tier=campaign.world_tier,
            game_mode=campaign.game_mode,
        )
    runtime_games[campaign.id] = game
    return game


def _load_existing_game(db: Session, campaign: Campaign) -> CampaignRuntime:
    if not campaign.live_state:
        raise RuleViolation("No persisted game state is available")
    return _load_or_start_game(db, campaign)


def _persist_game(db: Session, campaign: Campaign, game: CampaignRuntime) -> None:
    campaign.live_state = game.export()
    campaign.checkpoint_state = game.game.state.checkpoint
    campaign.version += 1
    db.commit()


def _persist_new_game_plus_meta(
    db: Session, campaign: Campaign, runtime: CampaignRuntime
) -> None:
    if runtime.postgame is None or runtime.pending_new_game_plus is None:
        raise RuleViolation("New Game+ state is incomplete")
    payload = runtime.pending_new_game_plus
    for profile_id in runtime.game.state.turn_order:
        profile = db.get(Profile, profile_id)
        member = db.scalar(select(CampaignMember).where(
            CampaignMember.campaign_id == campaign.id,
            CampaignMember.profile_id == profile_id,
        ))
        if profile is None or member is None:
            raise RuleViolation("Campaign member disappeared during New Game+ transition")
        profile.meta_progress = runtime.postgame.meta_progress_for(
            profile_id, profile.meta_progress
        )
        member.character_level = int(payload["character_levels"][profile_id])
    campaign.seed = int(payload["seed"])
    campaign.world_tier = int(payload["world_tier"])
    campaign.campaign_length = str(payload["campaign_length"])
    db.flush()


async def _broadcast_runtime_state(
    campaign_id: str,
    runtime: CampaignRuntime,
    events: list[dict],
    campaign_status: str,
    *,
    message_type: str = "state",
) -> None:
    for profile_id in list(lobbies.connections.get(campaign_id, {})):
        await lobbies.send_to(campaign_id, profile_id, {
            "type": message_type,
            "events": events,
            "state": runtime.client_view(profile_id),
            "campaign_status": campaign_status,
        })


async def _broadcast_lobby(db: Session, campaign_id: str) -> None:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return
    member_rows = list(
        db.execute(
            select(CampaignMember.profile_id, Profile.display_name)
            .join(Profile, Profile.id == CampaignMember.profile_id)
            .where(CampaignMember.campaign_id == campaign_id)
            .order_by(CampaignMember.id)
        )
    )
    members = [row.profile_id for row in member_rows]
    connected = set(lobbies.connections.get(campaign_id, {}))
    ready = set(lobbies.ready.get(campaign_id, set()))
    await lobbies.broadcast(
        campaign_id,
        {
            "type": "lobby",
            "members": members,
            "connected": sorted(connected),
            "ready": sorted(ready),
            "players": [
                {
                    "profile_id": row.profile_id,
                    "display_name": row.display_name,
                    "connected": row.profile_id in connected,
                    "ready": row.profile_id in ready,
                }
                for row in member_rows
            ],
            "campaign_status": campaign.status,
            "game_mode": campaign.game_mode,
            "can_ready": campaign.status in {"waiting", "paused"} and (
                len(members) == 1 if campaign.game_mode == "singleplayer" else len(members) == 2
            ),
            "can_pause": campaign.status == "playing",
        },
    )


async def _initialize_connection(
    db: Session,
    campaign_id: str,
    websocket: WebSocket,
    profile_id: str | None = None,
) -> None:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise RuleViolation("Campaign no longer exists")
    member_ids = list(
        db.scalars(select(CampaignMember.profile_id).where(CampaignMember.campaign_id == campaign_id))
    )
    # A process restart loses volatile ready/socket state. Normalize a formerly
    # playing campaign to paused as soon as a member reconnects alone.
    if campaign.status == "playing" and not _all_required_players_connected(campaign, member_ids):
        campaign.status = "paused"
        lobbies.clear_ready(campaign_id)
        db.commit()

    if campaign.live_state:
        game = _load_existing_game(db, campaign)
        if profile_id is None:
            profile_id = next(
                (
                    member_id for member_id, socket in lobbies.connections.get(campaign_id, {}).items()
                    if socket is websocket
                ),
                None,
            )
        if profile_id is None:
            raise RuleViolation("Cannot identify reconnecting campaign member")
        await websocket.send_json(
            {
                "type": "state",
                "events": [],
                "state": game.client_view(profile_id),
                "snapshot": True,
                "campaign_status": campaign.status,
            }
        )
    await _broadcast_lobby(db, campaign_id)


async def _finalize_disconnect(db: Session, campaign_id: str) -> None:
    campaign = db.get(Campaign, campaign_id)
    if campaign is not None:
        lobbies.clear_ready(campaign_id)
        if campaign.status == "playing":
            campaign.status = "paused"
            db.commit()
        await _broadcast_lobby(db, campaign_id)
    if campaign_id not in lobbies.connections:
        runtime_games.pop(campaign_id, None)


def _campaign_view(db: Session, campaign: Campaign) -> CampaignView:
    members = list(db.scalars(select(CampaignMember.profile_id).where(CampaignMember.campaign_id == campaign.id)))
    return CampaignView(
        campaign_id=campaign.id,
        invite_code=campaign.invite_code,
        status=campaign.status,
        campaign_length=campaign.campaign_length,
        world_tier=campaign.world_tier,
        game_mode=campaign.game_mode,
        members=members,
    )


def _all_required_players_connected(campaign: Campaign, member_ids: list[str]) -> bool:
    if campaign.game_mode == "singleplayer":
        return len(member_ids) == 1 and set(member_ids) <= set(lobbies.connections.get(campaign.id, {}))
    return lobbies.all_connected(campaign.id, member_ids)


def _all_required_players_ready(campaign: Campaign, member_ids: list[str]) -> bool:
    return _all_required_players_connected(campaign, member_ids) and set(member_ids) <= lobbies.ready.get(campaign.id, set())


def _new_invite_code(db: Session) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(alphabet[randbelow(len(alphabet))] for _ in range(6))
        if db.scalar(select(Campaign.id).where(Campaign.invite_code == code)) is None:
            return code


def _bearer_from_header(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().rstrip(".")
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False
