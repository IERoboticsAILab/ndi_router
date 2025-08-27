import json, yaml, threading
from pathlib import Path
from paho.mqtt.client import Client, MQTTMessage
from typing import Dict, Any
from common import (jdump, now_iso, t_device_meta, t_device_status, t_module_status,
                    t_module_cmd, t_module_cfg, t_module_evt)
from device.modules import MODULE_MAP

class DeviceAgent:
    """RPi-friendly device agent.

    - Loads `device/config.yaml`
    - Instantiates declared modules
    - Connects to the MQTT broker
    - Subscribes for per-module commands and config updates
    - Publishes meta, device status, and module status/acks
    """
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.device_id = cfg["device_id"]
        self.modules: Dict[str, Any] = {}
        for mname in cfg["modules"].keys():
            if mname not in MODULE_MAP:
                raise ValueError(f"Unknown module in config: {mname}")
            self.modules[mname] = MODULE_MAP[mname](self.device_id, cfg["modules"][mname])
        self.client = Client(client_id=f"device-{self.device_id}", clean_session=True)
        self._setup_mqtt()

    def _setup_mqtt(self):
        """Configure credentials, will message, callbacks, and connect."""
        m = self.cfg["mqtt"]
        self.client.username_pw_set(m.get("username"), m.get("password"))
        # LWT -> offline
        self.client.will_set(t_device_status(self.device_id), jdump({"online": False, "ts": now_iso()}), qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(m.get("host", "127.0.0.1"), m.get("port", 1883), keepalive=30)

    def start(self):
        # Start network loop and publish birth messages
        self.client.loop_start()
        self.publish_meta()
        self.publish_device_status({"online": True})
        # Subscribe to module topics
        for mname in self.modules.keys():
            self.client.subscribe(t_module_cmd(self.device_id, mname), qos=1)
            self.client.subscribe(t_module_cfg(self.device_id, mname), qos=1)

    def on_connect(self, client, userdata, flags, rc):
        # Re-subscribe happens automatically; publish statuses
        for mname, mod in self.modules.items():
            self.publish_module_status(mname, mod.status_payload())

    def publish_meta(self):
        meta = {
            "device_id": self.device_id,
            "modules": list(self.modules.keys()),
            "capabilities": {m: self.modules[m].cfg for m in self.modules},
            "version": "dev-0.1.0",
            "ts": now_iso()
        }
        self.client.publish(t_device_meta(self.device_id), jdump(meta), qos=1, retain=True)

    def publish_device_status(self, extra: Dict[str, Any] | None = None):
        payload = {"online": True, "ts": now_iso()}
        if extra: payload.update(extra)
        self.client.publish(t_device_status(self.device_id), jdump(payload), qos=1, retain=True)

    def publish_module_status(self, mname: str, status: Dict[str, Any]):
        self.client.publish(t_module_status(self.device_id, mname), jdump(status), qos=0, retain=True)

    def on_message(self, client: Client, userdata, msg: MQTTMessage):
        topic = msg.topic
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        for mname, mod in self.modules.items():
            if topic == t_module_cmd(self.device_id, mname):
                req_id = data.get("req_id")
                ok, err, details = mod.handle_cmd(data.get("action", ""), data.get("params", {}))
                self.publish_module_status(mname, mod.status_payload())
                # ack
                evt_topic = t_module_evt(self.device_id, mname)
                ack_payload = {"req_id": req_id, "ok": ok, "ts": now_iso(), "error": err, "details": details}
                self.client.publish(evt_topic, jdump(ack_payload), qos=1)
            elif topic == t_module_cfg(self.device_id, mname):
                mod.apply_cfg(data)
                self.publish_module_status(mname, mod.status_payload())

def main():
    cfg = yaml.safe_load(Path(__file__).with_name("config.yaml").read_text())
    agent = DeviceAgent(cfg)
    agent.start()
    # Keep alive
    threading.Event().wait()

if __name__ == "__main__":
    main()
