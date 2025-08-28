# lab-orchestrator-host

FastAPI-based orchestrator host with plugin system (NDI, LED).

## Install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

## Configure
Edit orchestrator_host/config.py (MQTT broker, plugins).

## Run
uvicorn orchestrator_host.host:app --host 0.0.0.0 --port 8080

## Systemd
Update systemd/lab-orchestrator-host.service paths and install with systemctl.
