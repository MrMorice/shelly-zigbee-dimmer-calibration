"""Local starting values only; actual trials live on the existing ZHA device."""
import probatio
from homeassistant import config_entries
from homeassistant.helpers import selector

from .curve import Curve


class DimmingOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is not None and (runtime.wizard.active or runtime.wizard.lock.locked() or runtime.pending is not None):
            return self.async_abort(reason="trial_active")
        errors = {}
        if user_input is not None:
            try:
                Curve(0, user_input["initial_gamma"], user_input["maximum"])
            except (ValueError, KeyError):
                errors["base"] = "invalid_values"
            else:
                return self.async_create_entry(title="", data=user_input)
        bounds = getattr(runtime, "saved_settings", {}).get("range_map", [0, 100])
        options = self.config_entry.options
        return self.async_show_form(step_id="init", errors=errors, data_schema=probatio.Schema({
            probatio.Required("maximum", default=options.get("maximum", bounds[1])):
                selector.NumberSelector(selector.NumberSelectorConfig(min=0.1, max=100, step=0.1,
                    mode=selector.NumberSelectorMode.BOX)),
            probatio.Required("initial_gamma", default=options.get("initial_gamma", 1.0)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=0.4, max=4, step=0.1,
                    mode=selector.NumberSelectorMode.BOX)),
        }))
