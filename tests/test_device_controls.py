"""Direct controls on the existing device, sharing the options-flow session."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.shelly_zigbee_calibration import button, sensor
from custom_components.shelly_zigbee_calibration.device_controls import control_buttons, DimmingStatusSensor
from custom_components.shelly_zigbee_calibration.runtime import DimmingRuntime
from custom_components.shelly_zigbee_calibration.wizard import DimmingWizard
from custom_components.shelly_zigbee_calibration.curve import Curve
from test_dimming import Backend


def controls():
    backend = Backend()
    backend.wizard = DimmingWizard(backend)
    backend.notify = MagicMock()
    backend.last_error = None
    existing = SimpleNamespace(id="existing-zha-device")
    entities = {item.action: item for item in control_buttons("test", existing, backend)}
    status = DimmingStatusSensor("test", existing, backend)
    return backend, entities, status


@pytest.mark.asyncio
async def test_all_platform_entities_use_same_existing_device():
    existing = SimpleNamespace(id="existing-zha-device")
    entry = SimpleNamespace(data={"ieee": "test"}, runtime_data=MagicMock())
    add_buttons, add_sensors = MagicMock(), MagicMock()
    with patch.object(button, "get_registered_device", return_value=existing):
        await button.async_setup_entry(MagicMock(), entry, add_buttons)
    with patch.object(sensor, "get_registered_device", return_value=existing):
        await sensor.async_setup_entry(MagicMock(), entry, add_sensors)
    buttons = add_buttons.call_args.args[0]
    sensors = add_sensors.call_args.args[0]
    assert len(buttons) == 7 and len(sensors) == 1
    assert all(item.device_entry is existing and item.device_info is None for item in buttons + sensors)
    assert len({item.unique_id for item in buttons + sensors}) == 8


@pytest.mark.asyncio
async def test_device_minimum_buttons_save_native_value_and_restore_brightness():
    runtime, entities, status = controls()
    assert status.native_value == "Bereit"
    assert entities["minimum"].available and not entities["save"].available
    await entities["minimum"].async_press()
    assert status.native_value == "Mindesthelligkeit: 0.0 %"
    assert not entities["gamma"].available and entities["increase"].available
    await entities["increase"].async_press()
    await entities["increase"].async_press()
    await entities["decrease"].async_press()
    assert status.extra_state_attributes["mindestwert"] == 0.5
    assert status.extra_state_attributes["schrittweite"] == 0.5
    await entities["save"].async_press()
    assert runtime.curve == runtime.native == Curve(0.5, 1.2)
    assert runtime.restored == [runtime.original]
    assert not runtime.wizard.active and status.native_value == "Bereit"
    assert not entities["save"].available


@pytest.mark.asyncio
async def test_device_gamma_buttons_adjust_native_gamma_and_cancel():
    runtime, entities, status = controls()
    await entities["gamma"].async_press()
    await entities["increase"].async_press()
    assert runtime.native.gamma == 1.3
    assert status.native_value == "Gamma-Vorschau: 1.3"
    assert status.extra_state_attributes["schrittweite"] == 0.1
    await entities["decrease"].async_press()
    await entities["decrease"].async_press()
    assert runtime.native.gamma == 1.1
    await entities["cancel"].async_press()
    assert runtime.native == runtime.curve == Curve(6, 1.2)
    assert runtime.pending is None and status.native_value == "Bereit"


@pytest.mark.asyncio
async def test_failed_device_adjustment_rolls_back_and_reports_error():
    runtime, entities, status = controls()
    await entities["minimum"].async_press()
    original_apply = runtime.apply
    calls = 0
    async def uncertain(curve):
        nonlocal calls
        calls += 1
        await original_apply(curve)
        if calls == 1:
            raise RuntimeError("Antwort verloren")
    runtime.apply = uncertain
    with pytest.raises(HomeAssistantError, match="Antwort verloren"):
        await entities["increase"].async_press()
    assert not runtime.wizard.active
    assert runtime.native == runtime.curve == Curve(6, 1.2)
    assert status.native_value == "Fehler – Details prüfen"
    assert status.extra_state_attributes["fehler"] == "Antwort verloren"


@pytest.mark.asyncio
async def test_device_cancel_recovers_journal_without_starting_trial():
    runtime, entities, status = controls()
    runtime.pending = {"original": True}
    runtime.resolve_source = MagicMock(return_value="light.original")
    runtime.recover = AsyncMock()
    assert entities["cancel"].available
    assert status.native_value == "Wiederherstellung ausstehend"
    await entities["cancel"].async_press()
    runtime.recover.assert_awaited_once()
    assert runtime.outputs == [] and not runtime.wizard.active


@pytest.mark.asyncio
async def test_notifications_publish_after_wizard_lock_release():
    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    runtime = DimmingRuntime(hass, SimpleNamespace(entry_id="test"))
    availability = []
    runtime.listeners.add(lambda: availability.append(not runtime.wizard.lock.locked()))
    async with runtime.wizard.lock:
        runtime.notify()
        assert availability == []
    await asyncio.sleep(0)
    assert availability == [True]


@pytest.mark.asyncio
async def test_duplicate_start_does_not_cancel_running_device_trial():
    runtime, entities, _ = controls()
    await entities["minimum"].async_press()
    with pytest.raises(HomeAssistantError, match="bereits geöffnet"):
        await entities["gamma"].async_press()
    assert runtime.wizard.active and runtime.wizard.mode == "minimum"
    await entities["cancel"].async_press()
