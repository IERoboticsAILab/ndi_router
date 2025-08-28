import json, yaml, threading
from pathlib import Path
from paho.mqtt.client import Client, MQTTMessage
from typing import Dict, Any
from common import (jdump, now_iso, ack, t_device_meta, t_device_status, t_device_cmd, t_device_evt,
                    t_module_status, t_module_cmd, t_module_cfg, t_module_evt, parse_json, validate_envelope,
                    make_ack, deep_merge, MAX_PARAMS_BYTES)
from device.modules import MODULE_MAP
import signal, time

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
        self.labels = cfg.get("labels", [])
        self.modules: Dict[str, Any] = {}
        modules_cfg: Dict[str, Any] = {}
        features_cfg: Dict[str, Any] = cfg.get("features") or {}
        feature_name = cfg.get("feature")
        if feature_name and feature_name in features_cfg:
            preset = features_cfg.get(feature_name) or {}
            if isinstance(preset, dict):
                modules_cfg.update(preset)
        explicit = cfg.get("modules") or {}
        if isinstance(explicit, dict):
            modules_cfg.update(explicit)
        for mname, mcfg in modules_cfg.items():
            if mname not in MODULE_MAP:
                raise ValueError(f"Unknown module in config: {mname}")
            self.modules[mname] = MODULE_MAP[mname](self.device_id, mcfg)
        self.client = Client(client_id=f"device-{self.device_id}", clean_session=True)
        self.heartbeat_interval_s = int(cfg.get("heartbeat_interval_s", 10))
        self._hb_stop = threading.Event()
        self._setup_mqtt()

    def _setup_mqtt(self):
        """Configure credentials, will message, callbacks, and connect."""
        m = self.cfg["mqtt"]
        self.client.username_pw_set(m.get("username"), m.get("password"))
        # LWT -> offline (broker will publish this on unexpected disconnect)
        lwt_payload = jdump({"online": False, "ts": now_iso(), "device_id": self.device_id})
        self.client.will_set(t_device_status(self.device_id), lwt_payload, qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(m.get("host", "127.0.0.1"), m.get("port", 1883), keepalive=30)

    def start(self):
        # Start network loop and publish birth messages
        self.client.loop_start()
        self.publish_meta()
        self.publish_device_status({"online": True, "device_id": self.device_id})
        # Subscribe to device + module topics
        self.client.subscribe(t_device_cmd(self.device_id), qos=1)
        for mname in self.modules.keys():
            self._subscribe_module_topics(mname)
        # Heartbeat loop
        threading.Thread(target=self._heartbeat_loop, name="hb", daemon=True).start()

    def _pub(self, topic: str, payload: Dict[str, Any], qos: int = 1, retain: bool = False) -> None:
        self.client.publish(topic, json.dumps(payload), qos=qos, retain=retain)

    def _heartbeat_loop(self):
        while not self._hb_stop.wait(self.heartbeat_interval_s):
            self.publish_device_status({"online": True, "device_id": self.device_id})

    def shutdown(self):
        # Stop heartbeat and best-effort offline publish
        self._hb_stop.set()
        try:
            self.publish_device_status({"online": False, "device_id": self.device_id})
            time.sleep(0.2)
        except Exception:
            pass
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def _subscribe_module_topics(self, mname: str) -> None:
        self.client.subscribe(t_module_cmd(self.device_id, mname), qos=1)
        self.client.subscribe(t_module_cfg(self.device_id, mname), qos=1)

    def _unsubscribe_module_topics(self, mname: str) -> None:
        self.client.unsubscribe(t_module_cmd(self.device_id, mname))
        self.client.unsubscribe(t_module_cfg(self.device_id, mname))

    def on_connect(self, client, userdata, flags, rc):
        # Re-subscribe happens automatically; publish statuses
        for mname, mod in self.modules.items():
            try:
                if hasattr(mod, "on_agent_connect"):
                    mod.on_agent_connect()
            except Exception:
                pass
            self.publish_module_status(mname, mod.status_payload())

    def publish_meta(self):
        meta = {
            "device_id": self.device_id,
            "modules": list(self.modules.keys()),
            "capabilities": {m: self.modules[m].cfg for m in self.modules},
            "labels": self.labels,
            "feature": self.cfg.get("feature"),
            "version": "dev-0.1.0",
            "ts": now_iso()
        }
        self.client.publish(t_device_meta(self.device_id), jdump(meta), qos=1, retain=True)

    def publish_device_status(self, extra: Dict[str, Any] | None = None):
        payload = {"online": True, "ts": now_iso(), "device_id": self.device_id}
        if extra: payload.update(extra)
        self.client.publish(t_device_status(self.device_id), jdump(payload), qos=1, retain=True)

    def publish_module_status(self, mname: str, status: Dict[str, Any]):
        self.client.publish(t_module_status(self.device_id, mname), jdump(status), qos=1, retain=True)

    def on_message(self, client: Client, userdata, msg: MQTTMessage):
        topic = msg.topic
        # Device-level commands
        if topic == t_device_cmd(self.device_id):
            ok, p, err = parse_json(msg.payload)
            evt_t = t_device_evt(self.device_id)
            if not ok:
                self._pub(evt_t, make_ack("?", False, "?", code="BAD_JSON", error=err)); return
            ok, verr = validate_envelope(p)
            if not ok:
                self._pub(evt_t, make_ack(p.get("req_id","?"), False, p.get("action","?"), p.get("actor"), code="BAD_REQUEST", error=verr)); return
            action = p["action"]; params = p["params"]; rid = p["req_id"]; actor = p.get("actor")
            try:
                ok, error, details = self.handle_device_cmd(action, params)
                self._pub(evt_t, make_ack(rid, ok, action, actor, code=("OK" if ok else "DEVICE_ERROR"), error=error, details=details))
            except Exception as e:
                self._pub(evt_t, make_ack(rid, False, action, actor, code="EXCEPTION", error=str(e)))
            return
        # Module-level commands/config
        for mname, mod in list(self.modules.items()):
            if topic == t_module_cmd(self.device_id, mname):
                ok, p, err = parse_json(msg.payload)
                evt_t = t_module_evt(self.device_id, mname)
                if not ok:
                    self._pub(evt_t, make_ack("?", False, "?", code="BAD_JSON", error=err)); return
                ok, verr = validate_envelope(p)
                if not ok:
                    self._pub(evt_t, make_ack(p.get("req_id","?"), False, p.get("action","?"), p.get("actor"), code="BAD_REQUEST", error=verr)); return
                action = p["action"]; params = p["params"]; rid = p["req_id"]; actor = p.get("actor")
                try:
                    ok, err_msg, details = mod.handle_cmd(action, params)
                    self.publish_module_status(mname, mod.status_payload())
                    self._pub(evt_t, make_ack(rid, ok, action, actor, code=("OK" if ok else "MODULE_ERROR"), error=err_msg, details=details))
                except Exception as e:
                    self._pub(evt_t, make_ack(rid, False, action, actor, code="EXCEPTION", error=str(e)))
                return
            if topic == t_module_cfg(self.device_id, mname):
                ok, p, err = parse_json(msg.payload)
                evt_t = t_module_evt(self.device_id, mname)
                if not ok:
                    self._pub(evt_t, make_ack("?", False, "cfg", code="BAD_JSON", error=err)); return
                if not isinstance(p, dict):
                    self._pub(evt_t, make_ack("?", False, "cfg", code="BAD_REQUEST", error="cfg_not_object")); return
                try:
                    if len(json.dumps(p).encode("utf-8")) > MAX_PARAMS_BYTES:
                        self._pub(evt_t, make_ack(p.get("req_id","?"), False, "cfg", code="BAD_REQUEST", error="cfg_too_large")); return
                except Exception:
                    pass
                try:
                    # Deep-merge configuration
                    mod.cfg = deep_merge(mod.cfg, p)
                    self.publish_module_status(mname, mod.status_payload())
                    self._pub(evt_t, make_ack(p.get("req_id","?"), True, "cfg"))
                except Exception as e:
                    self._pub(evt_t, make_ack(p.get("req_id","?"), False, "cfg", code="EXCEPTION", error=str(e)))
                return

    def handle_device_cmd(self, action: str, params: Dict[str, Any]) -> tuple[bool, str | None, Dict[str, Any]]:
        if action == "ping":
            return True, None, {"device_id": self.device_id, "ts": now_iso()}

        if action == "set_labels":
            labels = params.get("labels")
            if not isinstance(labels, list):
                return False, "labels must be a list", {}
            self.labels = labels
            self.cfg["labels"] = labels
            self.publish_meta()
            return True, None, {"labels": labels}

        if action == "add_module":
            mname = params.get("name")
            mcfg = params.get("cfg", {}) or {}
            if not mname:
                return False, "missing module name", {}
            if mname not in MODULE_MAP:
                return False, f"unknown module: {mname}", {}
            if mname in self.modules:
                self.modules[mname].apply_cfg(mcfg)
                self.publish_module_status(mname, self.modules[mname].status_payload())
                self.publish_meta()
                return True, None, {"updated": True}
            mod = MODULE_MAP[mname](self.device_id, mcfg)
            self.modules[mname] = mod
            self._subscribe_module_topics(mname)
            self.publish_module_status(mname, mod.status_payload())
            self.publish_meta()
            return True, None, {"added": mname}

        if action == "remove_module":
            mname = params.get("name")
            if not mname or mname not in self.modules:
                return False, "module not found", {}
            try:
                self._unsubscribe_module_topics(mname)
            except Exception:
                pass
            try:
                self.modules[mname].shutdown()
            except Exception:
                pass
            del self.modules[mname]
            self.publish_meta()
            return True, None, {"removed": mname}

        if action == "apply_feature":
            feature_name = params.get("feature")
            features_cfg = self.cfg.get("features") or {}
            if not feature_name or feature_name not in features_cfg:
                return False, "unknown feature", {}
            new_modules_cfg = features_cfg.get(feature_name) or {}
            # Tear down existing modules
            for existing in list(self.modules.keys()):
                try:
                    self._unsubscribe_module_topics(existing)
                except Exception:
                    pass
                try:
                    self.modules[existing].shutdown()
                except Exception:
                    pass
                del self.modules[existing]
            # Create new modules
            for new_name, new_cfg in (new_modules_cfg or {}).items():
                if new_name not in MODULE_MAP:
                    continue
                mod = MODULE_MAP[new_name](self.device_id, new_cfg)
                self.modules[new_name] = mod
                self._subscribe_module_topics(new_name)
                self.publish_module_status(new_name, mod.status_payload())
            self.cfg["feature"] = feature_name
            self.publish_meta()
            return True, None, {"feature": feature_name, "modules": list(self.modules.keys())}

        return False, f"unknown action: {action}", {}

def main():
    cfg = yaml.safe_load(Path(__file__).with_name("config.yaml").read_text())
    agent = DeviceAgent(cfg)
    agent.start()

    def _graceful(*_):
        agent.shutdown()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)
    # Keep alive
    threading.Event().wait()

if __name__ == "__main__":
    main()
