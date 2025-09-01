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

def _env(name: str, default: str) -> str:
    return os.getenv(name, default)

MQTT = {
    "host": _env("MQTT__HOST", "10.205.10.7"),
    "port": int(os.getenv("MQTT__PORT", "1883")),
    "username": _env("MQTT__USERNAME", "mqtt"),
    "password": _env("MQTT__PASSWORD", "123456789"),
}


