## Orchestrator Host

FastAPI-based orchestrator with a lightweight plugin system (NDI). It subscribes to device meta/status to build a live registry, exposes REST endpoints and simple UIs per plugin, and relays/schedules commands to devices via MQTT.

### Highlights
- **Plugin architecture**: add features by creating a small plugin class.
- **Live registry**: aggregates `/lab/device/{id}/meta` and `/lab/device/{id}/status`.
- **Command relay**: plugins publish to device module topics.
- **Scheduling + reservation**: prevent conflicts and automate actions.

---

## Install
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
uvicorn orchestrator_host.host:app --host 0.0.0.0 --port 8080
```

### Docker
- Build and run with Docker (see `Dockerfile`):
```bash
make docker-build
make docker-run
```

---

## Architecture

### Core pieces
- **`orchestrator_host/host.py`**: App entry; loads plugins; subscribes to device registry topics; mounts API and UI from plugins.
- **`orchestrator_host/plugin_api.py`**: Base classes for plugins and the shared `PluginContext` (MQTT, Registry, Scheduler, settings).
- **`orchestrator_host/services/mqtt.py`**: Shared MQTT client with topic filter routing.
- **`orchestrator_host/services/registry.py`**: In-memory device/lock registry with lease-based locking.
- **`orchestrator_host/services/scheduler.py`**: APScheduler wrapper for one-off and cron jobs.
- **`orchestrator_host/services/events.py`**: Ack and timestamp helpers.

### Plugins
- Located in `plugins/<name>_plugin/plugin.py`. Each plugin:
  - sets `module_name` (e.g., `"ndi"`)
  - implements `mqtt_topic_filters()` so the host can subscribe and forward
  - implements `handle_mqtt(topic, payload)` to react to orchestrator-level commands
  - can expose a REST API with `api_router()` and a UI via `ui_mount()`

### MQTT namespace (host-side)
- Host listens to device registry updates:
  - `/lab/device/+/meta` (retain)
  - `/lab/device/+/status` (retain)
- Host publishes a consolidated registry snapshot:
  - `/lab/orchestrator/registry` (retain)
- Plugins listen to orchestrator command topics (per module):
  - `/lab/orchestrator/{module}/cmd`
- Plugins publish orchestrator-level events/acks:
  - `/lab/orchestrator/{module}/evt`
- Plugins relay to devices on module command topics:
  - `/lab/device/{device_id}/{module}/cmd`

---

## Configuration
File: `orchestrator_host/config.py`

```python
PLUGINS = [
    {"module": "ndi", "path": "plugins.ndi_plugin.plugin:NDIPlugin", "settings": {
        # Plugin-specific settings
        "sources": ["NDI-Source-1", "NDI-Source-2"]
    }},
]

MQTT = {"host": "10.205.10.7", "port": 1883, "username": "mqtt", "password": "123456789"}
```

- Add or remove plugins by editing `PLUGINS`.
- `settings` is passed to the plugin via its `PluginContext`.

---

## Device Registry
- On startup, the host subscribes to `/lab/device/+/meta` and `/lab/device/+/status`.
- Each update merges into `Registry.devices[device_id]` and republishes a snapshot to `/lab/orchestrator/registry` with:
  - `devices`: the merged device map
  - `locks`: current module/device leases
  - `modules`: plugins loaded in the orchestrator
  - `ts`: timestamp

---

## Plugins in Detail

### NDI Plugin
- Orchestrator topic: `/lab/orchestrator/ndi/cmd`
- Events: `/lab/orchestrator/ndi/evt`
- Pass-through device actions: `start`, `stop`, `set_input`, `record_start`, `record_stop`.
- Host-level actions:
  - `reserve` `{ device_id, lease_s }`: acquire a lease `ndi:{device_id}`
  - `release` `{ device_id }`: release the lease
  - `schedule` `{ at|cron, commands: [{ device_id, action, params }] }`: schedule pass-through actions
- REST API:
  - `GET /api/ndi/status`: returns registry snapshot
  - `GET /api/ndi/sources`: returns discovered NDI sources (tries helper, falls back to `cyndilib` Finder)
  - `GET /api/ndi/devices`: returns devices advertising the `ndi` module
  - `POST /api/ndi/send` `{ device_id, action, source }`: dispatch to device
- UI: `GET /ui/ndi` basic controls to select device/source and start/stop/set input.

---

## Command Flows

### Orchestrator → Device Module (pass-through)
1. App publishes to plugin topic, e.g. `/lab/orchestrator/ndi/cmd`:
```json
{"req_id":"1","actor":"app","action":"start","params":{"device_id":"rpi-01","source":"NDI-Source-1"}}
```
2. Plugin republishes to `/lab/device/{device_id}/ndi/cmd` with same payload.
3. Device executes and publishes its ack to `/lab/device/{device_id}/ndi/evt`.
4. Plugin optionally emits a `DISPATCHED` ack on `/lab/orchestrator/ndi/evt`.

### Reservations
- Acquire: publish `{action:"reserve", params:{device_id:"rpi-01", lease_s:60}}` to `/lab/orchestrator/ndi/cmd`.
- Check: plugins call `registry.can_use("ndi:rpi-01", actor)` before scheduling executions.
- Release: publish `{action:"release", params:{device_id:"rpi-01"}}`.

### Scheduling
- Publish to plugin cmd topic with either `at` (ISO timestamp) or crontab `cron` and a `commands` array.
- The scheduler executes commands later using the same pass-through mapping.

---

## Developing a Plugin
1. Create `plugins/<name>_plugin/plugin.py`:
```python
from orchestrator_host.plugin_api import OrchestratorPlugin
from fastapi import APIRouter

class MyPlugin(OrchestratorPlugin):
    module_name = "my"
    def mqtt_topic_filters(self):
        return [f"/lab/orchestrator/{self.module_name}/cmd"]
    def handle_mqtt(self, topic, payload):
        # read payload["action"], payload["params"], relay or act
        pass
    def api_router(self):
        r = APIRouter()
        @r.get("/status")
        def status(): return self.ctx.registry.snapshot()
        return r
    def ui_mount(self):
        return {"path": f"/ui/{self.module_name}", "template": "plugin_shell.html", "title": "MY"}
```
2. Register it in `orchestrator_host/config.py` under `PLUGINS`.
3. Optionally add a UI template under `orchestrator_host/ui/templates/`.

---

## Security & Deployment Notes
- Lock down broker credentials, prefer per-service users.
- Consider TLS and auth for MQTT in production.
- Run the host behind a reverse proxy (nginx) if exposing externally.

---

## Troubleshooting
- **No devices listed**: ensure devices publish to `/lab/device/{id}/meta` and that broker IP matches on both sides.
- **Commands do nothing**: verify device has the required module in its meta and is subscribed to the module command topic.
- **NDI sources empty**: ensure `ndi_discovery` helper or `cyndilib` is available at runtime.
- **Scheduler errors**: check APScheduler logs; verify cron syntax `"m h dom mon dow"`.
