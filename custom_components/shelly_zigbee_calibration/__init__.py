"""Shelly Dimmer Gen4 calibration through the existing ZHA connection."""
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import ConfigEntryNotReady

from .helpers import get_registered_device, migrate_button_device, resolve_device

from .runtime import DimmingRuntime

PLATFORMS = [Platform.BUTTON]


async def async_setup_entry(hass, entry):
    try:
        resolve_device(hass, entry.data["ieee"])
        target = get_registered_device(hass, entry.data["ieee"])
    except (KeyError, ValueError) as exc:
        raise ConfigEntryNotReady(str(exc)) from exc
    runtime = DimmingRuntime(hass, entry)
    try:
        await runtime.load()
    except Exception as exc:
        raise ConfigEntryNotReady(str(exc)) from exc
    entry.runtime_data = runtime

    async def stop(event):
        try:
            await runtime.close()
        except Exception as exc:
            runtime.report_error(str(exc))
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop))
    migrate_button_device(hass, entry, target)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    try:
        await entry.runtime_data.close()
    except Exception as exc:
        entry.runtime_data.report_error(str(exc))
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
