PLUGINS = [
    {"module": "ndi", "path": "plugins.ndi_plugin.plugin:NDIPlugin", "settings": {
        # Static source list for now; replace with your actual NDI source names/addresses
        "sources": [
            "NDI-Source-1",
            "NDI-Source-2"
        ]
    }},
]

MQTT = {"host": "10.205.10.7", "port": 1883, "username": "mqtt", "password": "123456789"}


