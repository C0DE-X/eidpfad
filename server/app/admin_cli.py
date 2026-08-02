"""Offline administration, backup and profile recovery for Eidpfad.

Run this command in the stopped server container.  It intentionally has no HTTP
endpoint so production administration cannot be exposed accidentally.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, select

from .database import SessionLocal
from .models import Campaign, CampaignMember, Profile, ProfileRecovery

FORMAT_VERSION = 1


def _dump(row, fields: tuple[str, ...]) -> dict:
    return {field: getattr(row, field) for field in fields}


def export_backup(path: Path) -> None:
    with SessionLocal() as db:
        payload = {
            "format_version": FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "profiles": [_dump(row, ("id", "display_name", "token_hash", "meta_progress", "created_at")) for row in db.scalars(select(Profile))],
            "profile_recovery": [_dump(row, ("profile_id", "recovery_hash", "rotated_at")) for row in db.scalars(select(ProfileRecovery))],
            "campaigns": [_dump(row, ("id", "invite_code", "owner_profile_id", "seed", "campaign_length", "game_mode", "world_tier", "status", "checkpoint_state", "live_state", "version", "created_at")) for row in db.scalars(select(Campaign))],
            "campaign_members": [_dump(row, ("id", "campaign_id", "profile_id", "weapon", "magic", "character_level")) for row in db.scalars(select(CampaignMember))],
        }
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as target:
            temporary_name = target.name
            os.chmod(temporary_name, 0o600)
            target.write(serialized)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    print(f"Backup written to {path}")


def list_profiles() -> None:
    with SessionLocal() as db:
        for profile in db.scalars(select(Profile).order_by(Profile.display_name)):
            campaigns = db.scalar(select(func.count()).select_from(CampaignMember).where(CampaignMember.profile_id == profile.id))
            print(f"{profile.id}\t{profile.display_name}\t{campaigns} campaign(s)\t{profile.created_at}")


def delete_profile(profile_id: str, *, confirm: str) -> None:
    if confirm != profile_id:
        raise SystemExit("--confirm must exactly match --profile-id")
    with SessionLocal() as db:
        profile = db.get(Profile, profile_id)
        if profile is None:
            raise SystemExit("Profile not found")
        owned = list(db.scalars(select(Campaign).where(Campaign.owner_profile_id == profile_id)))
        for campaign in owned:
            db.execute(delete(CampaignMember).where(CampaignMember.campaign_id == campaign.id))
            db.delete(campaign)
        db.execute(delete(CampaignMember).where(CampaignMember.profile_id == profile_id))
        recovery = db.get(ProfileRecovery, profile_id)
        if recovery is not None:
            db.delete(recovery)
        db.delete(profile)
        db.commit()
    print(f"Deleted profile {profile_id} and {len(owned)} owned campaign(s)")


def restore_profile(path: Path, profile_id: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format_version") != FORMAT_VERSION:
        raise SystemExit("Unsupported backup format")
    required_collections = {"profiles", "profile_recovery", "campaigns", "campaign_members"}
    if not required_collections <= payload.keys() or not all(
        isinstance(payload[name], list) for name in required_collections
    ):
        raise SystemExit("Backup is incomplete or malformed")

    profile_data = next((row for row in payload["profiles"] if row["id"] == profile_id), None)
    if profile_data is None:
        raise SystemExit("Profile is not present in backup")
    own_memberships = [
        row for row in payload["campaign_members"] if row["profile_id"] == profile_id
    ]
    owned_campaigns = [
        row for row in payload["campaigns"] if row["owner_profile_id"] == profile_id
    ]
    owned_campaign_ids = {row["id"] for row in owned_campaigns}
    owned_memberships = [
        row for row in payload["campaign_members"]
        if row["campaign_id"] in owned_campaign_ids
    ]
    recovery = next((row for row in payload["profile_recovery"] if row["profile_id"] == profile_id), None)
    profile_data = dict(profile_data)
    recovery = dict(recovery) if recovery else None
    owned_campaigns = [dict(row) for row in owned_campaigns]
    memberships = {
        row["id"]: dict(row) for row in [*own_memberships, *owned_memberships]
    }
    profile_data["created_at"] = datetime.fromisoformat(profile_data["created_at"])
    if recovery:
        recovery["rotated_at"] = datetime.fromisoformat(recovery["rotated_at"])
    for row in owned_campaigns:
        row["created_at"] = datetime.fromisoformat(row["created_at"])
    with SessionLocal() as db:
        if db.get(Profile, profile_id) is not None:
            raise SystemExit("Profile already exists; delete it explicitly before restoring")
        required_partner_ids = {
            row["profile_id"] for row in memberships.values()
            if row["campaign_id"] in owned_campaign_ids and row["profile_id"] != profile_id
        }
        missing_partners = sorted(
            partner_id for partner_id in required_partner_ids
            if db.get(Profile, partner_id) is None
        )
        if missing_partners:
            raise SystemExit(
                "Cannot restore owned campaigns because member profiles are missing: "
                + ", ".join(missing_partners)
            )
        db.add(Profile(**profile_data))
        if recovery:
            db.add(ProfileRecovery(**recovery))
        for row in owned_campaigns:
            if db.get(Campaign, row["id"]) is None:
                db.add(Campaign(**row))
        db.flush()
        restored_memberships = 0
        skipped_memberships = 0
        for row in memberships.values():
            campaign_exists = db.get(Campaign, row["campaign_id"]) is not None
            if not campaign_exists:
                skipped_memberships += 1
                continue
            if db.get(CampaignMember, row["id"]) is None:
                db.add(CampaignMember(**row))
                restored_memberships += 1
        db.commit()
    print(
        f"Restored profile {profile_id} with {restored_memberships} campaign membership(s)"
        + (f"; skipped {skipped_memberships} missing non-owned campaign(s)" if skipped_memberships else "")
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="eidpfad-admin")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-profiles")
    backup = commands.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    remove = commands.add_parser("delete-profile")
    remove.add_argument("--profile-id", required=True)
    remove.add_argument("--confirm", required=True)
    restore = commands.add_parser("restore-profile")
    restore.add_argument("--input", type=Path, required=True)
    restore.add_argument("--profile-id", required=True)
    args = parser.parse_args()
    if args.command == "list-profiles":
        list_profiles()
    elif args.command == "backup":
        export_backup(args.output)
    elif args.command == "delete-profile":
        delete_profile(args.profile_id, confirm=args.confirm)
    else:
        restore_profile(args.input, args.profile_id)


if __name__ == "__main__":
    main()
