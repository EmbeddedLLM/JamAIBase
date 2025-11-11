from datetime import datetime, timedelta, timezone
from time import sleep

import pytest

from owl.utils.exceptions import AuthorizationError
from owl.utils.jwt import decode_jwt, encode_jwt


def test_jwt_round_trip():
    data = {"user_id": 123, "role": "admin"}
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = encode_jwt(data, expiry)
    decoded = decode_jwt(token, "expired", "invalid")
    # Should contain original data plus 'iat' and 'exp'
    assert decoded["user_id"] == 123
    assert decoded["role"] == "admin"
    assert "iat" in decoded
    assert "exp" in decoded


def test_jwt_expired():
    expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
    token = encode_jwt({"user_id": 456}, expiry)
    sleep(2)
    with pytest.raises(AuthorizationError, match="expired"):
        decode_jwt(token, "expired", "invalid")


def test_jwt_invalid_signature():
    data = {"user_id": 789}
    expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
    token = encode_jwt(data, expiry)
    # Tamper with the token
    bad_token = token + "abc"
    with pytest.raises(AuthorizationError, match="invalid"):
        decode_jwt(bad_token, "expired", "invalid")


def test_jwt_invalid_token_format():
    # Not even a JWT
    bad_token = "not.a.jwt"
    with pytest.raises(AuthorizationError, match="invalid"):
        decode_jwt(bad_token, "expired", "invalid")
