"""Read-only diagnostic observations using real ZCL frames, not real hardware."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zigpy.zcl import foundation as f

from custom_components.shelly_zigbee_calibration.rpc import ShellyRpc, RpcError
from custom_components.shelly_zigbee_calibration.rpc_diagnostics import summarize
from custom_components.shelly_zigbee_calibration.runtime import DimmingRuntime
from custom_components.shelly_zigbee_calibration.device_controls import RpcCheckButton, DimmingStatusSensor
from custom_components.shelly_zigbee_calibration.diagnostics import async_get_config_entry_diagnostics
from custom_components.shelly_zigbee_calibration.wizard import WizardError
from test_calibration import FakeDevice


class DiagnosticDevice(FakeDevice):
    def __init__(self, failure=None):
        super().__init__()
        self.failure = failure
        self.data_reads = 0
        self.rpc_handler = lambda rpc: {"id": 0, "gamma": 1.2, "range_map": [6, 80],
            "name": "PRIVATE-NAME", "secret": "PRIVATE-VALUE"}

    async def request(self, **kwargs):
        header, rest = f.ZCLHeader.deserialize(kwargs['data'])
        if header.command_id == f.GeneralCommand.Read_Attributes:
            request, _ = f.GENERAL_COMMANDS[header.command_id].schema.deserialize(rest)
            attribute, = request.attribute_ids
            if attribute == 2 and self.failure == 'rxctl_missing':
                return
            if attribute == 2 and self.failure == 'empty':
                self.rx.clear()
            if attribute == 0:
                self.data_reads += 1
                if self.failure in {'data_missing', 'wrong_profile'} or (
                    self.failure == 'partial' and self.data_reads > 1):
                    if self.failure == 'wrong_profile':
                        # Plausible reply from our device on an unexpected profile.
                        self.listener_event('handle_message', self, 0x0104, 0xFC01,
                            239, 1, bytes([0x1c, 0x90, 0x14, header.tsn, 0x01]))
                    return
        before = len(self.rpc_requests)
        await super().request(**kwargs)
        if len(self.rpc_requests) > before and self.failure in {'missing_dst', 'wrong_id'}:
            frame = json.loads(self.rx)
            if self.failure == 'missing_dst':
                del frame['dst']
            else:
                frame['id'] = -1
            self.rx = bytearray(json.dumps(frame).encode())


@pytest.mark.asyncio
@pytest.mark.parametrize('failure, expected', [
    ('rxctl_missing', 'RxCtl-Antwort fehlt oder ist ungültig'),
    ('empty', 'RxCtl meldet keine Antwortdaten'),
    ('data_missing', 'RPC-Datenantwort fehlt oder ist ungültig'),
    ('partial', 'RPC-Daten unvollständig oder ungültig'),
    ('missing_dst', 'RPC-Antwort nicht zugeordnet'),
    ('wrong_id', 'RPC-Antwort nicht zugeordnet'),
    ('wrong_profile', 'RPC-Datenantwort fehlt oder ist ungültig'),
])
async def test_distinguishes_actual_transport_failures(failure, expected):
    device = DiagnosticDevice(failure)
    rpc = ShellyRpc(device, exchange_timeout=0.01, response_timeout=0.03)
    with pytest.raises(RpcError):
        await rpc.call('Light.GetConfig', {'id': 0})
    report = rpc.diagnostics
    assert summarize(report) == expected
    assert report['request_complete']
    assert len(device.rpc_requests) == 1
    assert device.rpc_requests[0]['method'] == 'Light.GetConfig'
    assert not device._listeners
    if failure == 'rxctl_missing':
        assert report['rxctl_reads_succeeded'] == report['data_read_attempts'] == 0
        assert 'RxCtl' in report['phase']
    elif failure == 'empty':
        assert report['rxctl_reads_succeeded'] > 0 and report['rxctl_last'] == 0
    else:
        assert report['rxctl_last'] is not None
        assert report['data_read_attempts'] > 0
    if failure == 'partial':
        assert report['data_bytes'] > 0 and report['data_chunks'] == 1
    if failure == 'missing_dst':
        assert report['rpc_dst_missing'] == 1 and report['rpc_frames_unmatched'] == 1
    if failure == 'wrong_id':
        assert report['rpc_id_mismatches'] == 1
    if failure == 'wrong_profile':
        assert report['ignored_zcl']['profile'] > 0
        assert report['zcl_samples'][-1]['profile'] == '0x0104'


@pytest.mark.asyncio
async def test_complete_response_records_counts_not_configuration_payload():
    device = DiagnosticDevice()
    rpc = ShellyRpc(device)
    result = await rpc.call('Light.GetConfig', {'id': 0})
    assert result['name'] == 'PRIVATE-NAME'
    report = rpc.diagnostics
    assert report['status'] == 'complete'
    assert summarize(report) == 'RPC-Antwort vollständig'
    assert report['data_chunks'] > 1 and report['rpc_frames'] == 1
    serialized = json.dumps(report)
    assert 'PRIVATE-NAME' not in serialized and 'PRIVATE-VALUE' not in serialized
    assert str(device.ieee) not in serialized
    assert len(report['zcl_samples']) <= 12
    for sample in report['zcl_samples']:
        assert len(bytes.fromhex(sample['header'])) in {3, 5}
    report['zcl_samples'].clear()
    assert rpc.diagnostics['zcl_samples']  # Export cannot mutate internal report.


def runtime_for_test():
    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    runtime = DimmingRuntime(hass, SimpleNamespace(entry_id='test'))
    runtime.store = SimpleNamespace(async_save=AsyncMock())
    return runtime


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [None, 'data_missing'])
async def test_check_button_only_reads_and_exposes_downloadable_report(failure):
    device = DiagnosticDevice(failure)
    runtime = runtime_for_test()
    rpc = ShellyRpc(device, exchange_timeout=0.01, response_timeout=0.03)
    button = RpcCheckButton('test', SimpleNamespace(id='existing'), runtime)
    status = DimmingStatusSensor('test', SimpleNamespace(id='existing'), runtime)
    with patch.object(runtime, 'rpc', return_value=rpc), patch.object(runtime, 'output', new_callable=AsyncMock) as output, patch.object(runtime, 'recover', new_callable=AsyncMock) as recover:
        await button.async_press()
    assert runtime.rpc_report is not None
    assert button.extra_state_attributes['rpc_diagnose'] == runtime.rpc_report
    assert status.extra_state_attributes['rpc_diagnose'] == runtime.rpc_report
    assert status.native_value == runtime.rpc_report['summary']
    assert not runtime.rpc_checking and not runtime.wizard.active
    assert [request['method'] for request in device.rpc_requests] == ['Light.GetConfig']
    runtime.store.async_save.assert_not_awaited()
    runtime.hass.services.async_call.assert_not_called()
    output.assert_not_awaited()
    recover.assert_not_awaited()
    report = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=runtime))
    assert report['rpc_diagnostic'] == runtime.rpc_report
    serialized = json.dumps(report)
    assert 'PRIVATE-' not in serialized and str(device.ieee) not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize('blocker', ['active', 'pending', 'cooldown', 'lock'])
async def test_diagnostic_cannot_overlap_or_trigger_recovery(blocker):
    import time
    runtime = runtime_for_test()
    if blocker == 'active':
        runtime.wizard.active = True
    elif blocker == 'pending':
        runtime.pending = {'original': True}
    elif blocker == 'cooldown':
        runtime.hardware_until = time.monotonic() + 130
    elif blocker == 'lock':
        await runtime.wizard.lock.acquire()
    try:
        with patch.object(runtime, 'rpc') as rpc, patch.object(runtime, 'recover', new_callable=AsyncMock) as recover:
            with pytest.raises(WizardError):
                await runtime.check_rpc()
            rpc.assert_not_called()
            recover.assert_not_awaited()
    finally:
        if runtime.wizard.lock.locked():
            runtime.wizard.lock.release()


@pytest.mark.asyncio
async def test_valid_transport_with_unsupported_settings_has_distinct_result():
    device = DiagnosticDevice()
    device.rpc_handler = lambda rpc: {'id': 0, 'name': 'PRIVATE-NAME'}
    runtime = runtime_for_test()
    with patch.object(runtime, 'rpc', return_value=ShellyRpc(device)):
        report = await runtime.check_rpc()
    assert report['status'] == 'complete' and report['settings_supported'] is False
    assert report['summary'] == 'RPC vollständig; Dimmparameter fehlen'


@pytest.mark.asyncio
async def test_matching_rpc_error_is_not_mistaken_for_absent_response():
    device = DiagnosticDevice()
    device.error = {'code': -104, 'message': 'Unavailable'}
    runtime = runtime_for_test()
    with patch.object(runtime, 'rpc', return_value=ShellyRpc(device)):
        report = await runtime.check_rpc()
    assert report['summary'] == 'Shelly meldet RPC-Fehler'
    assert report['rpc_error_received'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [None, 'data_missing'])
async def test_short_probe_reads_getstatus_on_same_transport_without_changes(failure):
    device = DiagnosticDevice(failure)
    device.rpc_handler = lambda rpc: {'id': 0, 'output': True, 'brightness': 50}
    runtime = runtime_for_test()
    button = RpcCheckButton('test', SimpleNamespace(id='existing'), runtime, method='Light.GetStatus')
    rpc = ShellyRpc(device, exchange_timeout=0.01, response_timeout=0.03)
    with patch.object(runtime, 'rpc', return_value=rpc), patch.object(runtime, 'output', new_callable=AsyncMock) as output, patch.object(runtime, 'recover', new_callable=AsyncMock) as recover:
        await button.async_press()
    assert [request['method'] for request in device.rpc_requests] == ['Light.GetStatus']
    assert device.rpc_requests[0]['params'] == {'id': 0}
    assert runtime.rpc_report['method'] == 'Light.GetStatus'
    assert runtime.rpc_report['settings_supported'] is None
    assert button.extra_state_attributes['rpc_diagnose'] == runtime.rpc_report
    assert button.unique_id == 'test_dimming_rpc_check_status'
    assert button.name == 'Zigbee-RPC kurz prüfen'
    assert button.device_info is None and button.device_entry.id == 'existing'
    if failure is None:
        assert runtime.rpc_report['status'] == 'complete'
        assert runtime.rpc_report['summary'] == 'RPC-Antwort vollständig'
    else:
        assert runtime.rpc_report['summary'] == 'RPC-Datenantwort fehlt oder ist ungültig'
    runtime.store.async_save.assert_not_awaited()
    runtime.hass.services.async_call.assert_not_called()
    output.assert_not_awaited()
    recover.assert_not_awaited()
    assert not device._listeners


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['Light.SetConfig', 'Light.Calibrate', 'Light.Set'])
async def test_diagnostics_refuse_any_write_or_calibration_method(method):
    runtime = runtime_for_test()
    with patch.object(runtime, 'rpc') as rpc:
        with pytest.raises(WizardError, match='nur Light.GetConfig'):
            await runtime.check_rpc(method)
    rpc.assert_not_called()
