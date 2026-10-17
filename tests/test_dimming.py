"""Test native configuration, Zigbee-only RPC, rollback and real HA dialogs."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.shelly_zigbee_calibration.curve import Curve
from custom_components.shelly_zigbee_calibration.wizard import DimmingWizard, WizardError
from custom_components.shelly_zigbee_calibration.runtime import DimmingRuntime
from custom_components.shelly_zigbee_calibration.options_flow import DimmingOptionsFlow


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

    async def finish(self, curve):
        self.curve = curve
        self.pending = None


@pytest.mark.parametrize("config", [
    {"id": 0, "gamma": 1.2, "range_map": [6, 80]},
    {"id": 0, "gamma": 1, "range_map": None},
])
def test_native_config_roundtrip(config):
    curve = Curve.from_config(config)
    expected = {**config, "range_map": config["range_map"] or [0, 100]}
    assert curve.as_config() == {k: v for k, v in expected.items() if k != "id"}


@pytest.mark.parametrize("config", [{}, {"id": 0, "gamma": 1},
    {"id": 0, "gamma": float('nan'), "range_map": [0, 100]},
    {"id": 0, "gamma": 1, "range_map": [100, 0]},
    {"id": 0, "gamma": True, "range_map": [0, 100]},
    {"id": 1, "gamma": 1, "range_map": [0, 100]}])
def test_unsupported_or_invalid_native_config_is_rejected(config):
    with pytest.raises(ValueError):
        Curve.from_config(config)


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
    with pytest.raises(WizardError, match="Wiederherstellung"):
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
async def test_recovery_restores_before_new_attempt():
    runtime = DimmingRuntime(MagicMock(), SimpleNamespace(entry_id="test"))
    runtime.curve = Curve(5, 2)
    runtime.source = "light.source"
    snapshot = {"on": False, "brightness": 25}
    runtime.pending = {"source": runtime.source, "snapshot": snapshot, "curve": runtime.curve.as_dict()}
    runtime.hass.states.get.return_value = SimpleNamespace(state="off")
    runtime.store = SimpleNamespace(async_save=AsyncMock())
    with patch.object(runtime, "resolve_source", return_value=runtime.source), patch.object(runtime, "restore", new_callable=AsyncMock) as restore, patch.object(runtime, "apply", new_callable=AsyncMock) as apply, patch.object(runtime, "read_curve", new_callable=AsyncMock, return_value=Curve(5, 2)):

        await runtime.prepare()
    restore.assert_awaited_once_with(snapshot)
    assert runtime.pending is None
    assert runtime.curve == Curve(5, 2)


@pytest.mark.asyncio
async def test_dialog_close_cancels_owned_session():
    backend = Backend()
    wizard = DimmingWizard(backend)
    token = await wizard.start("minimum")
    flow = DimmingOptionsFlow()
    flow.runtime = SimpleNamespace(wizard=wizard, report_error=MagicMock())
    flow.token = token
    tasks = []
    flow.hass = MagicMock()
    flow.hass.async_create_task.side_effect = lambda coro: tasks.append(asyncio.create_task(coro))
    flow.async_remove()
    await asyncio.gather(*tasks)
    assert not wizard.active and backend.restored == [backend.original]


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
async def test_real_options_dialog_minimum_save_and_no_changes_on_open():
    backend = Backend()
    wizard = DimmingWizard(backend)
    flow = DimmingOptionsFlow()
    flow.handler = "entry"
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_known_entry.return_value = SimpleNamespace(
        runtime_data=SimpleNamespace(wizard=wizard), options={})
    result = await flow.async_step_init()
    assert result["type"] == "menu"
    assert result["menu_options"] == ["minimum", "gamma"]
    assert backend.outputs == []
    result = await flow.async_step_minimum()
    assert result["step_id"] == "minimum" and backend.outputs == [1]
    result = await flow.async_step_brighter()
    assert result["description_placeholders"]["minimum"] == "0.5"
    assert backend.curve.minimum == 6
    result = await flow.async_step_save()
    assert result["type"] == "create_entry"
    assert backend.curve == Curve(0.5, 1.2)
    assert flow.token is None
    assert backend.restored == [backend.original]


@pytest.mark.asyncio
async def test_real_options_dialog_cancel_preserves_previous_gamma():
    backend = Backend()
    wizard = DimmingWizard(backend)
    flow = DimmingOptionsFlow()
    flow.handler = "entry"
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_known_entry.return_value = SimpleNamespace(
        runtime_data=SimpleNamespace(wizard=wizard), options={})
    await flow.async_step_init()
    await flow.async_step_gamma()
    await flow.async_step_more_gamma()
    result = await flow.async_step_cancel()
    assert result["reason"] == "wizard_cancelled"
    assert backend.curve == Curve(6, 1.2)
    assert not wizard.active and backend.restored == [backend.original]


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
    runtime.pending = {'snapshot': 'original'}
    runtime.store = SimpleNamespace(async_save=AsyncMock(side_effect=OSError('disk full')))
    with pytest.raises(OSError):
        await runtime.finish(Curve(10, 2))
    assert runtime.curve == Curve(6, 1.2)
    assert runtime.pending == {'snapshot': 'original'}


@pytest.mark.asyncio
async def test_unreadable_rpc_aborts_before_first_config_or_brightness_write():
    backend = Backend()
    backend.prepare.side_effect = RuntimeError("RPC read timeout")
    wizard = DimmingWizard(backend)
    with pytest.raises(RuntimeError, match="RPC read timeout"):
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
async def test_native_apply_requires_setconfig_success_and_getconfig_readback():
    runtime = DimmingRuntime(MagicMock(), SimpleNamespace(entry_id="test"))
    rpc = SimpleNamespace(call=AsyncMock(return_value=None))
    with patch.object(runtime, "rpc", return_value=rpc), patch.object(runtime, "read_curve", new_callable=AsyncMock, return_value=Curve(5, 2, 90)):
        await runtime.apply(Curve(5, 2, 90))
    rpc.call.assert_awaited_once_with("Light.SetConfig", {
        "id": 0, "config": {"gamma": 2, "range_map": [5, 90]}})
    with patch.object(runtime, "rpc", return_value=rpc), patch.object(runtime, "read_curve", new_callable=AsyncMock, return_value=Curve(0, 1)):
        with pytest.raises(WizardError, match="nicht bestätigt"):
            await runtime.apply(Curve(5, 2, 90))


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
    with pytest.raises(WizardError, match="Wiederherstellung"):
        await wizard.cancel(token)
    assert backend.pending == backend.original
    assert backend.curve == Curve(6, 1.2)
    assert backend.restored == []


@pytest.mark.asyncio
async def test_persistent_journal_precedes_native_write_and_contains_old_config():
    runtime = DimmingRuntime(MagicMock(), SimpleNamespace(entry_id="test"))
    runtime.source = "light.shelly"
    runtime.curve = Curve(6, 1.2, 80)
    runtime.store = SimpleNamespace(async_save=AsyncMock())
    original = {"on": True, "brightness": 25}
    await runtime.begin(original)
    runtime.store.async_save.assert_awaited_once_with({"pending": {
        "source": "light.shelly", "snapshot": original,
        "curve": {"minimum": 6, "gamma": 1.2, "maximum": 80}}})


@pytest.mark.asyncio
async def test_generic_rpc_roundtrip_actual_zcl_and_no_automatic_retry():
    from test_calibration import FakeDevice
    from custom_components.shelly_zigbee_calibration.rpc import ShellyRpc, RpcError
    device = FakeDevice()
    config = {"id": 0, "gamma": 1.2, "range_map": [6, 80]}
    device.rpc_handler = lambda rpc: config
    result = await ShellyRpc(device).call("Light.GetConfig", {"id": 0})
    assert result == config
    assert device.rpc_requests[0]["method"] == "Light.GetConfig"
    assert not device._listeners
    device.rpc_handler = lambda rpc: None
    device.drop_after_start = True
    with pytest.raises(RpcError, match="Zigbee-RPC-Antwort"):
        await ShellyRpc(device, exchange_timeout=0.01).call("Light.SetConfig", {
            "id": 0, "config": {"gamma": 2}})
    assert len(device.rpc_requests) == 2
    assert not device._listeners


@pytest.mark.asyncio
async def test_generic_rpc_rejects_errors_and_skips_foreign_mailbox_reply():
    from test_calibration import FakeDevice
    from custom_components.shelly_zigbee_calibration.rpc import ShellyRpc, RpcError
    device = FakeDevice()
    device.stale = True
    device.rpc_handler = lambda rpc: {"id": 0, "gamma": 2, "range_map": [5, 100]}
    assert (await ShellyRpc(device).call("Light.GetConfig", {"id": 0}))["gamma"] == 2
    device.stale = False
    device.error = {"code": -103, "message": "Unsupported setting"}
    with pytest.raises(RpcError, match="Unsupported setting"):
        await ShellyRpc(device).call("Light.SetConfig", {"id": 0, "config": {"gamma": 2}})
    assert not device._listeners


@pytest.mark.asyncio
async def test_wizard_native_configuration_roundtrip_over_actual_zcl():
    import copy
    from test_calibration import FakeDevice
    from custom_components.shelly_zigbee_calibration.rpc import ShellyRpc
    device = FakeDevice()
    config = {"id": 0, "gamma": 1.2, "range_map": [6, 80], "initial_state": "restore_last"}
    original = copy.deepcopy(config)
    def handle(rpc):
        if rpc["method"] == "Light.GetConfig":
            return copy.deepcopy(config)
        assert rpc["method"] == "Light.SetConfig"
        assert set(rpc["params"]["config"]) == {"gamma", "range_map"}
        config.update(rpc["params"]["config"])
        return None
    device.rpc_handler = handle
    hass = MagicMock()
    hass.states.get.return_value = SimpleNamespace(state="on", attributes={"brightness": 83})
    hass.services.async_call = AsyncMock()
    runtime = DimmingRuntime(hass, SimpleNamespace(entry_id="test"))
    runtime.store = SimpleNamespace(async_save=AsyncMock())
    with patch.object(runtime, "rpc", side_effect=lambda: ShellyRpc(device)), patch.object(runtime, "resolve_source", return_value="light.shelly"):
        token = await runtime.wizard.start("minimum")
        assert config["range_map"] == [0, 80]
        await runtime.wizard.adjust_minimum(token, 6.5)
        assert config["range_map"] == [6.5, 80]
        await runtime.wizard.save(token)
        assert config["range_map"] == [6.5, 80]
        token = await runtime.wizard.start("minimum")
        await runtime.wizard.adjust_minimum(token, 10)
        await runtime.wizard.cancel(token)
        assert config["range_map"] == [6.5, 80]
    assert config["initial_state"] == original["initial_state"]
    assert config["gamma"] == original["gamma"]
    assert runtime.pending is None
    assert not device._listeners
    assert hass.services.async_call.call_args.args == (
        "light", "turn_on", {"entity_id": "light.shelly", "brightness": 83, "transition": 0})


@pytest.mark.asyncio
async def test_firmware_without_read_response_does_not_change_native_settings():
    from test_calibration import FakeDevice
    from custom_components.shelly_zigbee_calibration.rpc import ShellyRpc, RpcError
    device = FakeDevice()
    device.drop_after_start = True
    runtime = DimmingRuntime(MagicMock(), SimpleNamespace(entry_id="test"))
    runtime.hass.states.get.return_value = SimpleNamespace(state="on")
    runtime.store = SimpleNamespace(async_save=AsyncMock())
    with patch.object(runtime, "rpc", side_effect=lambda: ShellyRpc(device, exchange_timeout=0.01)), patch.object(runtime, "resolve_source", return_value="light.shelly"):
        with pytest.raises(RpcError, match="Zigbee-RPC-Antwort"):
            await runtime.wizard.start("gamma")
    assert [rpc["method"] for rpc in device.rpc_requests] == ["Light.GetConfig"]
    runtime.hass.services.async_call.assert_not_called()
    runtime.store.async_save.assert_not_awaited()
    assert not runtime.wizard.active and runtime.pending is None


@pytest.mark.asyncio
async def test_wizard_blocked_during_hardware_calibration_cooldown():
    import time
    runtime = DimmingRuntime(MagicMock(), SimpleNamespace(entry_id="test"))
    runtime.hardware_until = time.monotonic() + 130
    with patch.object(runtime, "read_curve", new_callable=AsyncMock) as read:
        with pytest.raises(WizardError, match="Kalibrierung"):
            await runtime.wizard.start("minimum")
        read.assert_not_awaited()
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
