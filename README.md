# NDI Router

Lightweight FastAPI web service and UI to discover NDI sources on your network and route a selected stream to one or more output devices over SSH.

The app discovers NDI sources using `cyndilib` and, on request, connects to selected devices to launch `yuri_simple` with the chosen NDI stream.

## Features

- **NDI discovery**: Enumerates live NDI sources using `cyndilib`
- **Web UI**: Simple page to pick a source and target devices
- **Multi-device routing**: Sends the same stream to multiple hosts concurrently
- **Stateless config**: Output devices are defined in a single JSON file
- **REST API**: Endpoints for sources, devices, and routing actions

## Requirements

- Python 3.11+
- Platform dependencies suitable for `cyndilib` (NDI runtime/SDK as required by your OS)
- Passwordless SSH access (public key auth) from the router host to each output device
- On each output device: an executable `run_yuri.sh` script available in the default login directory

## Quick start

1) Clone and install

```bash
git clone https://github.com/yourusername/ndi_router.git
cd ndi_router
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Configure SSH access to devices

- Ensure the router host can SSH to each device without a password.
```bash
ssh-keygen -t ed25519 -C "ndi_router"
ssh-copy-id user@DEVICE_IP
ssh user@DEVICE_IP "echo ok"
```

3) Define output devices in `src/output_devices.json`

```json
[
  { "name": "Display-1", "host": "192.168.1.10", "user": "youruser" },
  { "name": "Display-2", "host": "192.168.1.11", "user": "youruser" }
]
```

4) Prepare `run_yuri.sh` on each output device

Place an executable script named `run_yuri.sh` in the default login directory of the remote user (so that `./run_yuri.sh` works). Example content:

```bash
#!/usr/bin/env bash
set -euo pipefail
STREAM_NAME="${1:?NDI stream name required}"
pkill -f 'yuri_simple' || true
nohup yuri_simple "ndi_input[stream=${STREAM_NAME}]" "glx_window[fullscreen=True]" \
  > /tmp/yuri_simple.log 2>&1 &
echo "launched yuri_simple for ${STREAM_NAME}"
```

```bash
chmod +x run_yuri.sh
```

5) Run the web app

```bash
uvicorn src.main:app --reload
```

Open `http://127.0.0.1:8000` and use the UI to route a stream.

Environment variables (optional):

- `HOST` (default `127.0.0.1`)
- `PORT` (default `8000`)

## API

- `GET /api/ndi-sources`
  - Response: `{ "sources": [{ "name": str, "host": str, "stream": str }] }`

- `GET /api/output-devices`
  - Response: `{ "devices": [{ "name": str, "host": str, "user": str }] }`

- `POST /api/route`
  - Form fields:
    - `stream_name`: string (exact NDI source name as displayed)
    - `devices`: repeated string values of host addresses (e.g., `192.168.1.10`)
  - Response: `{ "status": "ok" }` on success

## How it works

- Discovery is implemented in `ndi_discovery.py` using `cyndilib.Finder` and exposed via FastAPI in `src/main.py`.
- The UI (`src/templates/index.html`) fetches sources/devices and posts the routing request.
- For each selected device, the server SSHes in via `paramiko` and runs `./run_yuri.sh "<stream>"`.

## Troubleshooting

- **No NDI sources appear**: Ensure the NDI runtime is installed and your machine is on the same network segment. Check host firewall rules.
- **SSH errors / prompts for password**: Confirm your public key is installed on each device and `sshd` allows public key auth. Test with `ssh user@DEVICE_IP "echo ok"`.
- **`run_yuri.sh` not found**: Place the script in the remote user's default directory and `chmod +x run_yuri.sh`. The server invokes `./run_yuri.sh`.
- **Display doesn’t update**: Confirm `yuri_simple` exists and runs on the target device. Inspect `/tmp/yuri_simple.log` on the device.

## Development

Project layout:

- `src/main.py`: FastAPI app, API endpoints, and simple HTML UI route
- `ndi_discovery.py`: NDI discovery helpers backed by `cyndilib`
- `src/templates/index.html`: Minimal UI for selecting sources and devices
- `src/output_devices.json`: Device configuration consumed by the API/UI
- `ndi_test.py`: Example extended discovery including resolution/framerate

Run the discovery helper directly:

```bash
python ndi_discovery.py
```

## Security note

This service performs remote command execution over SSH with no built-in authentication or authorization. Run it only on a trusted network or place it behind an authenticated reverse proxy.

## License

MIT License