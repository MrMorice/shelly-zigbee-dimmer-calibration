"""Write-only dimming trials with local settings and explicit rollback limits."""
import asyncio
import logging
import time
from datetime import UTC, datetime

from homeassistant.components.zha.helpers import get_config_entry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .curve import Curve, validate_settings
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
        self.saved_settings = {}
        self.last_sent = None
        self.outcome = None
        self.mode = None
        self.wizard = DimmingWizard(self)

    async def load(self):
        data = await self.store.async_load() or {}
        self.pending = data.get("pending")
        self.saved_settings = validate_settings(data.get("saved_settings", {}))
        self.outcome = data.get("outcome")

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

    async def prepare(self, mode):
        if time.monotonic() < self.hardware_until:
            raise WizardError("Die automatische Kalibrierung könnte noch laufen. Bitte warten.")
        self.source = self.resolve_source()
        await self.recover()
        state = self.hass.states.get(self.source)
        if state is None or state.state not in {"on", "off"}:
            raise WizardError("Die ZHA-Lichtsteuerung ist gerade nicht erreichbar")
        self.mode = mode
        options = getattr(self.entry, "options", {})
        bounds = self.saved_settings.get("range_map", [0, 100])
        maximum = options.get("maximum", bounds[1]) if mode == "minimum" else bounds[1]
        gamma = self.saved_settings.get("gamma", options.get("initial_gamma", 1.0))
        minimum = 0 if mode == "minimum" else bounds[0]
        self.curve = Curve(minimum, gamma, maximum)
        self.last_error = None
        self.outcome = None

    def _restore_settings(self):
        if self.pending is None:
            return {}
        if "restore_settings" in self.pending:
            return validate_settings(self.pending["restore_settings"])
        # Recovery of a pre-0.3 native trial: these values were actually read.
        if "curve" in self.pending:
            return Curve(**self.pending["curve"]).as_config()
        raise WizardError("Unbekannte Wiederherstellungsdaten; Sicherung bleibt erhalten")

    async def recover(self):
        if self.pending is not None:
            if self.pending.get("source") != self.source:
                raise WizardError("Die ursprüngliche Lichtsteuerung wurde geändert. Wiederherstellung prüfen.")
            await self.rollback()
            await self.restore(self.pending["snapshot"])
            await self.finish(None)

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

    async def _send_settings(self, settings):
        settings = validate_settings(settings)
        if not settings:
            return
        await self.rpc().send("Light.SetConfig", {"id": 0, "config": settings})
        self.last_sent = {"values": settings, "sent_at": datetime.now(UTC).isoformat(),
            "transmission_acknowledged": True, "device_values_confirmed": False}

    async def apply(self, curve):
        if self.mode not in {"minimum", "gamma"}:
            raise WizardError("Kein Einstellungsmodus aktiv")
        await self._send_settings(curve.as_config(self.mode))

    async def rollback(self):
        # On the first trial we do not know previous native values. Send nothing.
        settings = self._restore_settings()
        if settings:
            await self._send_settings(settings)

    async def begin(self, snapshot):
        key = "range_map" if self.mode == "minimum" else "gamma"
        previous = ({key: self.saved_settings[key]} if key in self.saved_settings else {})
        pending = {"source": self.source, "snapshot": snapshot,
            "mode": self.mode, "restore_settings": previous}
        await self.store.async_save({"saved_settings": self.saved_settings,
            "pending": pending, "outcome": self.outcome})
        self.pending = pending

    async def finish(self, curve):
        settings = validate_settings(self.saved_settings)
        if curve is not None:
            settings.update(curve.as_config(self.mode))
            outcome = "Werte gesendet und in HA gespeichert"
        elif self._restore_settings():
            outcome = "Gespeicherte Werte erneut gesendet"
        else:
            outcome = "Gestoppt – vorherige Gerätewerte unbekannt"
        # Failed local persistence must keep both memory and the journal intact.
        await self.store.async_save({"saved_settings": settings,
            "pending": None, "outcome": outcome})
        self.saved_settings = settings
        if curve is not None:
            self.curve = curve
        self.pending = None
        self.outcome = outcome

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
