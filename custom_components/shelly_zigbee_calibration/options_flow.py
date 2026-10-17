"""Native Home Assistant dialog for visual minimum and gamma adjustment."""
from homeassistant import config_entries
from homeassistant.core import callback


class DimmingOptionsFlow(config_entries.OptionsFlow):
    def __init__(self):
        self.token = None
        self.runtime = None

    async def async_step_init(self, user_input=None):
        self.runtime = self.config_entry.runtime_data
        return self.async_show_menu(step_id="init", menu_options=["minimum", "gamma"])

    async def _show(self, mode):
        runtime = self.config_entry.runtime_data
        self.runtime = runtime
        try:
            if self.token is None:
                self.token = await runtime.wizard.start(mode)
            runtime.wizard._require(self.token)
        except Exception as exc:
            return self.async_abort(reason="wizard_error", description_placeholders={"error": str(exc)})
        return self.async_show_menu(
            step_id=mode,
            menu_options=(["brighter", "darker", "save", "cancel"] if mode == "minimum"
                          else ["more_gamma", "less_gamma", "save", "cancel"]),
            description_placeholders={
                "minimum": f"{runtime.wizard.candidate.minimum:.1f}",
                "gamma": f"{runtime.wizard.candidate.gamma:.1f}",
            },
        )

    async def async_step_minimum(self, user_input=None):
        return await self._show("minimum")

    async def async_step_gamma(self, user_input=None):
        return await self._show("gamma")

    async def _adjust(self, mode, delta):
        if self.runtime is None or self.token is None:
            return self.async_abort(reason="wizard_expired")
        try:
            method = (self.runtime.wizard.adjust_minimum if mode == "minimum"
                      else self.runtime.wizard.adjust_gamma)
            await method(self.token, delta)
        except Exception as exc:
            return self.async_abort(reason="wizard_error", description_placeholders={"error": str(exc)})
        return await self._show(mode)

    async def async_step_brighter(self, user_input=None):
        return await self._adjust("minimum", 0.5)

    async def async_step_darker(self, user_input=None):
        return await self._adjust("minimum", -0.5)

    async def async_step_more_gamma(self, user_input=None):
        return await self._adjust("gamma", 0.1)

    async def async_step_less_gamma(self, user_input=None):
        return await self._adjust("gamma", -0.1)

    async def async_step_save(self, user_input=None):
        if self.runtime is None or self.token is None:
            return self.async_abort(reason="wizard_expired")
        try:
            await self.runtime.wizard.save(self.token)
        except Exception as exc:
            return self.async_abort(reason="wizard_error", description_placeholders={"error": str(exc)})
        self.token = None
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    async def async_step_cancel(self, user_input=None):
        if self.runtime is None or self.token is None:
            return self.async_abort(reason="wizard_expired")
        if self.runtime is not None:
            try:
                await self.runtime.wizard.cancel(self.token)
            except Exception as exc:
                return self.async_abort(reason="wizard_error", description_placeholders={"error": str(exc)})
        self.token = None
        return self.async_abort(reason="wizard_cancelled")

    @callback
    def async_remove(self):
        # Closing the dialog is cancellation, not implicit acceptance.
        if self.runtime is not None and self.token is not None:
            runtime, token = self.runtime, self.token
            self.token = None

            async def cancel():
                try:
                    await runtime.wizard.cancel(token)
                except Exception as exc:
                    runtime.report_error(str(exc))
            self.hass.async_create_task(cancel())
