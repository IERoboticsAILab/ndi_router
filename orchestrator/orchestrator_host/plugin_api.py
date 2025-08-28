from fastapi import APIRouter
from typing import Dict, Any, Optional, Iterable


class PluginContext:
    def __init__(self, mqtt, registry, scheduler, settings):
        self.mqtt = mqtt
        self.registry = registry
        self.scheduler = scheduler
        self.settings = settings  # dict


class OrchestratorPlugin:
    module_name: str  # e.g., "ndi"

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx

    # MQTT topic filters the host should subscribe on and forward to this plugin
    def mqtt_topic_filters(self) -> Iterable[str]:
        # e.g., [f"/lab/orchestrator/{self.module_name}/cmd"]
        raise NotImplementedError

    # Handle incoming MQTT message (topic, payload as dict)
    def handle_mqtt(self, topic: str, payload: Dict[str, Any]) -> None:
        raise NotImplementedError

    # Optional: expose REST API
    def api_router(self) -> Optional[APIRouter]:
        return None

    # Optional: UI mount path and template name
    def ui_mount(self) -> Optional[Dict[str, str]]:
        # return {"path": f"/ui/{self.module_name}", "template": "plugin_shell.html", "title": "NDI"}
        return None

    # Lifecycle hooks
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


