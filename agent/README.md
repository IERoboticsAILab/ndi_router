## Device Agent (lab-device-agent)

Minimal, readable MQTT device agent for running modules (NDI) on edge devices (e.g., Raspberry Pi). It exposes device-level controls and per-module controls.

### Key ideas
- **Simple structure**: one agent process, pluggable modules.
- **Device-level controls**: labels and module add/remove.
- **Module lifecycle**: clean startup/shutdown, separate status and acks.
- **Feature presets**: define named sets of modules and configs in YAML, apply at boot or at runtime.

---

## Install
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
PYTHONPATH=. python -m device.agent
```

### Systemd
- Edit `systemd/lab-device-agent.service` and set absolute paths.
- Install and enable:
```bash
sudo cp systemd/lab-device-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lab-device-agent
```

---

## Architecture

### Components
- **`device/agent.py`**: Starts MQTT client, loads modules, routes messages, and publishes statuses/meta.
- **`device/modules/base.py`**: `Module` abstract base class; provides `status_payload`, `apply_cfg`, optional `shutdown`.
- **`device/modules/ndi.py`**: Runs NDI viewer/recorder commands; manages background processes.
- **`common.py`**: Topic helpers, envelope/ack utilities, timestamps, JSON helpers.

### Message flow (high-level)
- Agent publishes retained device `meta` and device `status`.
- Orchestrator/app sends commands to the device and its modules.
- Agent executes actions and replies with acks on device/module event topics.
- Each module publishes its own `status` snapshot.

---

## MQTT Topics
Prefix constants (from `common.py`):
- `LAB_PREFIX = "/lab"`
- `DEVICE_T = "/lab/device/{device_id}"`
- `MODULE_T = "/lab/device/{device_id}/{module}"`

### Device topics
- `DEVICE_T + "/meta"` (retain): device capabilities/labels
- `DEVICE_T + "/status"` (retain): online heartbeat
- `DEVICE_T + "/cmd"`: device-level commands
- `DEVICE_T + "/evt"`: device-level acks/events

### Module topics
- `MODULE_T + "/status"` (retain): per-module status payload
- `MODULE_T + "/cmd"`: per-module commands
- `MODULE_T + "/cfg"`: runtime config updates for a module
- `MODULE_T + "/evt"`: per-module acks/events

---

## Payload Conventions

### Envelope for commands (app/orch → device/module)
```json
{
  "req_id": "<uuid>",
  "actor": "orchestrator|app|user",
  "ts": "2024-01-01T00:00:00Z",
  "action": "<action>",
  "params": { }
}
```

### Ack for replies (device/module → app/orch)
```json
{
  "req_id": "<same-as-request>",
  "ok": true,
  "ts": "2024-01-01T00:00:00Z",
  "error": null,
  "details": { }
}
```

### Module status payload
Published on `.../status` (retain):
```json
{
  "state": "idle|running",
  "online": true,
  "ts": "2024-01-01T00:00:00Z",
  "fields": { }
}
```

---

## Configuration
File: `device/config.yaml`

### Minimal example
```yaml
device_id: rpi-01
labels: ["zone-a", "rpi"]
modules:
  ndi:
    ndi_path: '/usr/local/lib/libndi.so'
    start_cmd_template: 'yuri_simple ndi_input[stream="{source}"] glx_window[fullscreen=True]'
    set_input_restart: true
    record_start_cmd_template: '/usr/local/bin/ffmpeg -y -f libndi_newtek -i "{source}" -c copy /home/pi/ndi_{device_id}.mp4'
mqtt:
  host: 10.205.10.7
  port: 1883
  username: mqtt
  password: "123456789"
```

---

## NDI Module (`ndi`)

### Config keys
- **ndi_path**: absolute path to libndi.so; also prepends its directory to `LD_LIBRARY_PATH` by default.
- **ndi_env**: object. Additional environment key/values injected into subprocesses (legacy `env` also supported).
- **start_cmd_template**: string. Must include `{source}` and can include `{device_id}`.
- **set_input_restart**: boolean. If true, `set_input` will restart the player using `start_cmd_template`.
- **record_start_cmd_template**: string. Template used to launch recorder.

### Commands (topic: `/lab/device/{device_id}/ndi/cmd`)
- **start**: `{ "action": "start", "params": {"source": "NDI-NAME"} }`
- **stop**: `{ "action": "stop" }`
- **set_input**: `{ "action": "set_input", "params": {"source": "NDI-NAME"} }`
- **record_start**: `{ "action": "record_start", "params": {"source": "NDI-NAME"} }` (source optional; falls back to current)
- **record_stop**: `{ "action": "record_stop" }`

### Status fields
- `fields.input`: current input source
- `fields.pid`: viewer process pid, if running
- `fields.recording`: boolean
- `fields.record_pid`: recorder process pid, if running

### Notes
- Subprocesses run in their own process groups and are terminated with SIGTERM for clean shutdowns.
- Stdout/stderr are suppressed. If debugging is needed, temporarily change `stdout/stderr` in `ndi.py` to `subprocess.PIPE` and add prints/logging.

---

## Meta Payload
Published on `/lab/device/{device_id}/meta` (retain):
```json
{
  "device_id": "rpi-01",
  "modules": ["ndi"],
  "capabilities": { "ndi": {"..."} },
  "labels": ["zone-a","display"],
  "version": "dev-0.1.0",
  "ts": "..."
}
```

---

## Extending with New Modules
1. Create a file under `device/modules/<your_module>.py`:
   - Subclass `Module`
   - Implement `handle_cmd(self, action, params)` returning `(ok, error, details)`
   - Optionally override `shutdown()` for cleanup
   - Update `self.state` and `self.fields` appropriately
2. Register in `device/modules/__init__.py` by adding to `MODULE_MAP`.
3. Add config under `modules` in `device/config.yaml`.
4. Send commands to `/lab/device/{device_id}/{module}/cmd`.

### Minimal module example
```python
from typing import Dict, Any
from .base import Module

class ExampleModule(Module):
    name = "example"

    def handle_cmd(self, action: str, params: Dict[str, Any]):
        if action == "say":
            text = params.get("text", "hello")
            self.state = "running"
            self.fields.update({"last": text})
            return True, None, {"echo": text}
        return False, f"unknown action: {action}", {}
```

---

## Troubleshooting
- **No connection to MQTT**: verify broker host/port/credentials in `config.yaml`.
- **No acks received**: ensure you are publishing to the correct topic; check device id and module name.
- **NDI viewer doesn’t start**: verify `NDI_PATH`/`ndi_path` and that your player (e.g., `yuri_simple`) is installed and in PATH.
- **Recording doesn’t start**: verify `ffmpeg` path and `record_start_cmd_template`.
- **Permissions**: some commands (e.g., `pkill`) may require sufficient permissions.
- **Debugging subprocesses**: temporarily change `stdout/stderr` in `ndi.py` from `DEVNULL` to `PIPE` and add prints.

---

## Security Notes
- Broker credentials are stored in `device/config.yaml`. Lock down file permissions.
- Prefer a dedicated MQTT user per device and network isolation.
- Consider TLS and authentication on your broker for production.

---

## Quick Reference
- Device command topic: `/lab/device/{device_id}/cmd`
- Device ack topic: `/lab/device/{device_id}/evt`
- Module command topic: `/lab/device/{device_id}/{module}/cmd`
- Module ack topic: `/lab/device/{device_id}/{module}/evt`
- Status (retained): `/lab/device/{device_id}/status` and `/lab/device/{device_id}/{module}/status`
- Meta (retained): `/lab/device/{device_id}/meta`
