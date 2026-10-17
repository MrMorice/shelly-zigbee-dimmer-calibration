"""One explicit calibration button per configured dimmer."""
import asyncio
import logging
import time

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util
from zigpy.exceptions import ZigbeeException

from .const import COOLDOWN_SECONDS
from .device_controls import control_buttons
from .helpers import get_registered_device, resolve_device
from .rpc import RpcError, ShellyRpc

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    ieee = entry.data["ieee"]
    device = get_registered_device(hass, ieee)
    entities = [CalibrationButton(ieee, device, runtime=entry.runtime_data)]
    if entry.runtime_data is not None:
        entities.extend(control_buttons(ieee, device, entry.runtime_data))
    async_add_entities(entities)


class CalibrationButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Kalibrierung starten"
    _attr_icon = "mdi:tune"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(self, ieee, registered_device=None, *, runtime=None):
        self.runtime = runtime
        self.ieee = ieee
        self._attr_unique_id = f"{ieee}_zigbee_calibration"
        # Core 2026.10 scopes identifiers by config entry. Reusing ZHA's
        # identifier via DeviceInfo would create a second device under our entry.
        # Attach the existing registry entry directly; EntityPlatform supports
        # this when device_info is None. The button keeps its existing unique ID.
        self.device_entry = registered_device
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0
        self._result = "Noch nicht gestartet"
        self._attempt = None

    @property
    def extra_state_attributes(self):
        return {"letzter_versuch": self._attempt, "ergebnis": self._result}

    async def async_press(self):
        if self.runtime is not None and (self.runtime.wizard.active or self.runtime.wizard.lock.locked() or self.runtime.pending is not None):
            raise HomeAssistantError("Zuerst den Dimmkurven-Assistenten beenden")
        if self._lock.locked():
            raise HomeAssistantError("Eine Kalibrierungsanfrage läuft bereits")
        if time.monotonic() < self._next_allowed:
            raise HomeAssistantError("Bitte nach dem letzten Versuch mindestens 130 Sekunden warten")
        async with self._lock:
            try:
                device = resolve_device(self.hass, self.ieee)
            except (KeyError, ValueError) as exc:
                raise HomeAssistantError(str(exc)) from exc
            self._next_allowed = time.monotonic() + COOLDOWN_SECONDS
            if self.runtime is not None:
                self.runtime.hardware_until = self._next_allowed
            self._attempt = dt_util.utcnow().isoformat()
            self._result = "Start wird angefragt"
            self.async_write_ha_state()
            try:
                await ShellyRpc(device).calibrate()
            except (RpcError, ZigbeeException, TimeoutError) as exc:
                self._result = str(exc)
                _LOGGER.warning("Kalibrierungsanfrage für %s: %s", self.ieee, exc)
                raise HomeAssistantError(str(exc)) from exc
            except asyncio.CancelledError:
                self._result = "Anfrage unterbrochen; Kalibrierung könnte bereits laufen"
                raise
            except Exception as exc:
                self._result = "Unerwarteter Fehler; Kalibrierung könnte bereits laufen"
                _LOGGER.exception("Kalibrierungsanfrage für %s fehlgeschlagen", self.ieee)
                raise HomeAssistantError(self._result) from exc
            else:
                self._result = "Befehl vollständig übertragen; Start und Abschluss an der Lampe prüfen"
            finally:
                # Cooldown starts after the transaction, including uncertain outcomes.
                self._next_allowed = time.monotonic() + COOLDOWN_SECONDS
                if self.runtime is not None:
                    self.runtime.hardware_until = self._next_allowed
                self.async_write_ha_state()
