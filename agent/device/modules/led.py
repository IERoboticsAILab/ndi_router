from typing import Dict, Any
from .base import Module

class LEDModule(Module):
    name = "led"

    def handle_cmd(self, action: str, params: Dict[str, Any]) -> tuple[bool, str | None, dict]:
        """Simple LED control stub. Replace with real driver calls as needed."""
        if action == "off":
            self.state = "idle"
            self.fields.update({"mode": "off"})
            return True, None, {}
        if action == "solid":
            color = params.get("color", "#FFFFFF")
            self.state = "running"
            self.fields.update({"mode": "solid", "color": color, "brightness": params.get("brightness", 255)})
            return True, None, {}
        if action == "effect":
            name = params.get("name", "rainbow")
            self.state = "running"
            self.fields.update({"mode": "effect", "effect": name, "speed": params.get("speed", 0.8),
                                "brightness": params.get("brightness", 180), "fps": 60})
            return True, None, {}
        if action == "brightness":
            b = params.get("value", 128)
            self.fields.update({"brightness": b})
            return True, None, {}
        return False, f"unknown action: {action}", {}
