"""Dimming assistant controls attached directly to the existing ZHA device."""
from homeassistant.components.button import ButtonEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .wizard import WizardError


class DeviceControl:
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(self, ieee, device, runtime, key, name):
        self.device_entry = device
        self.runtime = runtime
        self._attr_unique_id = f"{ieee}_dimming_{key}"
        self._attr_name = name

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.runtime.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self.runtime.listeners.discard(self.async_write_ha_state))


class DimmingControlButton(DeviceControl, ButtonEntity):
    _attr_icon = "mdi:tune"

    def __init__(self, ieee, device, runtime, action, name):
        super().__init__(ieee, device, runtime, action, name)
        self.action = action

    @property
    def available(self):
        wizard = self.runtime.wizard
        if wizard.lock.locked():
            return False
        if self.action in {"minimum", "gamma"}:
            return not wizard.active
        if self.action == "cancel":
            return wizard.active or self.runtime.pending is not None
        return wizard.active

    async def async_press(self):
        wizard = self.runtime.wizard
        token = wizard.token
        try:
            if self.action in {"minimum", "gamma"}:
                await wizard.start(self.action)
            elif self.action == "cancel":
                if wizard.active:
                    await wizard.cancel(token)
                elif self.runtime.pending is not None:
                    # Recover an interrupted session without starting a new trial.
                    async with wizard.lock:
                        if wizard.active:
                            raise WizardError("Ein neuer Einstellungsversuch läuft bereits")
                        self.runtime.source = self.runtime.resolve_source()
                        await self.runtime.recover()
                else:
                    raise WizardError("Kein Einstellungsversuch aktiv")
            else:
                if not wizard.active:
                    raise WizardError("Zuerst Mindesthelligkeit oder Gamma-Vorschau starten")
                if self.action == "save":
                    await wizard.save(token)
                else:
                    direction = 1 if self.action == "increase" else -1
                    if wizard.mode == "minimum":
                        await wizard.adjust_minimum(token, direction * 0.5)
                    else:
                        await wizard.adjust_gamma(token, direction * 0.1)
        except Exception as exc:
            self.runtime.last_error = str(exc)
            self.runtime.report_error(str(exc))
            # Stop preview and roll back on a failed device-panel adjustment too.
            try:
                if wizard.active and wizard.token == token and self.action not in {"minimum", "gamma"}:
                    await wizard.cancel(token)
            except Exception as recovery_error:
                self.runtime.report_error(str(recovery_error))
            raise HomeAssistantError(str(exc)) from exc
        else:
            self.runtime.last_error = None
        finally:
            self.runtime.notify()


class RpcCheckButton(DeviceControl, ButtonEntity):
    action = "rpc_check"
    _attr_icon = "mdi:connection"

    def __init__(self, ieee, device, runtime, *, method="Light.GetConfig"):
        self.method = method
        if method == "Light.GetStatus":
            self.action = "rpc_check_status"
            name = "Zigbee-RPC kurz prüfen"
        else:
            self.action = "rpc_check"
            name = "Zigbee-RPC prüfen"
        super().__init__(ieee, device, runtime, self.action, name)

    @property
    def available(self):
        wizard = self.runtime.wizard
        return not wizard.active and not wizard.lock.locked() and self.runtime.pending is None

    @property
    def extra_state_attributes(self):
        return {"rpc_diagnose": self.runtime.rpc_report}

    async def async_press(self):
        try:
            await self.runtime.check_rpc(self.method)
        except Exception as exc:
            raise HomeAssistantError(str(exc)) from exc


class DimmingStatusSensor(DeviceControl, SensorEntity):
    _attr_icon = "mdi:lightbulb-auto"

    def __init__(self, ieee, device, runtime):
        super().__init__(ieee, device, runtime, "status", "Dimmkurven-Status")

    @property
    def native_value(self):
        runtime = self.runtime
        wizard = runtime.wizard
        if getattr(runtime, "rpc_checking", False):
            return "Zigbee-RPC-Prüfung läuft"
        if runtime.last_error:
            return "Fehler – Details prüfen"
        if wizard.active:
            curve = wizard.candidate
            if wizard.mode == "minimum":
                return f"Mindesthelligkeit: {curve.minimum:.1f} %"
            return f"Gamma-Vorschau: {curve.gamma:.1f}"
        if runtime.pending is not None:
            return "Wiederherstellung ausstehend"
        if getattr(runtime, "rpc_report", None):
            return runtime.rpc_report["summary"]
        return "Bereit"

    @property
    def extra_state_attributes(self):
        wizard = self.runtime.wizard
        curve = wizard.candidate if wizard.active else None
        return {
            "rpc_diagnose": getattr(self.runtime, "rpc_report", None),
            "modus": wizard.mode if wizard.active else None,
            "mindestwert": curve.minimum if curve else None,
            "gamma": curve.gamma if curve else None,
            "schrittweite": (0.5 if wizard.mode == "minimum" else 0.1) if wizard.active else None,
            "fehler": self.runtime.last_error or wizard.error,
            "wiederherstellung_ausstehend": self.runtime.pending is not None and not wizard.active,
        }


def control_buttons(ieee, device, runtime):
    return [
        RpcCheckButton(ieee, device, runtime),
        RpcCheckButton(ieee, device, runtime, method="Light.GetStatus"),
    ] + [DimmingControlButton(ieee, device, runtime, action, name) for action, name in (
        ("minimum", "Mindesthelligkeit suchen"),
        ("gamma", "Gamma-Vorschau starten"),
        ("increase", "Dimmwert erhöhen (+)"),
        ("decrease", "Dimmwert senken (−)"),
        ("save", "Dimmwerte speichern"),
        ("cancel", "Dimmversuch abbrechen"),
    )]
