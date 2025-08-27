import time
from typing import Dict, Any


class Registry:
    def __init__(self):
        self.devices: Dict[str, Any] = {}   # merge from device meta/status
        self.locks: Dict[str, Any] = {}     # key "module:device" -> {holder, exp}

    def lock(self, key: str, holder: str, ttl_s: int) -> bool:
        exp = time.time() + ttl_s
        cur = self.locks.get(key)
        if cur and cur["exp"] > time.time() and cur["holder"] != holder:
            return False
        self.locks[key] = {"holder": holder, "exp": exp}
        return True

    def release(self, key: str, holder: str) -> bool:
        cur = self.locks.get(key)
        if not cur or cur["holder"] != holder:
            return False
        del self.locks[key]
        return True

    def snapshot(self) -> Dict[str, Any]:
        return {"devices": self.devices, "locks": self.locks}

    def can_use(self, key: str, actor: str) -> bool:
        cur = self.locks.get(key)
        if not cur:
            return True
        if cur.get("exp", 0) <= time.time():
            return True
        return cur.get("holder") == actor


