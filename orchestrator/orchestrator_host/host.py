from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from importlib import import_module
from pathlib import Path

from orchestrator_host.plugin_api import OrchestratorPlugin, PluginContext
from orchestrator_host.services.mqtt import SharedMQTT
from orchestrator_host.services.registry import Registry
from orchestrator_host.services.scheduler import Scheduler
from orchestrator_host.services.events import ack, now_iso
from orchestrator_host import config


app = FastAPI(title="Main Orchestrator")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "ui" / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "ui" / "static")), name="static")

mqtt = SharedMQTT(**config.MQTT)
registry = Registry()
scheduler = Scheduler()

_plugins: dict[str, OrchestratorPlugin] = {}


def _load_class(path: str):
    mod, cls = path.split(":")
    m = import_module(mod)
    return getattr(m, cls)


def load_plugins():
    for p in config.PLUGINS:
        Cls = _load_class(p["path"])  # type: ignore
        ctx = PluginContext(mqtt=mqtt, registry=registry, scheduler=scheduler, settings=p.get("settings", {}))
        inst: OrchestratorPlugin = Cls(ctx)
        _plugins[inst.module_name] = inst
        mqtt.subscribe(inst.mqtt_topic_filters(), inst.handle_mqtt)
        router = inst.api_router()
        if router:
            app.include_router(router, prefix=f"/api/{inst.module_name}", tags=[inst.module_name])
        ui = inst.ui_mount()
        if ui:
            path = ui["path"]
            title = ui["title"]
            tpl = ui["template"]

            @app.get(path, response_class=HTMLResponse)
            async def ui_page(request: Request, _title=title, _tpl=tpl):
                return templates.TemplateResponse(_tpl, {"request": request, "title": _title, "module": path.split("/")[-1], "plugins": list(_plugins.keys())})
        inst.start()


@app.on_event("startup")
def on_start():
    # subscribe device meta/status to build registry
    def _dev_cb(topic, payload):
        did = payload.get("device_id")
        if not did:
            return
        d = registry.devices.get(did, {})
        d.update(payload)
        registry.devices[did] = d
        # publish registry snapshot (retained)
        snap = registry.snapshot()
        snap["ts"] = now_iso()
        snap["modules"] = list(_plugins.keys())
        mqtt.publish_json("/lab/orchestrator/registry", snap, qos=1, retain=True)

    # allow wildcards later via SharedMQTT._match enhancement if needed
    mqtt.subscribe(["/lab/device/+/meta", "/lab/device/+/status"], _dev_cb)
    load_plugins()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "plugins": list(_plugins.keys())})


@app.get("/api/registry", response_class=JSONResponse)
async def api_registry():
    snap = registry.snapshot()
    snap["ts"] = now_iso()
    snap["modules"] = list(_plugins.keys())
    return JSONResponse(content=snap)

@app.delete("/api/registry/devices/{device_id}")
async def delete_device(device_id: str):
    if device_id not in registry.devices:
        raise HTTPException(status_code=404, detail="unknown device")
    # Clear retained meta/status from broker so the device does not reappear
    mqtt.publish_raw(f"/lab/device/{device_id}/meta", payload=None, qos=1, retain=True)
    mqtt.publish_raw(f"/lab/device/{device_id}/status", payload=None, qos=1, retain=True)
    # Remove from registry and publish snapshot
    try:
        del registry.devices[device_id]
    except Exception:
        pass
    snap = registry.snapshot(); snap["ts"] = now_iso(); snap["modules"] = list(_plugins.keys())
    mqtt.publish_json("/lab/orchestrator/registry", snap, qos=1, retain=True)
    return {"ok": True, "removed": device_id}

@app.get("/ui/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    return templates.TemplateResponse("devices.html", {"request": request, "title": "Devices", "plugins": list(_plugins.keys())})

