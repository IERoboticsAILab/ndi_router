from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import time

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
            try:
                discovered = _discover_ndi_source_names(timeout=3.0)
                # If discovery returns something, use it; otherwise fall back
                if discovered:
                    return {"sources": discovered}
            except Exception:
                # Fall back to configured list on any error (module missing, etc.)
                pass
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



def _discover_ndi_source_names(timeout: float = 3.0) -> List[str]:
    """Discover NDI sources and return a list of human-readable names.

    Prefer using the project's `ndi_discovery.list_all_ndi_sources` helper.
    Fall back to direct cyndilib Finder usage if import is unavailable.
    Returns a list like ["host (stream)", ...].
    """
    # Try to import helper from repo root
    try:
        from ndi_discovery import list_all_ndi_sources  # type: ignore
    except Exception:
        # Try adding repo root to sys.path (two levels up from this file)
        try:
            import sys
            from pathlib import Path
            repo_root = Path(__file__).resolve().parents[2]
            if str(repo_root) not in sys.path:
                sys.path.append(str(repo_root))
            from ndi_discovery import list_all_ndi_sources  # type: ignore
        except Exception:
            list_all_ndi_sources = None  # type: ignore

    if list_all_ndi_sources is not None:  # type: ignore
        try:
            items = list_all_ndi_sources(timeout=timeout)  # type: ignore
            names: List[str] = []
            for it in items:
                name = it.get("name")
                if name:
                    names.append(name)
                else:
                    host = it.get("host", "")
                    stream = it.get("stream", "")
                    label = f"{host} ({stream})".strip()
                    names.append(label)
            return names
        except Exception:
            # Fall back to direct Finder path below
            pass

    # Fallback: direct Finder usage
    from cyndilib.finder import Finder  # type: ignore
    finder = Finder()
    finder.open()
    try:
        end_time = time.time() + timeout
        while time.time() < end_time:
            changed = finder.wait_for_sources(timeout=end_time - time.time())
            if changed:
                finder.update_sources()
            time.sleep(0.1)

        names: List[str] = []
        for src in finder.iter_sources():
            names.append(src.name)
        return names
    finally:
        finder.close()

