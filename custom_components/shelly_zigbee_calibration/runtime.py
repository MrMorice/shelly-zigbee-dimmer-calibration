"""Native Shelly configuration over Zigbee with persistent rollback recovery."""
import asyncio
import logging
import time

from homeassistant.components.zha.helpers import get_config_entry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .curve import Curve
from .helpers import get_registered_device, resolve_device
from .rpc import ShellyRpc
from .wizard import DimmingWizard, WizardError

_LOGGER = logging.getLogger(__name__)


class DimmingRuntime:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.curve")
        self.curve = Curve()
        self.pending = None
        self.source = None
        self.hardware_until = 0.0
        self.listeners = set()
        self.last_error = None
        self.wizard = DimmingWizard(self)

    async def load(self):
        data = await self.store.async_load() or {}
        self.pending = data.get("pending")

    def resolve_source(self):
        device = get_registered_device(self.hass, self.entry.data["ieee"])
        zha_entry = get_config_entry(self.hass)
        entities = er.async_get(self.hass)
        matches = [item.entity_id for item in er.async_entries_for_device(
            entities, device.id, include_disabled_entities=True
        ) if item.domain == "light" and item.platform == "zha"
            and item.config_entry_id == zha_entry.entry_id and item.disabled_by is None]
        if len(matches) != 1:
            raise WizardError("Am Shelly muss genau eine aktive ZHA-Lichtsteuerung vorhanden sein")
        return matches[0]

    async def prepare(self):
        if time.monotonic() < self.hardware_until:
            raise WizardError("Die automatische Kalibrierung könnte noch laufen. Bitte warten.")
        self.source = self.resolve_source()
        await self.recover()
        state = self.hass.states.get(self.source)
        if state is None or state.state not in {"on", "off"}:
            raise WizardError("Die ZHA-Lichtsteuerung ist gerade nicht erreichbar")
        self.curve = await self.read_curve()
        self.last_error = None

    async def recover(self):
        if self.pending is not None:
            if self.pending.get("source") != self.source:
                raise WizardError("Die ursprüngliche Lichtsteuerung wurde geändert. Wiederherstellung prüfen.")
            original = Curve(**self.pending["curve"])
            await self.apply(original)
            await self.restore(self.pending["snapshot"])
            await self.finish(original)

    async def snapshot(self):
        state = self.hass.states.get(self.source)
        if state is None or state.state not in {"on", "off"}:
            raise WizardError("Lampenstatus konnte nicht gelesen werden")
        brightness = state.attributes.get("brightness")
        if state.state == "on" and (not isinstance(brightness, (float, int)) or not 0 <= brightness <= 255):
            raise WizardError("Die aktuelle Lampenhelligkeit ist nicht verfügbar")
        return {"on": state.state == "on", "brightness": brightness}

    async def _call(self, service, values):
        if self.resolve_source() != self.source:
            raise WizardError("Die ursprüngliche Lichtsteuerung ist nicht mehr verfügbar")
        async with asyncio.timeout(15):
            await self.hass.services.async_call(
                "light", service, {"entity_id": self.source, **values}, blocking=True
            )

    async def output(self, percent):
        if percent <= 0:
            await self._call("turn_off", {})
        else:
            brightness = max(1, min(255, round(percent / 100 * 255)))
            await self._call("turn_on", {"brightness": brightness, "transition": 0})

    async def restore(self, snapshot):
        if snapshot["on"]:
            await self._call("turn_on", {"brightness": snapshot["brightness"], "transition": 0})
        else:
            await self._call("turn_off", {})

    def rpc(self):
        return ShellyRpc(resolve_device(self.hass, self.entry.data["ieee"]))

    async def read_curve(self):
        try:
            result = await self.rpc().call("Light.GetConfig", {"id": 0})
            return Curve.from_config(result)
        except ValueError as exc:
            raise WizardError(str(exc)) from exc

    async def apply(self, curve):
        # Partial SetConfig preserves unrelated settings and the original maximum.
        result = await self.rpc().call("Light.SetConfig", {"id": 0, "config": curve.as_config()})
        if result is not None:
            raise WizardError("Unerwartete Antwort auf Light.SetConfig")
        actual = await self.read_curve()
        if actual != curve:
            raise WizardError("Shelly hat die angefragten Dimmwerte nicht bestätigt")

    async def begin(self, snapshot):
        pending = {"source": self.source, "snapshot": snapshot, "curve": self.curve.as_dict()}
        await self.store.async_save({"pending": pending})
        self.pending = pending

    async def finish(self, curve):
        await self.store.async_save({"pending": None})
        self.curve = curve
        self.pending = None

    async def close(self):
        await self.wizard.cancel()

    def notify(self):
        # Entity availability checks the wizard lock, so publish after it releases.
        self.hass.loop.call_soon(self._notify_listeners)

    def _notify_listeners(self):
        for listener in tuple(self.listeners):
            listener()

    def report_error(self, message):
        self.last_error = message
        self.notify()
        _LOGGER.warning("Dimmkurven-Assistent: %s", message)
