"""Export local write-only state, never imply that it was read from the device."""
import copy


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = getattr(entry, "runtime_data", None)
    return {"mode": "write_only", "device_values_confirmed": False,
        "saved_settings": copy.deepcopy(getattr(runtime, "saved_settings", {})),
        "last_sent": copy.deepcopy(getattr(runtime, "last_sent", None)),
        "recovery_pending": getattr(runtime, "pending", None) is not None,
        "outcome": getattr(runtime, "outcome", None)}
