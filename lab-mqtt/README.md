# lab-mqtt

Minimal, production-ready skeleton for **device agents** (RPi-friendly) and an **orchestrator host** with plugin sub-orchestrators (NDI, LED, ...).

## Tree
```
lab-mqtt/
├─ requirements.txt
├─ common.py
├─ README.md
├─ Makefile
├─ device/
│  ├─ __init__.py
│  ├─ agent.py
│  ├─ config.yaml
│  └─ modules/
│     ├─ __init__.py
│     ├─ base.py
│     ├─ led.py
│     └─ ndi.py
├─ orchestrators/                 # removed; host + plugins replace these
├─ orchestrator_host/             # new host + plugins
│  ├─ host.py
│  ├─ plugin_api.py
│  ├─ services/{mqtt,registry,scheduler,events}.py
│  └─ ui/templates/{base,index,plugin_shell}.html
├─ plugins/
│  ├─ ndi_plugin/plugin.py
│  └─ led_plugin/plugin.py
├─ systemd/
│  ├─ lab-device-agent.service
│  └─ lab-orchestrator.service
└─ tools/
   ├─ publish.py
   └─ sample_messages/
      ├─ reserve_led.json
      ├─ effect_led.json
      └─ start_ndi.json
```

## Quickstart

1) **Install deps**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2) **Configure your device** (RPi): edit `device/config.yaml`. For MVP, keep only `ndi` in `modules`.

3) **Start broker** (Mosquitto/EMQX). No ACLs needed for MVP.

4) **Run agent** on the RPi:
```bash
PYTHONPATH=. python -m device.agent
```

5) **Run orchestrator host (FastAPI)**:
```bash
uvicorn orchestrator_host.host:app --reload --port 8080
```

6) **Smoke test** (in another shell):
```bash
python tools/publish.py /lab/orchestrator/ndi/cmd tools/sample_messages/start_ndi.json
```

## Topics

- Device meta: `/lab/device/{device_id}/meta` (retained)
- Device status: `/lab/device/{device_id}/status` (retained)
- Module cmd: `/lab/devices/{device_id}/{module}/cmd`
- Module status: `/lab/devices/{device_id}/{module}/status` (retained)
- Module evt (acks): `/lab/devices/{device_id}/{module}/evt`
- Orchestrator cmd: `/lab/orchestrator/{module}/cmd`
- Orchestrator evt: `/lab/orchestrator/{module}/evt`
- Registry: `/lab/orchestrator/registry` (retained)

## Systemd (optional)
Edit the `WorkingDirectory=` and `User=` in files under `systemd/`, then:
```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lab-device-agent.service
sudo systemctl enable --now lab-orchestrator.service
```

## Notes
- Keep `PYTHONPATH=.` if running from the repo root.
- LED module is a stub that returns immediate acks; swap its internals when ready.
- Legacy orchestrators remain for parity during migration; the new host supersedes them.

---

## Device Agent (README)

### Overview
`device/agent.py` loads `device/config.yaml`, instantiates modules (e.g., `ndi`, `led`), connects to MQTT, publishes retained device `meta` and `status`, and listens for per-module `cmd`/`cfg` topics.

### Install
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Configure `device/config.yaml`
- `device_id`: unique name for the device (e.g., `rpi-01`)
- `modules.ndi`: command templates for start/stop/set_input/record
- `mqtt`: broker host/port/username/password

### Run
```bash
PYTHONPATH=. python -m device.agent
```

### MQTT Topics (device side)
- `/lab/device/{device_id}/meta` (retained)
- `/lab/device/{device_id}/status` (retained)
- `/lab/devices/{device_id}/{module}/cmd`
- `/lab/devices/{device_id}/{module}/cfg`
- `/lab/devices/{device_id}/{module}/status` (retained)
- `/lab/devices/{device_id}/{module}/evt`

---

## Orchestrator Host (README)

### Overview
Unified host that loads module plugins, shares one MQTT connection, one scheduler, and a shared registry. Each plugin exposes MQTT handling, optional REST API, and a basic UI panel.

### Run
```bash
uvicorn orchestrator_host.host:app --reload --port 8080
```
Open `http://localhost:8080/` and click a plugin.

### Configuration
`orchestrator_host/config.py` controls which plugins load and MQTT connection details.

### MQTT Topics (orchestrator)
- `/lab/orchestrator/{module}/cmd` (input)
- `/lab/orchestrator/{module}/evt` (acks)
- `/lab/orchestrator/registry` (optional retained snapshot in future)

### REST
- `/api/{module}/...` per plugin (e.g., `/api/ndi/status`).

### Systemd
`systemd/lab-orchestrator-host.service` can be installed to run the web host. Update `WorkingDirectory` and `ExecStart` paths for your environment.
