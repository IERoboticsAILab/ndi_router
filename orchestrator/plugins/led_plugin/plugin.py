from fastapi import APIRouter
from typing import Dict, Any

from orchestrator_host.plugin_api import OrchestratorPlugin
from orchestrator_host.services.events import ack


class LEDPlugin(OrchestratorPlugin):
    module_name = "led"

    def mqtt_topic_filters(self):
        return [f"/lab/orchestrator/{self.module_name}/cmd"]

    def handle_mqtt(self, topic: str, payload: Dict[str, Any]) -> None:
        req_id = payload.get("req_id", "no-req")
        action = payload.get("action")
        params = payload.get("params", {})
        device_id = params.get("device_id")
        actor = payload.get("actor", "app")

        # Keep passthrough actions to module commands only
        passthrough = {"effect", "solid", "off", "brightness"}
        if action in passthrough:
            dev_topic = f"/lab/device/{device_id}/{self.module_name}/cmd"
            self.ctx.mqtt.publish_json(dev_topic, payload, qos=1, retain=False)
            evt = ack(req_id, True, "DISPATCHED")
            self.ctx.mqtt.publish_json(f"/lab/orchestrator/{self.module_name}/evt", evt)
            return
        if action == "reserve":
            lease_s = int(params.get("lease_s", 60))
            key = f"{self.module_name}:{device_id}"
            ok = self.ctx.registry.lock(key, actor, lease_s)
            code = "OK" if ok else "IN_USE"
            err = None if ok else "in_use"
            self.ctx.mqtt.publish_json(f"/lab/orchestrator/{self.module_name}/evt", ack(req_id, ok, code, err))
            return
        if action == "release":
            key = f"{self.module_name}:{device_id}"
            ok = self.ctx.registry.release(key, actor)
            code = "OK" if ok else "NOT_OWNER"
            err = None if ok else "not_owner"
            self.ctx.mqtt.publish_json(f"/lab/orchestrator/{self.module_name}/evt", ack(req_id, ok, code, err))
            return
        if action == "schedule":
            when = params.get("at"); cron = params.get("cron"); commands = params.get("commands", [])
            if when:
                from datetime import datetime
                run_date = datetime.fromisoformat(when.replace("Z", "+00:00"))
                self.ctx.scheduler.once(run_date, self._run_commands, module=self.module_name, commands=commands, actor=actor)
            elif cron:
                self.ctx.scheduler.cron(cron, self._run_commands, module=self.module_name, commands=commands, actor=actor)
            self.ctx.mqtt.publish_json(f"/lab/orchestrator/{self.module_name}/evt", ack(req_id, True, "SCHEDULED"))
            return
        evt = ack(req_id, False, "BAD_ACTION", f"Unsupported action: {action}")
        self.ctx.mqtt.publish_json(f"/lab/orchestrator/{self.module_name}/evt", evt)

    def _run_commands(self, module: str, commands: list[Dict[str, Any]], actor: str):
        import uuid
        from orchestrator_host.services.events import now_iso
        for c in commands:
            device_id = c.get("device_id")
            if not device_id:
                continue
            key = f"{module}:{device_id}"
            if not self.ctx.registry.can_use(key, actor):
                continue
            env = {"req_id": str(uuid.uuid4()), "actor": f"host:{actor}", "ts": now_iso(), "action": c.get("action"), "params": c.get("params", {})}
            env["params"]["device_id"] = device_id
            self.ctx.mqtt.publish_json(f"/lab/device/{device_id}/{module}/cmd", env, qos=1, retain=False)

    def api_router(self):
        r = APIRouter()

        @r.get("/status")
        def status():
            reg = self.ctx.registry.snapshot()
            return reg

        return r

    def ui_mount(self):
        return {"path": f"/ui/{self.module_name}", "template": "plugin_shell.html", "title": "LED"}


