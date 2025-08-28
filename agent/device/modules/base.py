from abc import ABC, abstractmethod
from typing import Dict, Any

class Module(ABC):
    """Abstract device module.

    Concrete modules (e.g., NDIModule, LEDModule) subclass this and implement
    `handle_cmd`. The agent uses instances to process MQTT commands and emit
    status updates.
    """
    name: str

    def __init__(self, device_id: str, cfg: Dict[str, Any] | None = None):
        self.device_id = device_id
        self.cfg = cfg or {}
        self.state = "idle"
        self.fields: Dict[str, Any] = {}

    @abstractmethod
    def handle_cmd(self, action: str, params: Dict[str, Any]) -> tuple[bool, str | None, dict]:
        """Run a module action. Returns (ok, error_message, details_dict)."""
        ...

    def apply_cfg(self, cfg: Dict[str, Any]) -> None:
        """Merge new configuration into the module at runtime."""
        self.cfg.update(cfg)

    def status_payload(self) -> Dict[str, Any]:
        """Current status snapshot for publishing to MQTT."""
        from common import now_iso
        return {"state": self.state, "online": True, "ts": now_iso(), "fields": self.fields}

    def shutdown(self) -> None:
        """Called before a module is removed to allow cleanup. Optional override."""
        return None

    def on_agent_connect(self) -> None:
        """Called when the agent connects to the broker. Modules can perform setup.

        Default is no-op. Subclasses can override to export environment variables
        or perform runtime initialization dependent on the host environment.
        """
        return None
