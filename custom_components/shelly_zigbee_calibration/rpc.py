"""Small, bounded Shelly RPC transport over Zigbee, without patching ZHA.

Use raw listener events because some zigpy releases do not deserialize responses
on Shelly's manufacturer-specific profile. No application-level retries: a lost
reply must never automatically start a second calibration.
"""
from __future__ import annotations

import asyncio
import json
import struct
import uuid

from .const import MANUFACTURER, RPC_CLUSTER, RPC_ENDPOINT, SOURCE_ENDPOINT


class RpcError(Exception):
    """An explicit protocol/device error or an uncertain command outcome."""


class ShellyRpc:
    """One serialized RPC transaction on a device's shared RPC mailbox."""

    def __init__(self, device, *, exchange_timeout=8.0, response_timeout=15.0):
        self.device = device
        self.app = device.application
        self.endpoint = device.endpoints[RPC_ENDPOINT]
        self.profile = self.endpoint.profile_id
        self.exchange_timeout = exchange_timeout
        self.response_timeout = response_timeout
        self._pending = None

    def handle_message(self, sender, profile, cluster, src_ep, dst_ep, message):
        """Receive only our exact manufacturer-specific ZCL response."""
        if (self._pending is None or sender.ieee != self.device.ieee
                or profile != self.profile or cluster != RPC_CLUSTER
                or src_ep != RPC_ENDPOINT or dst_ep != SOURCE_ENDPOINT):
            return
        tsn, expected_command, future = self._pending
        if future.done() or len(message) < 5:
            return
        control = message[0]
        if (control & 0x03 or not control & 0x04 or not control & 0x08
                or int.from_bytes(message[1:3], "little") != MANUFACTURER
                or message[3] != tsn):
            return
        command, payload = message[4], message[5:]
        if command == expected_command:
            future.set_result(payload)
        elif command == 0x0B:  # Default response instead of requested response.
            future.set_exception(RpcError("Shelly meldet eine unerwartete ZCL-Antwort: "
                                          + payload.hex()))

    async def _exchange(self, command, payload, response_command):
        tsn = self.device.get_sequence()
        future = asyncio.get_running_loop().create_future()
        self._pending = (tsn, response_command, future)
        # Global command; manufacturer-specific; suppress default responses.
        frame = struct.pack("<B H B B", 0x14, MANUFACTURER, tsn, command) + payload
        try:
            async with asyncio.timeout(self.exchange_timeout):
                await self.device.request(
                    profile=self.profile, cluster=RPC_CLUSTER,
                    src_ep=SOURCE_ENDPOINT, dst_ep=RPC_ENDPOINT,
                    sequence=tsn, data=frame, expect_reply=False, retries=0,
                )
                return await future
        finally:
            self._pending = None
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()  # Consume a response that raced a send failure.

    async def _write(self, attribute, datatype, value):
        reply = await self._exchange(
            0x02, struct.pack("<HB", attribute, datatype) + value, 0x04
        )
        if reply != b"\x00":
            raise RpcError("Zigbee-Schreibzugriff abgelehnt: " + reply.hex())

    async def _read(self, attribute, datatype):
        reply = await self._exchange(0x00, struct.pack("<H", attribute), 0x01)
        if len(reply) < 3 or int.from_bytes(reply[:2], "little") != attribute:
            raise RpcError("Unerwartete Zigbee-Attributantwort")
        if reply[2] != 0:
            raise RpcError(f"Zigbee-Lesezugriff abgelehnt: Status 0x{reply[2]:02x}")
        if len(reply) < 4 or reply[3] != datatype:
            raise RpcError("Unerwarteter Zigbee-Datentyp")
        value = reply[4:]
        if datatype == 0x23 and len(value) == 4:
            return int.from_bytes(value, "little")
        if datatype == 0x42 and value and value[0] != 0xFF:
            size = value[0]
            if len(value) == size + 1:
                return value[1:]
        raise RpcError("Unvollständige Zigbee-Attributantwort")

    async def _read_frame(self, size):
        if not 0 < size <= 8192:
            raise RpcError("Ungültige Länge der Shelly-RPC-Antwort")
        data = bytearray()
        while len(data) < size:
            chunk = await self._read(0, 0x42)
            if not chunk or len(data) + len(chunk) > size:
                raise RpcError("Ungültige RPC-Antwortstücke")
            data.extend(chunk)
        try:
            frame = json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            raise RpcError("Shelly hat keine gültige JSON-Antwort geliefert") from exc
        if not isinstance(frame, dict):
            raise RpcError("Ungültiger Shelly-RPC-Antworttyp")
        return frame

    async def calibrate(self):
        """Start calibration; return only after Shelly acknowledges the RPC."""
        request_id = uuid.uuid4().int & 0x7FFFFFFF
        source = "ha-cal-" + uuid.uuid4().hex[:8]
        payload = json.dumps({
            "id": request_id, "src": source,
            "method": "Light.Calibrate", "params": {"id": 0},
        }, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        self.app.add_listener(self)
        try:
            # TxCtl resets an incomplete outgoing frame. Serialize at integration
            # level and do not use a second RPC client on this device concurrently.
            await self._write(1, 0x23, struct.pack("<I", len(payload)))
            for offset in range(0, len(payload), 40):
                chunk = payload[offset:offset + 40]
                await self._write(0, 0x42, bytes([len(chunk)]) + chunk)
            # Calibration is asynchronous. A null result acknowledges START only.
            async with asyncio.timeout(self.response_timeout):
                stale = 0
                while True:
                    size = await self._read(2, 0x23)
                    if not size:
                        await asyncio.sleep(0.25)
                        continue
                    frame = await self._read_frame(size)
                    if frame.get("id") != request_id or frame.get("dst") != source:
                        stale += 1
                        if stale > 8:
                            raise RpcError("Zu viele fremde RPC-Antworten; anderer RPC-Client aktiv?")
                        continue
                    if "error" in frame:
                        raise RpcError("Shelly lehnt Kalibrierung ab: "
                                       + json.dumps(frame["error"], ensure_ascii=False))
                    if "result" not in frame or frame["result"] is not None:
                        raise RpcError("Unerwartete Antwort auf Light.Calibrate")
                    return
        except TimeoutError as exc:
            raise RpcError(
                "Keine vollständige Bestätigung vom Shelly. Die Kalibrierung "
                "könnte bereits laufen. Zwei Minuten warten und Lampe prüfen."
            ) from exc
        finally:
            self.app.remove_listener(self)
