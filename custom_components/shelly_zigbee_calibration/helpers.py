"""Resolve existing ZHA devices; never open a second radio connection."""
from homeassistant.components.zha.helpers import get_config_entry, get_zha_gateway
from homeassistant.helpers import device_registry as dr

from .const import RPC_CLUSTER, RPC_ENDPOINT


def get_controller(hass):
    gateway = get_zha_gateway(hass)
    if gateway.application_controller is None:
        raise ValueError("ZHA ist noch nicht bereit")
    return gateway.application_controller


def is_supported(device):
    model = (getattr(device, "model", None) or "").casefold()
    manufacturer = (getattr(device, "manufacturer", None) or "").casefold()
    endpoint = getattr(device, "endpoints", {}).get(RPC_ENDPOINT)
    return (
        "shelly" in manufacturer
        and model in {"dimmer", "s4dm-0a101wwl", "shellydimmerg4", "shelly dimmer gen4"}
        and endpoint is not None
        and endpoint.profile_id == 0xC001
        and RPC_CLUSTER in endpoint.in_clusters
    )


def get_candidates(hass):
    app = get_controller(hass)
    registry = dr.async_get(hass)
    zha_entry = get_config_entry(hass)
    result = {}
    for device in app.devices.values():
        if not is_supported(device):
            continue
        ieee = str(device.ieee)
        registered = registry.async_get_device_by_identifier(("zha", ieee), zha_entry.entry_id)
        name = (registered.name_by_user or registered.name) if registered else None
        result[ieee] = f"{name or 'Shelly Dimmer Gen4'} ({ieee})"
    return result


def resolve_device(hass, ieee):
    app = get_controller(hass)
    device = next((d for d in app.devices.values() if str(d.ieee) == ieee), None)
    if device is None or not is_supported(device):
        raise ValueError("Der konfigurierte Shelly Dimmer Gen4 ist in ZHA nicht verfügbar")
    return device
