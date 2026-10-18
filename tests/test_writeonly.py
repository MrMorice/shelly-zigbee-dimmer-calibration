"""Write-only device trials, persistence, recovery and upgrade cleanup."""
import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zigpy.zcl import foundation as f

from custom_components.shelly_zigbee_calibration.curve import Curve, validate_settings
from custom_components.shelly_zigbee_calibration.runtime import DimmingRuntime
from custom_components.shelly_zigbee_calibration.rpc import ShellyRpc
from custom_components.shelly_zigbee_calibration.wizard import WizardError
from custom_components.shelly_zigbee_calibration.options_flow import DimmingOptionsFlow
from test_calibration import FakeDevice


def wired_runtime(*, saved=None, options=None):
    device = FakeDevice()
    native = {'range_map': [5, 87], 'gamma': 2.4, 'name': 'unchanged'}
    def handle(rpc):
        assert rpc['method'] == 'Light.SetConfig'
        assert rpc['params']['id'] == 0
        native.update(rpc['params']['config'])
        return None
    device.rpc_handler = handle
    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    hass.states.get.return_value = SimpleNamespace(state='on', attributes={'brightness': 83})
    hass.services.async_call = AsyncMock()
    entry = SimpleNamespace(entry_id='test', options=options or {})
    runtime = DimmingRuntime(hass, entry)
    runtime.saved_settings = copy.deepcopy(saved or {})
    runtime.store = SimpleNamespace(async_load=AsyncMock(return_value={}), async_save=AsyncMock())
    runtime.resolve_source = lambda: 'light.original'
    runtime.rpc = lambda: ShellyRpc(device, exchange_timeout=0.01)
    return runtime, device, native


def assert_write_only(device):
    assert device.requests
    for request in device.requests:
        header, _ = f.ZCLHeader.deserialize(request['data'])
        assert header.command_id == f.GeneralCommand.Write_Attributes
    assert not device._listeners


@pytest.mark.asyncio
async def test_first_minimum_cancel_keeps_trial_values_and_never_invents_backup():
    runtime, device, native = wired_runtime(options={'maximum': 90})
    token = await runtime.wizard.start('minimum')
    assert native['range_map'] == [0, 90] and native['gamma'] == 2.4
    assert runtime.pending['restore_settings'] == {}
    await runtime.wizard.adjust_minimum(token, 2)
    before = len(device.rpc_requests)
    await runtime.wizard.cancel(token)
    assert len(device.rpc_requests) == before
    assert native['range_map'] == [2, 90]
    assert runtime.saved_settings == {} and runtime.pending is None
    assert runtime.outcome == 'Gestoppt – vorherige Gerätewerte unbekannt'
    assert runtime.last_sent['device_values_confirmed'] is False
    assert runtime.hass.services.async_call.call_args.args[2]['brightness'] == 83
    assert all(set(r['params']['config']) == {'range_map'} for r in device.rpc_requests)
    assert_write_only(device)


@pytest.mark.asyncio
async def test_gamma_trial_save_and_later_cancel_only_change_gamma():
    runtime, device, native = wired_runtime(options={'initial_gamma': 1.3})
    token = await runtime.wizard.start('gamma')
    assert native['gamma'] == 1.3 and native['range_map'] == [5, 87]
    await runtime.wizard.adjust_gamma(token, 0.1)
    await runtime.wizard.save(token)
    assert runtime.saved_settings == {'gamma': 1.4}
    assert runtime.outcome == 'Werte gesendet und in HA gespeichert'
    token = await runtime.wizard.start('gamma')
    assert native['gamma'] == 1.4  # Last saved value takes precedence over initial value.
    await runtime.wizard.adjust_gamma(token, 1)
    await runtime.wizard.cancel(token)
    assert native['gamma'] == 1.4 and native['range_map'] == [5, 87]
    assert runtime.outcome == 'Gespeicherte Werte erneut gesendet'
    assert all(set(r['params']['config']) == {'gamma'} for r in device.rpc_requests)
    assert_write_only(device)


@pytest.mark.asyncio
async def test_first_gamma_cancel_does_not_reset_unknown_value_to_default():
    runtime, device, native = wired_runtime()
    token = await runtime.wizard.start('gamma')
    await runtime.wizard.adjust_gamma(token, 0.2)
    before = len(device.rpc_requests)
    await runtime.wizard.cancel(token)
    assert len(device.rpc_requests) == before
    assert native['gamma'] == 1.2  # Last trial remains, never falsely restore unknown 2.4.
    assert runtime.saved_settings == {}


@pytest.mark.asyncio
async def test_minimum_save_persists_partial_values_and_preserves_other_saved_parameter():
    runtime, device, native = wired_runtime(saved={'gamma': 1.5}, options={'maximum': 80})
    token = await runtime.wizard.start('minimum')
    await runtime.wizard.adjust_minimum(token, 6)
    await runtime.wizard.save(token)
    assert native == {'range_map': [6, 80], 'gamma': 2.4, 'name': 'unchanged'}
    assert runtime.saved_settings == {'range_map': [6, 80], 'gamma': 1.5}
    stored = runtime.store.async_save.call_args.args[0]
    assert stored['saved_settings'] == runtime.saved_settings and stored['pending'] is None
    assert runtime.last_sent['values'] == {'range_map': [6, 80]}
    assert_write_only(device)


