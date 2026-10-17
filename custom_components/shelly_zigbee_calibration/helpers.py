"""Resolve existing ZHA devices; never open a second radio connection."""
from homeassistant.components.zha.helpers import get_config_entry, get_zha_gateway
from homeassistant.helpers import device_registry as dr, entity_registry as er

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


def get_registered_device(hass, ieee):
    """Return the exact device owned by ZHA, never a second plugin device."""
    entry = get_config_entry(hass)
    registered = dr.async_get(hass).async_get_device_by_identifier(
        ("zha", ieee), entry.entry_id
    )
    if registered is None:
        raise ValueError("Das vorhandene ZHA-Gerät ist noch nicht registriert")
    return registered


def migrate_button_device(hass, entry, target):
    """Move only our button; remove only empty duplicates owned by our entry."""
    ieee = entry.data["ieee"]
    entities = er.async_get(hass)
    entity_id = entities.async_get_entity_id(
        "button", "shelly_zigbee_calibration", f"{ieee}_zigbee_calibration"
    )
    if entity_id:
        entity = entities.async_get(entity_id)
        if entity.config_entry_id == entry.entry_id and entity.device_id != target.id:
            entities.async_update_entity(entity_id, device_id=target.id)
    devices = dr.async_get(hass)
    for duplicate in devices.async_get_devices(
        identifiers={("zha", ieee)}, config_entry_id=entry.entry_id
    ):
        if duplicate.id == target.id:
            continue
        if er.async_entries_for_device(entities, duplicate.id, include_disabled_entities=True):
            continue
        if dr.async_entries_for_parent_device(devices, duplicate.id):
            continue
        devices.async_remove_device(duplicate.id)
