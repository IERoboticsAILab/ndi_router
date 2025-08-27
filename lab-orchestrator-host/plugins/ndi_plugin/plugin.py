from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

from orchestrator_host.plugin_api import OrchestratorPlugin
from orchestrator_host.services.events import ack


class NDIPlugin(OrchestratorPlugin):
    module_name = "ndi"

    def mqtt_topic_filters(self):
        return [f"/lab/orchestrator/{self.module_name}/cmd"]

    def handle_mqtt(self, topic: str, payload: Dict[str, Any]) -> None:
        req_id = payload.get("req_id", "no-req")
        action = payload.get("action")
        params = payload.get("params", {})
        device_id = params.get("device_id")
        actor = payload.get("actor", "app")

        # Keep passthrough actions strictly to device module commands; reserve/release/schedule are host-level in the old code
        passthrough = {"start", "stop", "set_input", "record_start", "record_stop"}
        if action in passthrough:
            dev_topic = f"/lab/devices/{device_id}/{self.module_name}/cmd"
            self.ctx.mqtt.publish_json(dev_topic, payload, qos=1, retain=False)
            evt = ack(req_id, True, "DISPATCHED")
            self.ctx.mqtt.publish_json(f"/lab/orchestrator/{self.module_name}/evt", evt)
            return
        # Reserve
        if action == "reserve":
            lease_s = int(params.get("lease_s", 60))
            key = f"{self.module_name}:{device_id}"
            ok = self.ctx.registry.lock(key, actor, lease_s)
            code = "OK" if ok else "IN_USE"
            err = None if ok else "in_use"
            self.ctx.mqtt.publish_json(f"/lab/orchestrator/{self.module_name}/evt", ack(req_id, ok, code, err))
            return
        # Release
        if action == "release":
            key = f"{self.module_name}:{device_id}"
            ok = self.ctx.registry.release(key, actor)
            code = "OK" if ok else "NOT_OWNER"
            err = None if ok else "not_owner"
            self.ctx.mqtt.publish_json(f"/lab/orchestrator/{self.module_name}/evt", ack(req_id, ok, code, err))
            return
        # Schedule
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
            self.ctx.mqtt.publish_json(f"/lab/devices/{device_id}/{module}/cmd", env, qos=1, retain=False)

    def api_router(self):
        r = APIRouter()

        class SendBody(BaseModel):
            device_id: str
            source: str
            action: str | None = None  # default to "start"

        @r.get("/status")
        def status():
            reg = self.ctx.registry.snapshot()
            return reg

        @r.get("/sources")
        def sources() -> Dict[str, List[str]]:
            srcs = self.ctx.settings.get("sources", [])
            return {"sources": list(srcs)}

        @r.get("/devices")
        def devices() -> Dict[str, Any]:
            reg = self.ctx.registry.snapshot()
            ndi_devices = {}
            for did, meta in reg.get("devices", {}).items():
                modules = meta.get("modules", [])
                if "ndi" in modules:
                    ndi_devices[did] = {
                        "device_id": did,
                        "online": meta.get("online", True),
                        "capabilities": meta.get("capabilities", {}).get("ndi", {}),
                    }
            return {"devices": ndi_devices}

        @r.post("/send")
        def send(body: SendBody):
            device_id = body.device_id
            source = body.source
            action = body.action or "start"
            # Validate source in configured list if provided
            srcs = self.ctx.settings.get("sources", [])
            if srcs and source not in srcs:
                raise HTTPException(status_code=400, detail="unknown source")
            # Validate device exists
            reg = self.ctx.registry.snapshot()
            if device_id not in reg.get("devices", {}):
                raise HTTPException(status_code=404, detail="unknown device")

            import uuid
            from orchestrator_host.services.events import now_iso
            payload = {
                "req_id": str(uuid.uuid4()),
                "actor": "api",
                "ts": now_iso(),
                "action": action,
                "params": {"device_id": device_id, "source": source},
            }
            dev_topic = f"/lab/devices/{device_id}/{self.module_name}/cmd"
            self.ctx.mqtt.publish_json(dev_topic, payload, qos=1, retain=False)
            return {"ok": True, "dispatched": True, "device_id": device_id, "source": source, "action": action}

        return r

    def ui_mount(self):
        return {"path": f"/ui/{self.module_name}", "template": "ndi.html", "title": "NDI"}


