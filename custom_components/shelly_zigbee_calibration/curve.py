"""Native Shelly dimming settings; no software brightness transformation."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Curve:
    minimum: float = 0.0
    gamma: float = 1.0
    maximum: float = 100.0

    def __post_init__(self):
        values = (self.minimum, self.gamma, self.maximum)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError("Ungültige Shelly-Dimmwerte")
        if not 0 <= self.minimum < self.maximum <= 100 or not 0.4 <= self.gamma <= 4:
            raise ValueError("Shelly-Dimmwerte außerhalb des gültigen Bereichs")

    def as_dict(self):
        return {"minimum": self.minimum, "gamma": self.gamma, "maximum": self.maximum}

    def as_config(self, mode=None):
        if mode == "minimum":
            return {"range_map": [self.minimum, self.maximum]}
        if mode == "gamma":
            return {"gamma": self.gamma}
        return {"gamma": self.gamma, "range_map": [self.minimum, self.maximum]}


def validate_settings(settings):
    """Validate a locally saved partial configuration, never infer missing values."""
    if not isinstance(settings, dict) or set(settings) - {"range_map", "gamma"}:
        raise ValueError("Ungültige gespeicherte Dimmwerte")
    bounds = settings.get("range_map", [0, 100])
    if not isinstance(bounds, list) or len(bounds) != 2:
        raise ValueError("Ungültige gespeicherte Helligkeitsgrenzen")
    Curve(bounds[0], settings.get("gamma", 1), bounds[1])
    result = {}
    if "range_map" in settings:
        result["range_map"] = list(bounds)
    if "gamma" in settings:
        result["gamma"] = settings["gamma"]
    return result
