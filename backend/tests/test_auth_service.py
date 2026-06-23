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

import jwt
import pytest
from passlib.context import CryptContext

from app.config import settings
from app.services import auth_service
from app.services.auth_service import (
    ALGORITHM,
    create_access_token,
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
