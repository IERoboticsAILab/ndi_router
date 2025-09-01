PLUGINS = [
    {"module": "ndi", "path": "plugins.ndi_plugin.plugin:NDIPlugin", "settings": {
        # Static source list for now; replace with your actual NDI source names/addresses
        "sources": [
            "NDI-Source-1",
            "NDI-Source-2"
        ]
    }},
]

import os
from pathlib import Path

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    # Support .env placed in the orchestrator/ directory or alongside this file
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / ".env",  # orchestrator/.env when running from repo
        here.parent / ".env",          # orchestrator/orchestrator_host/.env fallback
        Path.cwd() / ".env",           # current working directory
    ]
    for env_path in candidates:
        if env_path.exists():
            load_dotenv(env_path)
            break
except Exception:
    pass

def _env(name: str, default: str) -> str:
    return os.getenv(name, default)

MQTT = {
    "host": _env("MQTT_HOST", "10.205.10.7"),
    "port": int(os.getenv("MQTT_PORT", "1883")),
    "username": _env("MQTT_USERNAME", "mqtt"),
    "password": _env("MQTT_PASSWORD", "123456789"),
}


