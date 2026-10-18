"""Export the most recent read-only RPC check without device configuration."""
import copy


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = getattr(entry, "runtime_data", None)
    report = getattr(runtime, "rpc_report", None)
    return {"rpc_diagnostic": copy.deepcopy(report),
            "note": "Zigbee-RPC prüfen am Shelly-Gerät drücken, dann Diagnose erneut herunterladen."}