@pytest.mark.asyncio
async def test_cancel_uses_ha_saved_values_even_if_device_was_changed_elsewhere():
    runtime, device, native = wired_runtime(saved={'range_map': [6, 80], 'gamma': 1.5}, options={'maximum': 90})
    token = await runtime.wizard.start('minimum')
    await runtime.wizard.adjust_minimum(token, 10)
    await runtime.wizard.cancel(token)
    assert native['range_map'] == [6, 80]
    assert native['gamma'] == 2.4  # Not overwritten with unrelated saved gamma.
    assert runtime.last_sent['device_values_confirmed'] is False
    assert_write_only(device)


@pytest.mark.asyncio
async def test_acknowledged_but_rejected_rpc_is_never_claimed_as_confirmed():
    runtime, device, native = wired_runtime()
    device.error = {'code': -103, 'message': 'Unsupported gamma'}
    token = await runtime.wizard.start('gamma')
    await runtime.wizard.save(token)
    assert native['gamma'] == 2.4  # Simulated device rejects RPC, despite successful ZCL writes.
    assert runtime.saved_settings == {'gamma': 1.0}
    assert runtime.last_sent['device_values_confirmed'] is False
    assert runtime.outcome == 'Werte gesendet und in HA gespeichert'
    assert_write_only(device)


@pytest.mark.asyncio
async def test_load_keeps_saved_partial_settings_without_network_side_effects():
    runtime, device, native = wired_runtime()
    runtime.store.async_load.return_value = {'saved_settings': {'gamma': 1.7}, 'pending': None}
    await runtime.load()
    assert runtime.saved_settings == {'gamma': 1.7}
    assert not device.requests
    runtime.hass.services.async_call.assert_not_called()
    runtime.store.async_save.assert_not_awaited()


@pytest.mark.asyncio
async def test_journal_is_written_before_first_device_change():
    runtime, device, native = wired_runtime()
    runtime.store.async_save.side_effect = OSError('disk full')
    with pytest.raises(OSError):
        await runtime.wizard.start('minimum')
    assert not device.requests and runtime.pending is None
    runtime.hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_failed_local_save_retains_backup_for_later_recovery():
    runtime, device, native = wired_runtime(saved={'range_map': [6, 80]})
    token = await runtime.wizard.start('minimum')
    await runtime.wizard.adjust_minimum(token, 10)
    runtime.store.async_save.side_effect = OSError('disk full')
    with pytest.raises(WizardError, match='Abschluss'):
        await runtime.wizard.save(token)
    assert runtime.saved_settings == {'range_map': [6, 80]}
    assert runtime.pending['restore_settings'] == {'range_map': [6, 80]}
    runtime.store.async_save.side_effect = None
    await runtime.recover()
    assert native['range_map'] == [6, 80] and runtime.pending is None


@pytest.mark.asyncio
async def test_recovery_without_prior_values_restores_only_lamp():
    runtime, device, native = wired_runtime()
    runtime.source = 'light.original'
    runtime.pending = {'source': runtime.source, 'mode': 'minimum',
        'restore_settings': {}, 'snapshot': {'on': False, 'brightness': None}}
    await runtime.recover()
    assert not device.requests and runtime.pending is None
    assert runtime.hass.services.async_call.call_args.args[:2] == ('light', 'turn_off')
    assert runtime.outcome == 'Gestoppt – vorherige Gerätewerte unbekannt'


@pytest.mark.asyncio
async def test_legacy_native_journal_is_recovered_without_rpc_reads():
    runtime, device, native = wired_runtime()
    runtime.source = 'light.original'
    runtime.pending = {'source': runtime.source, 'curve': Curve(7, 1.6, 85).as_dict(),
        'snapshot': {'on': True, 'brightness': 83}}
    await runtime.recover()
    assert native['range_map'] == [7, 85] and native['gamma'] == 1.6
    assert runtime.pending is None
    assert_write_only(device)


@pytest.mark.asyncio
async def test_wrong_recovery_source_never_changes_another_light():
    runtime, device, native = wired_runtime()
    runtime.source = 'light.changed'
    runtime.pending = {'source': 'light.original', 'restore_settings': {'gamma': 1.5},
        'snapshot': {'on': True, 'brightness': 83}}
    with pytest.raises(WizardError, match='geändert'):
        await runtime.recover()
    assert runtime.pending is not None and not device.requests
    runtime.hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_first_trial_timeout_stops_without_saving_or_inventing_baseline():
    runtime, device, native = wired_runtime()
    runtime.wizard.timeout = 0.01
    token = await runtime.wizard.start('minimum')
    await runtime.wizard.adjust_minimum(token, 3)
    await asyncio.sleep(0.03)
    assert not runtime.wizard.active and runtime.pending is None
    assert runtime.saved_settings == {} and native['range_map'] == [3, 100]


