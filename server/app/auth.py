import hashlib
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Profile, ProfileRecovery, utc_now


bearer = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_device_token() -> tuple[str, str]:
    return create_secret()


def create_recovery_code() -> tuple[str, str]:
    return create_secret()


def create_secret() -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    return secret, hash_token(secret)


def rotate_device_token(profile: Profile) -> str:
    token, profile.token_hash = create_device_token()
    return token


def rotate_recovery_code(db: Session, profile: Profile) -> str:
    recovery_code, recovery_hash = create_recovery_code()
    credential = db.get(ProfileRecovery, profile.id)
    if credential is None:
        credential = ProfileRecovery(profile_id=profile.id, recovery_hash=recovery_hash)
        db.add(credential)
    else:
        credential.recovery_hash = recovery_hash
        credential.rotated_at = utc_now()
    return recovery_code


def verify_recovery_code(stored_hash: str, recovery_code: str) -> bool:
    return secrets.compare_digest(stored_hash, hash_token(recovery_code))


def get_current_profile(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Profile:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    profile = db.scalar(select(Profile).where(Profile.token_hash == hash_token(credentials.credentials)))
    if profile is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return profile
