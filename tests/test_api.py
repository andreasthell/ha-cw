"""Tests for the API client's token handling."""

import asyncio
import base64
import json
from datetime import UTC, datetime

import pytest
from aiohttp import ClientResponseError

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


class _Response:
    def __init__(self, status: int, text: str = ""):
        self.status = status
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise ClientResponseError(status=self.status, message="error")

    async def text(self):
        return self._text


class _Session:
    """Answers every GET with *response*, or raises *error*."""

    def __init__(self, response: _Response | None = None, error: Exception | None = None):
        self._response = response
        self._error = error

    def get(self, url, **kwargs):
        if self._error:
            raise self._error
        return self._response


def _price_zone(session: _Session) -> str:
    client = CheckwattApiClient(session, "user", "password")
    return asyncio.run(client.get_price_zone())


class TestRequestErrors:
    def test_success(self):
        assert _price_zone(_Session(_Response(200, "SE4\n"))) == "SE4"

    def test_http_status_in_message(self):
        with pytest.raises(ConnectionError, match=r"^Request to /ems/pricezone failed: HTTP 404$"):
            _price_zone(_Session(_Response(404)))

    def test_timeout_in_message(self):
        # aiohttp's total timeout raises TimeoutError, which is not a ClientError.
        with pytest.raises(ConnectionError, match=r"^Request to /ems/pricezone failed: timeout$"):
            _price_zone(_Session(error=TimeoutError()))