@pytest.mark.asyncio
async def test_local_options_do_not_send_and_validate_starting_values():
    runtime, device, native = wired_runtime()
    flow = DimmingOptionsFlow()
    flow.handler = 'entry'
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_known_entry.return_value = SimpleNamespace(
        runtime_data=runtime, options={})
    result = await flow.async_step_init()
    assert result['type'] == 'form'
    result = await flow.async_step_init({'maximum': 80, 'initial_gamma': 1.6})
    assert result['type'] == 'create_entry' and result['data']['maximum'] == 80
    result = await flow.async_step_init({'maximum': 0, 'initial_gamma': 1.6})
    assert result['errors']['base'] == 'invalid_values'
    assert not device.requests and runtime.saved_settings == {}
    runtime.hass.services.async_call.assert_not_called()


@pytest.mark.parametrize('values', [{'gamma': float('nan')}, {'range_map': [100, 0]},
    {'range_map': [True, 100]}, {'unknown': 1}, {'gamma': 8}])
def test_invalid_saved_settings_rejected(values):
    with pytest.raises(ValueError):
        validate_settings(values)


@pytest.mark.asyncio
async def test_upgrade_cleanup_removes_only_retired_probe_entities_from_own_entry(tmp_path):
    from types import MappingProxyType
    from homeassistant.config_entries import ConfigEntry, ConfigEntries
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from homeassistant.core import HomeAssistant
    from custom_components.shelly_zigbee_calibration.helpers import remove_obsolete_diagnostics
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    entries = []
    for domain in ['zha', 'shelly_zigbee_calibration', 'shelly_zigbee_calibration']:
        entry = ConfigEntry(data={'ieee': 'test'}, domain=domain, title=domain,
            version=1, minor_version=1, source='user', unique_id=str(len(entries)),
            options={}, discovery_keys=MappingProxyType({}), subentries_data=[])
        hass.config_entries._entries[entry.entry_id] = entry
        entries.append(entry)
    dr.async_setup(hass)
    await dr.async_load(hass, load_empty=True)
    await er.async_load(hass, load_empty=True)
    devices, entities = dr.async_get(hass), er.async_get(hass)
    device = devices.async_get_or_create(config_entry_id=entries[0].entry_id,
        identifiers={('zha', 'test')}, name='Shelly')
    old = entities.async_get_or_create('button', 'shelly_zigbee_calibration',
        'test_dimming_rpc_check', config_entry=entries[1], device_id=device.id)
    other = entities.async_get_or_create('button', 'shelly_zigbee_calibration',
        'test_dimming_rpc_check_status', config_entry=entries[2], device_id=device.id)
    keep = entities.async_get_or_create('button', 'shelly_zigbee_calibration',
        'test_dimming_save', config_entry=entries[1], device_id=device.id)
    light = entities.async_get_or_create('light', 'zha', 'native',
        config_entry=entries[0], device_id=device.id)
    remove_obsolete_diagnostics(hass, entries[1])
    remove_obsolete_diagnostics(hass, entries[1])  # Repeating cleanup is harmless.
    assert entities.async_get(old.entity_id) is None
    assert entities.async_get(other.entity_id) is not None
    assert entities.async_get(keep.entity_id).device_id == device.id
    assert entities.async_get(light.entity_id).device_id == device.id
    assert devices.async_get(device.id) is not None
    # Once the second retired probe is genuinely owned by our entry, remove it too.
    entities.async_remove(other.entity_id)
    second = entities.async_get_or_create('button', 'shelly_zigbee_calibration',
        'test_dimming_rpc_check_status', config_entry=entries[1], device_id=device.id)
    remove_obsolete_diagnostics(hass, entries[1])
    assert entities.async_get(second.entity_id) is None
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_options_cannot_change_starting_values_during_trial():
    runtime, device, native = wired_runtime()
    token = await runtime.wizard.start('minimum')
    flow = DimmingOptionsFlow()
    flow.handler = 'entry'
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_known_entry.return_value = SimpleNamespace(
        runtime_data=runtime, options={})
    result = await flow.async_step_init({'maximum': 80, 'initial_gamma': 1.6})
    assert result['type'] == 'abort' and result['reason'] == 'trial_active'
    assert runtime.wizard.active
    await runtime.wizard.cancel(token)


@pytest.mark.asyncio
async def test_diagnostics_and_status_label_local_values_as_unconfirmed():
    from custom_components.shelly_zigbee_calibration.diagnostics import async_get_config_entry_diagnostics
    from custom_components.shelly_zigbee_calibration.device_controls import DimmingStatusSensor
    runtime, device, native = wired_runtime()
    token = await runtime.wizard.start('minimum')
    await runtime.wizard.adjust_minimum(token, 5)
    await runtime.wizard.save(token)
    report = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=runtime))
    status = DimmingStatusSensor('test', SimpleNamespace(id='same-device'), runtime)
    assert report['saved_settings'] == {'range_map': [5, 100]}
    assert report['device_values_confirmed'] is False and report['mode'] == 'write_only'
    assert status.extra_state_attributes['geraetewerte_bestaetigt'] is False
    assert status.extra_state_attributes['in_ha_gespeichert'] == {'range_map': [5, 100]}
    assert 'rpc_diagnose' not in status.extra_state_attributes
