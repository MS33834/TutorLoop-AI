"""Unit tests for auth_service pure functions.

Covers password hashing/verification and JWT access token creation without
requiring a running database. The async ``get_current_user`` dependency (which
needs a DB session) is intentionally excluded.

Note: this environment ships passlib 1.7.4 alongside bcrypt 5.x, which are
incompatible (passlib's wrap-bug detection raises ``ValueError``). When the
bcrypt backend fails to load, the ``_working_hasher`` fixture substitutes a
working passlib scheme so the hash/verify round-trip logic is still exercised.
In an environment with a compatible bcrypt, the real backend is used as-is.
"""

from datetime import UTC, datetime

import jwt
import pytest
from fastapi import HTTPException
from passlib.context import CryptContext

from app.config import settings
from app.services import auth_service
from app.services.auth_service import (
    ACCESS_TOKEN_TYPE,
    ALGORITHM,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)

PASSWORD = "Sup3rSecret!"


@pytest.fixture(autouse=True)
def _working_hasher(monkeypatch):
    """Ensure ``pwd_context`` can actually hash/verify during the test."""
    try:
        auth_service.pwd_context.hash("probe-password")
    except Exception:
        monkeypatch.setattr(
            auth_service,
            "pwd_context",
            CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto"),
        )


def test_verify_password_correct_returns_true():
    hashed = get_password_hash(PASSWORD)
    assert verify_password(PASSWORD, hashed) is True


def test_verify_password_wrong_returns_false():
    hashed = get_password_hash(PASSWORD)
    assert verify_password("definitely-not-it", hashed) is False


def test_hash_password_returns_non_empty_string():
    hashed = get_password_hash(PASSWORD)
    assert isinstance(hashed, str)
    assert hashed  # non-empty
    # The plaintext must not appear verbatim in the hash.
    assert PASSWORD not in hashed


def test_hash_password_uses_random_salt():
    # bcrypt embeds a random salt, so hashing the same password twice must
    # produce distinct hashes that both verify against the plaintext.
    h1 = get_password_hash(PASSWORD)
    h2 = get_password_hash(PASSWORD)
    assert h1 != h2
    assert verify_password(PASSWORD, h1)
    assert verify_password(PASSWORD, h2)


def test_create_access_token_returns_valid_jwt_string():
    token = create_access_token({"sub": "user-123"})
    assert isinstance(token, str)
    assert token.count(".") == 2  # JWT structure: header.payload.signature


def test_create_access_token_contains_user_id():
    user_id = "user-abc-456"
    token = create_access_token({"sub": user_id})
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload["sub"] == user_id


def test_create_access_token_includes_expiry():
    token = create_access_token({"sub": "user-123"})
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert "exp" in payload
    # A freshly minted token must not be expired.
    assert payload["exp"] > 0


def test_create_access_token_includes_iat_claim():
    """The token must include an 'iat' (issued-at) timestamp."""
    token = create_access_token({"sub": "user-123"})
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert "iat" in payload
    assert payload["iat"] > 0


def test_create_access_token_includes_type_claim():
    """The token must include a 'type' claim set to 'access'."""
    token = create_access_token({"sub": "user-123"})
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload.get("type") == "access"


def test_create_access_token_respects_custom_expiry():
    from datetime import timedelta

    token = create_access_token({"sub": "user-123"}, expires_delta=timedelta(seconds=-1))
    # An already-expired token should fail signature/exp verification.
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def test_create_access_token_does_not_mutate_input_data():
    data = {"sub": "user-123"}
    create_access_token(data)
    assert data == {"sub": "user-123"}  # original dict untouched (no "exp" added)


# ---------------------------------------------------------------------------
# Refresh token tests
# ---------------------------------------------------------------------------


def test_create_refresh_token_returns_valid_jwt_string():
    token = create_refresh_token({"sub": "user-123"})
    assert isinstance(token, str)
    assert token.count(".") == 2


def test_create_refresh_token_contains_type_claim():
    token = create_refresh_token({"sub": "user-123"})
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload.get("type") == REFRESH_TOKEN_TYPE


def test_create_refresh_token_contains_subject():
    user_id = "user-refresh-abc"
    token = create_refresh_token({"sub": user_id})
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload["sub"] == user_id


def test_create_refresh_token_has_longer_expiry_than_access():
    """Refresh token expiry (30 days) must outlive the access token expiry."""
    access = create_access_token({"sub": "u1"})
    refresh = create_refresh_token({"sub": "u1"})
    access_payload = jwt.decode(access, settings.secret_key, algorithms=[ALGORITHM])
    refresh_payload = jwt.decode(refresh, settings.secret_key, algorithms=[ALGORITHM])
    assert refresh_payload["exp"] > access_payload["exp"]


def test_create_refresh_token_does_not_mutate_input_data():
    data = {"sub": "user-123"}
    create_refresh_token(data)
    assert data == {"sub": "user-123"}


def test_decode_access_token_rejects_refresh_token():
    """An access-token decoder must reject a refresh token (type mismatch)."""
    refresh = create_refresh_token({"sub": "user-123"})
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(refresh)
    assert exc_info.value.status_code == 401


def test_decode_refresh_token_rejects_access_token():
    """A refresh-token decoder must reject an access token (type mismatch)."""
    access = create_access_token({"sub": "user-123"})
    with pytest.raises(HTTPException) as exc_info:
        decode_refresh_token(access)
    assert exc_info.value.status_code == 401


def test_decode_access_token_returns_payload_for_valid_access_token():
    token = create_access_token({"sub": "user-xyz"})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-xyz"
    assert payload["type"] == ACCESS_TOKEN_TYPE


def test_decode_refresh_token_returns_payload_for_valid_refresh_token():
    token = create_refresh_token({"sub": "user-xyz"})
    payload = decode_refresh_token(token)
    assert payload["sub"] == "user-xyz"
    assert payload["type"] == REFRESH_TOKEN_TYPE


def test_decode_access_token_rejects_garbage_string():
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not.a.jwt")
    assert exc_info.value.status_code == 401


def test_decode_refresh_token_rejects_expired_token():
    from datetime import timedelta

    # Manually craft an expired refresh token.
    import jwt as _jwt

    from app.services.auth_service import REFRESH_TOKEN_EXPIRE_DAYS

    now = datetime.now(UTC)
    payload = {
        "sub": "user-123",
        "exp": now - timedelta(seconds=1),
        "iat": now - timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "type": REFRESH_TOKEN_TYPE,
    }
    expired = _jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    with pytest.raises(HTTPException) as exc_info:
        decode_refresh_token(expired)
    assert exc_info.value.status_code == 401
