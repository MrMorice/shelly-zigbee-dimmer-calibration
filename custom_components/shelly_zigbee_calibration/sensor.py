"""Assistant status on the existing Shelly device."""
from .device_controls import DimmingStatusSensor
from .helpers import get_registered_device


async def async_setup_entry(hass, entry, async_add_entities):
    ieee = entry.data["ieee"]
    async_add_entities([DimmingStatusSensor(ieee, get_registered_device(hass, ieee), entry.runtime_data)])
