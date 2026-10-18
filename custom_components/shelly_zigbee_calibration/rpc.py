"""Bounded write-only Shelly RPC transport over the existing Zigbee connection.

Use raw listener events because some zigpy releases do not deserialize responses
on Shelly's manufacturer-specific profile. No application-level retries: a lost
reply must never automatically start a second calibration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import struct
import uuid

from .const import MANUFACTURER, RPC_CLUSTER, RPC_ENDPOINT, SOURCE_ENDPOINT


_LOGGER = logging.getLogger(__name__)


class RpcError(Exception):
    """An explicit protocol/device error or an uncertain command outcome."""


class ShellyRpc:
    """One serialized RPC transaction on a device's shared RPC mailbox."""

    def __init__(self, device, *, exchange_timeout=8.0):
        self.device = device
        self.app = device.application
        self.endpoint = device.endpoints[RPC_ENDPOINT]
        self.profile = self.endpoint.profile_id
        self.exchange_timeout = exchange_timeout
        self._pending = None
        self.phase = "Vorbereitung"
        self.may_have_started = False
        self._received_headers = []

    def handle_message(self, sender, profile, cluster, src_ep, dst_ep, message):
        """Receive only our exact manufacturer-specific ZCL response."""
        if (self._pending is None or sender.ieee != self.device.ieee
                or cluster != RPC_CLUSTER):
            return
        if len(self._received_headers) < 8:
            self._received_headers.append(
                f"Profil={profile:#06x}, EP={src_ep}->{dst_ep}, Header={message[:5].hex()}"
            )
        if (profile != self.profile or src_ep != RPC_ENDPOINT
                or dst_ep != SOURCE_ENDPOINT or len(message) < 3):
            return
        tsn, expected_command, future = self._pending
        if future.done():
            return
        control = message[0]
        if control & 0x03 or not control & 0x08:
            return
        # Some devices omit the manufacturer header in global responses. The
        # sender, APS profile/cluster/endpoints and TSN still identify our request.
        offset = 1
        if control & 0x04:
            if len(message) < 5 or int.from_bytes(message[1:3], "little") != MANUFACTURER:
                return
            offset = 3
        if message[offset] != tsn:
            return
        command, payload = message[offset + 1], message[offset + 2:]
        if command == expected_command:
            future.set_result(payload)
        elif command == 0x0B and len(payload) == 2:
            if payload[0] != 0x02:
                return
            if payload[1] != 0:
                future.set_exception(RpcError(
                    f"Shelly-ZCL-Fehler bei {self.phase}: Status 0x{payload[1]:02x}"
                ))
            else:
                # ZCL write acknowledgement only, not RPC execution confirmation.
                future.set_result(b"\x00")

    async def _exchange(self, command, payload, response_command):
        tsn = self.device.get_sequence()
        future = asyncio.get_running_loop().create_future()
        self._pending = (tsn, response_command, future)
        # Match normal zigpy global requests: allow explicit default errors or
        # success responses, rather than asking the firmware to suppress them.
        frame = struct.pack("<B H B B", 0x04, MANUFACTURER, tsn, command) + payload
        _LOGGER.debug("RPC %s: ZCL command=0x%02x TSN=%d", self.phase, command, tsn)
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

    async def send(self, method, params):
        """Write one RPC request; ZCL acknowledgements do not confirm its result."""
        self.may_have_started = False
        self._received_headers = []
        request_id = uuid.uuid4().int & 0x7FFFFFFF
        source = "ha-cal-" + uuid.uuid4().hex[:8]
        payload = json.dumps({
            "id": request_id, "src": source,
            "method": method, "params": params,
        }, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        self.app.add_listener(self)
        try:
            # TxCtl resets an incomplete outgoing frame. Serialize at integration
            # level and do not use a second RPC client on this device concurrently.
            self.phase = "TxCtl schreiben (Anfragelänge)"
            await self._write(1, 0x23, struct.pack("<I", len(payload)))
            for offset in range(0, len(payload), 40):
                chunk = payload[offset:offset + 40]
                self.phase = f"Data schreiben (Bytes {offset + 1}–{offset + len(chunk)} von {len(payload)})"
                if offset + len(chunk) == len(payload):
                    self.may_have_started = True
                await self._write(0, 0x42, bytes([len(chunk)]) + chunk)
        except TimeoutError as exc:
            observed = "; ".join(self._received_headers) or "keine RPC-ZCL-Antwort empfangen"
            outcome = ("Der Shelly könnte die Anfrage bereits ausgeführt haben; Wirkung prüfen."
                       if self.may_have_started else
                       "Die vollständige Anfrage wurde noch nicht übertragen.")
            raise RpcError(
                f"Zeitüberschreitung bei {self.phase}. {outcome} Empfang: {observed}"
            ) from exc
        finally:
            self.app.remove_listener(self)

    async def calibrate(self):
        """Request hardware calibration once without reading the RPC mailbox."""
        await self.send("Light.Calibrate", {"id": 0})
