"""Config flow for CheckWatt."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthenticationError, CheckwattApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# M4: enforce reasonable length limits on credential fields.
_STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): vol.All(str, vol.Length(min=1, max=256)),
        vol.Required(CONF_PASSWORD): vol.All(str, vol.Length(min=1, max=256)),
    }
)


async def _validate(hass, user_input: dict) -> dict[str, str]:
    """Validate credentials and return errors dict (empty on success)."""
    client = CheckwattApiClient(
        async_get_clientsession(hass),
        user_input[CONF_USERNAME],
        user_input[CONF_PASSWORD],
    )
    errors: dict[str, str] = {}
    try:
        await client.validate_credentials()
    except AuthenticationError:
        errors["base"] = "invalid_auth"
    except ConnectionError:
        errors["base"] = "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error during CheckWatt credential validation")
        errors["base"] = "unknown"
    return errors


class CheckwattConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()
            errors = await _validate(self.hass, user_input)
            if not errors:
                # H1: use a generic title — don't expose the user's email in the UI/logs.
                return self.async_create_entry(title="CheckWatt", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_STEP_USER_SCHEMA,
            errors=errors,
        )

