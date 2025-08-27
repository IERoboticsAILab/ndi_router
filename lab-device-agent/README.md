# lab-device-agent

Minimal MQTT device agent for lab modules (NDI, LED).

## Install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

## Configure
Edit device/config.yaml (device_id, mqtt, module command templates).

## Run
PYTHONPATH=. python -m device.agent

## Systemd
Update systemd/lab-device-agent.service paths and install with systemctl.
