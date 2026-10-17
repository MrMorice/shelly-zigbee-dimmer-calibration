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

    @classmethod
    def from_config(cls, config):
        if not isinstance(config, dict) or config.get("id") != 0 or "gamma" not in config or "range_map" not in config:
            raise ValueError("Die Firmware liefert gamma und range_map nicht zurück; keine Einstellungen geändert")
        bounds = config["range_map"]
        if bounds is None:
            bounds = [0, 100]
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("Ungültige Shelly-range_map")
        return cls(bounds[0], config["gamma"], bounds[1])

    def as_dict(self):
        return {"minimum": self.minimum, "gamma": self.gamma, "maximum": self.maximum}

    def as_config(self):
        return {"gamma": self.gamma, "range_map": [self.minimum, self.maximum]}
