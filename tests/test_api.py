"""Tests for the API client's token handling."""

import base64
import json
from datetime import UTC, datetime

from custom_components.checkwatt.api import CheckwattApiClient


def _jwt(claims: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


class TestStoreTokens:
    def test_expiry_read_from_urlsafe_payload(self):
        exp = int(datetime.now(UTC).timestamp()) + 900
        # "?>" and "~" encode to "-" and "_" in base64url.
        token = _jwt({"exp": exp, "iss": "https://example.com/?a>b~c", "name": "Åsa Öberg"})
        assert "-" in token or "_" in token
        client = CheckwattApiClient(None, "user", "password")
        client._store_tokens(
            {
                "JwtToken": token,
                "RefreshToken": "refresh",
                "RefreshTokenExpires": "2030-01-01T00:00:00Z",
            }
        )
        assert client._jwt_expiry == datetime.fromtimestamp(exp, tz=UTC)
