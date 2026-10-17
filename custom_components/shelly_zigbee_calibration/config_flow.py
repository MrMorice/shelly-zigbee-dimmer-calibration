"""Choose an existing Shelly Dimmer Gen4 without starting calibration."""
import probatio
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DOMAIN
from .helpers import get_candidates


class CalibrationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        try:
            candidates = get_candidates(self.hass)
        except (KeyError, ValueError):
            return self.async_abort(reason="zha_not_ready")
        if not candidates:
            return self.async_abort(reason="no_devices")
        errors = {}
        if user_input is not None:
            ieee = user_input["ieee"]
            if ieee in candidates:
                await self.async_set_unique_id(ieee)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=candidates[ieee], data={"ieee": ieee})
            errors["base"] = "device_missing"
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=probatio.Schema({
                probatio.Required("ieee"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[{"value": key, "label": label}
                                 for key, label in candidates.items()],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
        )
