"""Shelly Dimmer Gen4 calibration through the existing ZHA connection."""
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .helpers import get_registered_device, migrate_button_device, resolve_device

PLATFORMS = [Platform.BUTTON]


async def async_setup_entry(hass, entry):
    try:
        resolve_device(hass, entry.data["ieee"])
        target = get_registered_device(hass, entry.data["ieee"])
    except (KeyError, ValueError) as exc:
        raise ConfigEntryNotReady(str(exc)) from exc
    migrate_button_device(hass, entry, target)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
