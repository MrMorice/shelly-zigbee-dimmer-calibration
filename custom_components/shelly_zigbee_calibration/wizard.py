"""Interactive preview with rollback, timeout and persistent recovery journal."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import uuid

from .curve import Curve


class WizardError(Exception):
    """An adjustment could not be completed safely."""


class DimmingWizard:
    """Backend implements snapshot, output, restore, begin and finish.

    Preview changes native settings temporarily. A journal exists before the first
    write. Cancel resends locally saved values if known, then restores brightness.
    No RPC read is needed, and no native configuration is claimed as verified.
    """

    def __init__(self, backend, *, step_delay=0.6, timeout=300):
        self.backend = backend
        self.step_delay = step_delay
        self.timeout = timeout
        self.lock = asyncio.Lock()
        self.active = False
        self.token = None
        self.mode = None
        self.candidate = Curve()
        self.original = None
        self.level = 0.0
        self.error = None
        self._sweep_task = None
        self._timeout_task = None

    def _notify(self):
        notify = getattr(self.backend, "notify", None)
        if notify is not None:
            notify()

    async def start(self, mode):
        if mode not in {"minimum", "gamma"}:
            raise WizardError("Unbekannter Einstellungsmodus")
        async with self.lock:
            if self.active:
                raise WizardError("Ein Einstellungsassistent ist bereits geöffnet")
            await self.backend.prepare(mode)
            original = await self.backend.snapshot()
            await self.backend.begin(original)
            self.original = original
            self.candidate = self.backend.curve
            if mode == "minimum":
                self.candidate = replace(self.candidate, minimum=0.0)
            self.mode = mode
            self.token = uuid.uuid4().hex
            self.active = True
            self.error = None
            self.level = 0.0
            try:
                if mode == "minimum":
                    await self.backend.apply(self.candidate)
                    await self.backend.output(1.0)
                else:
                    await self.backend.apply(self.candidate)
                    await self.backend.output(0.0)
            except Exception:
                await self._finish_locked(False)
                raise
            self._timeout_task = asyncio.create_task(self._expire())
            if mode == "gamma":
                self._sweep_task = asyncio.create_task(self._sweep())
            self._notify()
            return self.token

    def _require(self, token):
        if not self.active or token != self.token:
            raise WizardError("Der Einstellungsversuch ist beendet. Bitte neu öffnen.")

    async def adjust_minimum(self, token, delta):
        async with self.lock:
            self._require(token)
            if self.mode != "minimum":
                raise WizardError("Mindestwertsuche ist nicht aktiv")
            value = round(max(0.0, min(max(0.0, self.candidate.maximum - 0.1), self.candidate.minimum + delta)), 1)
            candidate = replace(self.candidate, minimum=value)
            if candidate != self.candidate:
                await self.backend.apply(candidate)
            await self.backend.output(1.0)
            self.candidate = candidate
            self.level = 1.0
            self._notify()

    async def adjust_gamma(self, token, delta):
        async with self.lock:
            self._require(token)
            if self.mode != "gamma":
                raise WizardError("Gamma-Vorschau ist nicht aktiv")
            gamma = round(max(0.4, min(4.0, self.candidate.gamma + delta)), 1)
            candidate = replace(self.candidate, gamma=gamma)
            if candidate != self.candidate:
                await self.backend.apply(candidate)
            await self.backend.output(self.level)
            self.candidate = candidate
            self._notify()

    async def save(self, token):
        async with self.lock:
            self._require(token)
            await self._finish_locked(True)

    async def cancel(self, token=None):
        async with self.lock:
            if not self.active or (token is not None and self.token != token):
                return
            await self._finish_locked(False)

    async def _finish_locked(self, commit):
        current = asyncio.current_task()
        tasks = [task for task in (self._sweep_task, self._timeout_task)
                 if task is not None and task is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._sweep_task = self._timeout_task = None
        # A failed restore leaves the journal intact and prevents new previews.
        self.active = False
        self.token = None
        try:
            if commit:
                await self.backend.apply(self.candidate)
            else:
                await self.backend.rollback()
            await self.backend.restore(self.original)
            await self.backend.finish(self.candidate if commit else None)
        except Exception as exc:
            self.error = f"Abschluss nicht vollständig: {exc}"
            raise WizardError(self.error) from exc
        finally:
            self._notify()

    async def _expire(self):
        await asyncio.sleep(self.timeout)
        try:
            await self.cancel()
        except Exception as exc:
            self.error = str(exc)
            self.backend.report_error(self.error)

    async def _sweep(self):
        # A full up/down cycle takes about 24 seconds, plus Zigbee command time.
        sequence = [*range(1, 101, 5), 100, *range(96, 0, -5)]
        try:
            while True:
                for level in sequence:
                    async with self.lock:
                        if not self.active:
                            return
                        await self.backend.output(level)
                        self.level = level
                    await asyncio.sleep(self.step_delay)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = f"Vorschau fehlgeschlagen: {exc}"
            self.backend.report_error(self.error)
            try:
                await self.cancel()
            except Exception as restore_error:
                self.backend.report_error(str(restore_error))
