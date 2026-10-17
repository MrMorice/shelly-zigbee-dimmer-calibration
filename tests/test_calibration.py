"""Real HA/zigpy imports; simulated remote device, no physical hardware."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import json

import pytest
import zigpy.types as t
from zigpy.util import ListenableMixin
from zigpy.zcl import foundation as f

from custom_components.shelly_zigbee_calibration import button, config_flow
from custom_components.shelly_zigbee_calibration.helpers import is_supported
from custom_components.shelly_zigbee_calibration.rpc import RpcError, ShellyRpc
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant


class FakeDevice(ListenableMixin):
    """Shelly RPC mailbox speaking actual zigpy ZCL encodings."""
    def __init__(self):
        super().__init__()
        self.application = self
        self.ieee = t.EUI64.convert("00:11:22:33:44:55:66:77")
        self.manufacturer = "Shelly"
        self.model = "S4DM-0A101WWL"
        self.endpoints = {239: SimpleNamespace(profile_id=0xC001, in_clusters={0xFC01: None})}
        self.sequence = 0
        self.tx = bytearray()
        self.tx_size = 0
        self.rx = bytearray()
        self.requests = []
        self.rpc_requests = []
        self.error = None
        self.drop = False
        self.drop_after_start = False
        self.write_failure = False
        self.stale = False
        self.actual_reply = None

    def get_sequence(self):
        self.sequence = (self.sequence + 1) % 256
        return self.sequence

    async def request(self, **kwargs):
        self.requests.append(kwargs)
        assert kwargs["profile"] == 0xC001
        assert kwargs["cluster"] == 0xFC01
        assert kwargs["src_ep"] == 1 and kwargs["dst_ep"] == 239
        assert kwargs["expect_reply"] is False and kwargs["retries"] == 0
        hdr, rest = f.ZCLHeader.deserialize(kwargs["data"])
        assert hdr.manufacturer == 0x1490
        assert hdr.frame_control.direction == f.Direction.Client_to_Server
        req, remaining = f.GENERAL_COMMANDS[hdr.command_id].schema.deserialize(rest)
        assert not remaining
        if self.drop:
            return
        if hdr.command_id == f.GeneralCommand.Write_Attributes:
            record, = req.attributes
            if self.write_failure:
                response = f.WriteAttributesResponseSchema(status_records=[
                    f.WriteAttributesStatusRecord(status=f.Status.READ_ONLY, attrid=record.attrid)
                ])
            else:
                if record.attrid == 1:
                    self.tx_size = int(record.value.value)
                    self.tx.clear()
                else:
                    self.tx.extend(str(record.value.value).encode("ascii"))
                    if len(self.tx) == self.tx_size:
                        rpc = json.loads(self.tx)
                        self.rpc_requests.append(rpc)
                        frame = {"id": rpc["id"], "dst": rpc["src"], "src": "shellydimmerg4-test"}
                        frame.update({"error": self.error} if self.error else {"result": None})
                        self.rx = bytearray(json.dumps(frame).encode())
                        if self.stale:
                            self.actual_reply = self.rx
                            self.rx = bytearray(b'{"id":-1,"dst":"old-client","result":null}')
                response = f.WriteAttributesResponseSchema(status_records=[
                    f.WriteAttributesStatusRecord(status=f.Status.SUCCESS)
                ])
            cmd = f.GeneralCommand.Write_Attributes_rsp
        else:
            assert hdr.command_id == f.GeneralCommand.Read_Attributes
            if self.drop_after_start:
                return
            attrid, = req.attribute_ids
            if attrid == 2:
                value = f.TypeValue(type=0x23, value=t.uint32_t(len(self.rx)))
            else:
                chunk = bytes(self.rx[:23])
                del self.rx[:23]
                value = f.TypeValue(type=0x42, value=t.CharacterString(chunk.decode()))
                if not self.rx and self.actual_reply is not None:
                    self.rx, self.actual_reply = self.actual_reply, None
            response = f.ReadAttributesResponse(status_records=[
                f.ReadAttributeRecord(attrid=attrid, status=f.Status.SUCCESS, value=value)
            ])
            cmd = f.GeneralCommand.Read_Attributes_rsp
        header = f.ZCLHeader.general(
            tsn=hdr.tsn, command_id=cmd, manufacturer=0x1490,
            direction=f.Direction.Server_to_Client,
        )
        self.listener_event("handle_message", self, 0xC001, 0xFC01, 239, 1,
                            header.serialize() + response.serialize())


@pytest.mark.asyncio
async def test_calibration_wire_roundtrip():
    device = FakeDevice()
    await ShellyRpc(device).calibrate()
    assert len(device.rpc_requests) == 1
    assert device.rpc_requests[0]["method"] == "Light.Calibrate"
    assert device.rpc_requests[0]["params"] == {"id": 0}
    assert not device._listeners


@pytest.mark.asyncio
async def test_stale_mailbox_response_is_not_accepted():
    device = FakeDevice()
    device.stale = True
    await ShellyRpc(device).calibrate()
    assert len(device.rpc_requests) == 1


@pytest.mark.asyncio
async def test_rpc_device_error():
    device = FakeDevice()
    device.error = {"code": -114, "message": "Calibration in progress"}
    with pytest.raises(RpcError, match="-114"):
        await ShellyRpc(device).calibrate()
    assert not device._listeners


@pytest.mark.asyncio
async def test_write_rejected_never_starts_calibration():
    device = FakeDevice()
    device.write_failure = True
    with pytest.raises(RpcError, match="Schreibzugriff"):
        await ShellyRpc(device).calibrate()
    assert not device.rpc_requests
    assert not device._listeners


@pytest.mark.asyncio
@pytest.mark.parametrize("after_start", [False, True])
async def test_no_automatic_retry_on_lost_response(after_start):
    device = FakeDevice()
    device.drop = not after_start
    device.drop_after_start = after_start
    with pytest.raises(RpcError, match="könnte bereits laufen"):
        await ShellyRpc(device, exchange_timeout=0.01).calibrate()
    assert len(device.rpc_requests) == int(after_start)
    assert not device._listeners


@pytest.mark.asyncio
async def test_cancellation_removes_listener():
    device = FakeDevice()
    device.drop = True
    task = asyncio.create_task(ShellyRpc(device).calibrate())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not device._listeners


@pytest.mark.asyncio
async def test_reply_from_wrong_device_is_ignored():
    device = FakeDevice()
    client = ShellyRpc(device)
    future = asyncio.get_running_loop().create_future()
    client._pending = (3, 4, future)
    wrong = SimpleNamespace(ieee="different")
    reply = bytes.fromhex("1c9014030400")
    client.handle_message(wrong, 0xC001, 0xFC01, 239, 1, reply)
    assert not future.done()
    client.handle_message(device, 0xC001, 0xFC01, 239, 1, reply)
    assert future.result() == b"\x00"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [b"", b"\x02\x00\x00\x23\x01", b"\x02\x00\x86"])
async def test_invalid_attribute_response(raw):
    client = ShellyRpc(FakeDevice())
    client._exchange = AsyncMock(return_value=raw)
    with pytest.raises(RpcError):
        await client._read(2, 0x23)


@pytest.mark.asyncio
async def test_empty_response_chunk_rejected():
    client = ShellyRpc(FakeDevice())
    client._read = AsyncMock(return_value=b"")
    with pytest.raises(RpcError, match="Antwortstücke"):
        await client._read_frame(10)


def test_model_profile_and_cluster_guard():
    device = FakeDevice()
    assert is_supported(device)
    device.model = "Shelly 1PM Gen4"
    assert not is_supported(device)
    device.model = "S4DM-0A101WWL"
    device.endpoints[239].profile_id = 0x0104
    assert not is_supported(device)


@pytest.mark.asyncio
async def test_button_ack_and_duplicate_protection():
    entity = button.CalibrationButton(str(FakeDevice().ieee))
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    device = FakeDevice()
    with patch.object(button, "resolve_device", return_value=device):
        await entity.async_press()
        assert "Start vom Shelly bestätigt" in entity.extra_state_attributes["ergebnis"]
        with pytest.raises(HomeAssistantError, match="130 Sekunden"):
            await entity.async_press()
    assert len(device.rpc_requests) == 1


@pytest.mark.asyncio
async def test_button_timeout_does_not_claim_success_and_blocks_retries():
    entity = button.CalibrationButton(str(FakeDevice().ieee))
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    with patch.object(button, "resolve_device", return_value=FakeDevice()), patch.object(
        button.ShellyRpc, "calibrate", side_effect=RpcError("Unbestätigt")
    ):
        with pytest.raises(HomeAssistantError, match="Unbestätigt"):
            await entity.async_press()
        assert entity.extra_state_attributes["ergebnis"] == "Unbestätigt"
        with pytest.raises(HomeAssistantError, match="130 Sekunden"):
            await entity.async_press()


@pytest.mark.asyncio
async def test_real_ha_config_flow_form_and_schema(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    flow = config_flow.CalibrationConfigFlow()
    flow.hass = hass
    candidates = {"00:11:22:33:44:55:66:77": "Testdimmer"}
    with patch.object(config_flow, "get_candidates", return_value=candidates):
        result = await flow.async_step_user()
    assert result["type"] == "form"
    assert result["data_schema"]({"ieee": next(iter(candidates))})


@pytest.mark.asyncio
async def test_no_device_config_abort():
    flow = config_flow.CalibrationConfigFlow()
    flow.hass = MagicMock()
    with patch.object(config_flow, "get_candidates", return_value={}):
        result = await flow.async_step_user()
    assert result["reason"] == "no_devices"


@pytest.mark.asyncio
async def test_setup_only_registers_platform_and_never_calibrates():
    from custom_components import shelly_zigbee_calibration as integration
    hass = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    entry = SimpleNamespace(data={"ieee": "test"})
    with patch.object(integration, "resolve_device", return_value=FakeDevice()), patch.object(
        ShellyRpc, "calibrate", new_callable=AsyncMock
    ) as calibrate:
        assert await integration.async_setup_entry(hass, entry)
        calibrate.assert_not_called()
        hass.config_entries.async_forward_entry_setups.assert_awaited_once()


@pytest.mark.asyncio
async def test_busy_button_rejects_concurrent_press():
    entity = button.CalibrationButton("test")
    async with entity._lock:
        with pytest.raises(HomeAssistantError, match="läuft bereits"):
            await entity.async_press()
