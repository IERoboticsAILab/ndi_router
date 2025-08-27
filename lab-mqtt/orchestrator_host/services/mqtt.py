import json, paho.mqtt.client as mqtt
from typing import Callable, Dict, Any, Iterable


class SharedMQTT:
    def __init__(self, host: str, port: int, username: str = None, password: str = None):
        self.client = mqtt.Client()
        if username:
            self.client.username_pw_set(username, password)
        self._handlers = []  # list[(filters: Iterable[str], cb: Callable)]
        self.client.on_message = self._on_message
        self.client.connect(host, port, 60)
        self.client.loop_start()

    def subscribe(self, filters: Iterable[str], cb: Callable[[str, Dict[str, Any]], None]):
        self._handlers.append((list(filters), cb))
        for f in filters:
            self.client.subscribe(f, qos=1)

    def publish_json(self, topic: str, obj: Dict[str, Any], qos=1, retain=False):
        self.client.publish(topic, json.dumps(obj), qos=qos, retain=retain)

    def _on_message(self, _c, _u, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        for filters, cb in self._handlers:
            if any(self._match(msg.topic, f) for f in filters):
                cb(msg.topic, payload)

    @staticmethod
    def _match(topic: str, pattern: str) -> bool:
        # support '+' single-level wildcard
        t = topic.split('/')
        p = pattern.split('/')
        if len(t) != len(p):
            return False
        for a, b in zip(t, p):
            if b == '+':
                continue
            if a != b:
                return False
        return True


