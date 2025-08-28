import json, time, uuid
from typing import Dict, Any

# Topic prefixes for the lab MQTT namespace. All producers/consumers should use
# these helpers so topics remain consistent across device and orchestrator code.
LAB_PREFIX = "/lab"
DEVICE_T = LAB_PREFIX + "/device/{device_id}"
MODULE_T = LAB_PREFIX + "/devices/{device_id}/{module}"
ORCH_T   = LAB_PREFIX + "/orchestrator/{module}"

def now_iso() -> str:
    """Return current time in UTC ISO-8601 format with 'Z'."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def jdump(d: Dict[str, Any]) -> str:
    """Compact JSON dump with stable separators for MQTT payloads."""
    return json.dumps(d, separators=(",", ":"), ensure_ascii=False)

def envelope(actor: str, action: str, params: Dict[str, Any] | None = None,
             reply_to: str | None = None, ttl_s: int | None = None,
             req_id: str | None = None) -> Dict[str, Any]:
    """Build a canonical command envelope for app/orchestrator→device messages."""
    return {
        "req_id": req_id or str(uuid.uuid4()),
        "actor": actor,
        "ts": now_iso(),
        "action": action,
        "params": params or {},
        "reply_to": reply_to,
        "ttl_s": ttl_s
    }

def ack(req_id: str, ok: bool, error: str | None = None, details: Dict[str, Any] | None = None):
    """Standard ack payload used for both orchestrator and device module replies."""
    return {"req_id": req_id, "ok": ok, "ts": now_iso(), "error": error, "details": details or {}}

# Topic builders — use these to generate exact topic strings
def t_device_status(device_id): return DEVICE_T.format(device_id=device_id) + "/status"
def t_device_meta(device_id):   return DEVICE_T.format(device_id=device_id) + "/meta"
def t_device_cmd(device_id):    return DEVICE_T.format(device_id=device_id) + "/cmd"

def t_module_cmd(device_id, module):    return MODULE_T.format(device_id=device_id, module=module) + "/cmd"
def t_module_cfg(device_id, module):    return MODULE_T.format(device_id=device_id, module=module) + "/cfg"
def t_module_status(device_id, module): return MODULE_T.format(device_id=device_id, module=module) + "/status"
def t_module_evt(device_id, module):    return MODULE_T.format(device_id=device_id, module=module) + "/evt"

def t_orch_cmd(module): return ORCH_T.format(module=module) + "/cmd"
def t_orch_evt(module): return ORCH_T.format(module=module) + "/evt"
def t_registry():       return LAB_PREFIX + "/orchestrator/registry"
