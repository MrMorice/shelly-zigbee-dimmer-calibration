"""Test native configuration, Zigbee-only RPC, rollback and real HA dialogs."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.shelly_zigbee_calibration.curve import Curve
from custom_components.shelly_zigbee_calibration.wizard import DimmingWizard, WizardError
from custom_components.shelly_zigbee_calibration.runtime import DimmingRuntime


class Backend:
    def __init__(self):
        self.curve = Curve(6, 1.2)
        self.pending = None
        self.applied = []
        self.native = self.curve
        self.outputs = []
        self.restored = []
        self.original = {"on": True, "brightness": 83}
        self.prepare = AsyncMock()
        self.fail_restore = False
        self.report_error = MagicMock()

    async def snapshot(self):
        return dict(self.original)

    async def begin(self, snapshot):
        self.pending = snapshot

    async def apply(self, curve):
        self.native = curve
        self.applied.append(curve)

    async def output(self, value):
        self.outputs.append(value)

    async def restore(self, snapshot):
        if self.fail_restore:
            raise RuntimeError("offline")
        self.restored.append(snapshot)

    async def rollback(self):
        await self.apply(self.curve)

    async def finish(self, curve):
        if curve is not None:
            self.curve = curve
        self.pending = None


@pytest.mark.asyncio
async def test_minimum_trial_is_not_saved_until_explicit_save():
    backend = Backend()
    wizard = DimmingWizard(backend)
    token = await wizard.start("minimum")
    assert backend.outputs == [1]
    for _ in range(12):
        await wizard.adjust_minimum(token, 0.5)
    assert backend.native.minimum == 6
    assert backend.outputs[-1] == 1
    assert backend.curve == Curve(6, 1.2)
    await wizard.adjust_minimum(token, 0.5)
    await wizard.save(token)
    assert backend.curve == Curve(6.5, 1.2)
    assert backend.native == backend.curve
    assert backend.restored == [backend.original]
    assert backend.pending is None and not wizard.active


@pytest.mark.asyncio
async def test_cancel_preserves_curve_and_restores_original_light():
    backend = Backend()
    wizard = DimmingWizard(backend)
    token = await wizard.start("minimum")
    await wizard.adjust_minimum(token, 25)
    await wizard.cancel(token)
    assert backend.curve == Curve(6, 1.2)
    assert backend.restored == [backend.original]
    assert backend.pending is None
    with pytest.raises(WizardError):
        await wizard.save(token)


@pytest.mark.asyncio
async def test_gamma_sweep_moves_both_directions_and_stops():
    backend = Backend()
    wizard = DimmingWizard(backend, step_delay=0.001)
    token = await wizard.start("gamma")
    await asyncio.sleep(0.09)
    await wizard.adjust_gamma(token, 0.1)
    assert wizard.candidate.gamma == 1.3
    await wizard.save(token)
    count = len(backend.outputs)
    await asyncio.sleep(0.005)
    assert len(backend.outputs) == count
    assert max(backend.outputs) == 100
    assert any(a > b for a, b in zip(backend.outputs, backend.outputs[1:]))
    assert backend.curve == Curve(6, 1.3)


@pytest.mark.asyncio
async def test_timeout_cancels_and_restores_without_saving():
    backend = Backend()
    wizard = DimmingWizard(backend, timeout=0.01)
    token = await wizard.start("minimum")
    await wizard.adjust_minimum(token, 10)
    await asyncio.sleep(0.03)
    assert not wizard.active
    assert backend.curve == Curve(6, 1.2)
    assert backend.restored == [backend.original]


@pytest.mark.asyncio
async def test_restore_failure_retains_journal_and_old_curve():
    backend = Backend()
    wizard = DimmingWizard(backend)
    token = await wizard.start("minimum")
    await wizard.adjust_minimum(token, 10)
    backend.fail_restore = True
    with pytest.raises(WizardError, match="Abschluss"):
        await wizard.save(token)
    assert backend.pending == backend.original
    assert backend.curve == Curve(6, 1.2)
    assert not wizard.active


@pytest.mark.asyncio
async def test_duplicate_sessions_and_stale_cancel_do_not_affect_current():
    backend = Backend()
    wizard = DimmingWizard(backend)
    first = await wizard.start("minimum")
    with pytest.raises(WizardError, match="bereits geöffnet"):
        await wizard.start("gamma")
    await wizard.cancel(first)
    second = await wizard.start("minimum")
    await wizard.cancel(first)
    assert wizard.active and wizard.token == second
    await wizard.cancel(second)


@pytest.mark.asyncio
async def test_gamma_and_minimum_are_bounded():
    backend = Backend()
    wizard = DimmingWizard(backend)
    token = await wizard.start("minimum")
    await wizard.adjust_minimum(token, -1000)
    assert wizard.candidate.minimum == 0
    await wizard.adjust_minimum(token, 1000)
    assert wizard.candidate.minimum == 99.9
    await wizard.cancel(token)
    token = await wizard.start("gamma")
    await wizard.adjust_gamma(token, 1000)
    assert wizard.candidate.gamma == 4
    await wizard.adjust_gamma(token, -1000)
    assert wizard.candidate.gamma == 0.4
    await wizard.cancel(token)


@pytest.mark.asyncio
async def test_setup_and_load_never_change_device_brightness():
    runtime = DimmingRuntime(MagicMock(), SimpleNamespace(entry_id="test"))
    runtime.store = SimpleNamespace(async_load=AsyncMock(return_value={"curve": {"minimum": 5, "gamma": 2}}))
    with patch.object(runtime, "resolve_source", return_value="light.source"), patch.object(runtime, "output") as output:
        await runtime.load()
    output.assert_not_called()
    assert runtime.curve == Curve()


@pytest.mark.asyncio
async def test_auto_calibration_is_blocked_during_wizard():
    from custom_components.shelly_zigbee_calibration.button import CalibrationButton
    from homeassistant.exceptions import HomeAssistantError
    backend = Backend()
    wizard = DimmingWizard(backend)
    runtime = SimpleNamespace(wizard=wizard, pending=None)
    token = await wizard.start("minimum")
    entity = CalibrationButton("test", runtime=runtime)
    with pytest.raises(HomeAssistantError, match="Assistenten"):
        await entity.async_press()
    await wizard.cancel(token)


@pytest.mark.asyncio
async def test_real_ha_registry_resolves_original_light(tmp_path):
    from types import MappingProxyType
    from homeassistant.config_entries import ConfigEntry, ConfigEntries
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from homeassistant.core import HomeAssistant
    from custom_components.shelly_zigbee_calibration import runtime as module
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    entries = []
    for domain in ['zha', 'shelly_zigbee_calibration']:
        entry = ConfigEntry(data={"ieee": "test"}, domain=domain,
            title=domain, version=1, minor_version=1, source="user", unique_id=domain,
            options={}, discovery_keys=MappingProxyType({}), subentries_data=[])
        hass.config_entries._entries[entry.entry_id] = entry
        entries.append(entry)
    dr.async_setup(hass)
    await dr.async_load(hass, load_empty=True)
    await er.async_load(hass, load_empty=True)
    registry = dr.async_get(hass)
    entities = er.async_get(hass)
    device = registry.async_get_or_create(config_entry_id=entries[0].entry_id,
        identifiers={("zha", "test")}, name="Shelly")
    native = entities.async_get_or_create('light', 'zha', 'native',
        config_entry=entries[0], device_id=device.id)
    runtime = DimmingRuntime(hass, entries[1])
    with patch.object(module, 'get_registered_device', return_value=device), patch.object(
        module, 'get_config_entry', return_value=entries[0]):
        assert runtime.resolve_source() == native.entity_id
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_failed_save_does_not_change_in_memory_curve_or_clear_recovery():
    runtime = DimmingRuntime(MagicMock(), SimpleNamespace(entry_id='test'))
    runtime.curve = Curve(6, 1.2)
    runtime.mode = "minimum"
    runtime.pending = {'snapshot': 'original'}
    runtime.store = SimpleNamespace(async_save=AsyncMock(side_effect=OSError('disk full')))
    with pytest.raises(OSError):
        await runtime.finish(Curve(10, 2))
    assert runtime.curve == Curve(6, 1.2)
    assert runtime.pending == {'snapshot': 'original'}


@pytest.mark.asyncio
async def test_prepare_failure_aborts_before_first_config_or_brightness_write():
    backend = Backend()
    backend.prepare.side_effect = RuntimeError("Licht nicht erreichbar")
    wizard = DimmingWizard(backend)
    with pytest.raises(RuntimeError, match="Licht nicht erreichbar"):
        await wizard.start("minimum")
    assert backend.applied == [] and backend.outputs == [] and backend.pending is None
    assert not wizard.active


@pytest.mark.asyncio
async def test_native_minimum_preserves_maximum_and_cancel_restores_config():
    backend = Backend()
    backend.curve = backend.native = Curve(6, 1.2, 80)
    wizard = DimmingWizard(backend)
    token = await wizard.start("minimum")
    assert backend.native == Curve(0, 1.2, 80)
    await wizard.adjust_minimum(token, 1000)
    assert backend.native == Curve(79.9, 1.2, 80)
    await wizard.cancel(token)
    assert backend.native == Curve(6, 1.2, 80)


@pytest.mark.asyncio
async def test_initial_native_write_failure_triggers_rollback():
    backend = Backend()
    original_apply = backend.apply
    calls = 0
    async def uncertain(curve):
        nonlocal calls
        calls += 1
        await original_apply(curve)
        if calls == 1:
            raise RuntimeError("reply lost after native write")
    backend.apply = uncertain
    wizard = DimmingWizard(backend)
    with pytest.raises(RuntimeError, match="reply lost"):
        await wizard.start("minimum")
    assert backend.native == backend.curve == Curve(6, 1.2)
    assert backend.pending is None and backend.restored == [backend.original]
    assert not wizard.active


@pytest.mark.asyncio
async def test_native_rollback_failure_preserves_recovery_journal():
    backend = Backend()
    wizard = DimmingWizard(backend)
    token = await wizard.start("minimum")
    backend.apply = AsyncMock(side_effect=RuntimeError("offline"))
    with pytest.raises(WizardError, match="Abschluss"):
        await wizard.cancel(token)
    assert backend.pending == backend.original
    assert backend.curve == Curve(6, 1.2)
    assert backend.restored == []


@pytest.mark.asyncio
async def test_wizard_blocked_during_hardware_calibration_cooldown():
    import time
    runtime = DimmingRuntime(MagicMock(), SimpleNamespace(entry_id="test"))
    runtime.hardware_until = time.monotonic() + 130
    with patch.object(runtime, "rpc") as read:
        with pytest.raises(WizardError, match="Kalibrierung"):
            await runtime.wizard.start("minimum")
        read.assert_not_called()
    assert not runtime.wizard.active


@pytest.mark.asyncio
async def test_offline_unload_keeps_recovery_and_still_unloads_platform():
    from custom_components import shelly_zigbee_calibration as integration
    runtime = SimpleNamespace(close=AsyncMock(side_effect=WizardError("offline")),
        pending={"curve": "original"}, report_error=MagicMock())
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    entry = SimpleNamespace(runtime_data=runtime)
    assert await integration.async_unload_entry(hass, entry)
    assert runtime.pending == {"curve": "original"}
    runtime.report_error.assert_called_once_with("offline")
