import json, time, uuid, datetime
from typing import Dict, Any

# Topic prefixes for the lab MQTT namespace. All producers/consumers should use
# these helpers so topics remain consistent across device and orchestrator code.
LAB_PREFIX = "/lab"
DEVICE_T = LAB_PREFIX + "/device/{device_id}"
MODULE_T = LAB_PREFIX + "/device/{device_id}/{module}"
ORCH_T   = LAB_PREFIX + "/orchestrator/{module}"

# Envelope/validation settings
MAX_PARAMS_BYTES = 16384
ALLOWED_ACTORS = {"orchestrator", "app", "user", "test"}

def now_iso() -> str:
    """Return current time in UTC ISO-8601 format with 'Z'."""
    try:
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    except Exception:
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
    """Legacy ack payload. Prefer make_ack for standardized acks."""
    return {"req_id": req_id, "ok": ok, "ts": now_iso(), "error": error, "details": details or {}}

# New helpers for validation and standardized acks
def deep_merge(a: Dict[str, Any], b: Dict[str, Any] | None):
    for k, v in (b or {}).items():
        if k in a and isinstance(a[k], dict) and isinstance(v, dict):
            deep_merge(a[k], v)
        else:
            a[k] = v
    return a

def parse_json(raw: bytes):
    try:
        return True, json.loads(raw.decode("utf-8")), None
    except Exception as e:
        return False, None, f"bad_json:{e}"

def validate_envelope(p: Dict[str, Any]):
    if not isinstance(p, dict):
        return False, "bad_request:not_object"
    if "action" not in p or not isinstance(p["action"], str) or not p["action"]:
        return False, "bad_request:missing_action"
    actor = p.get("actor")
    if actor and actor not in ALLOWED_ACTORS:
        return False, f"bad_request:actor_not_allowed:{actor}"
    params = p.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return False, "bad_request:params_not_object"
    if len(json.dumps(params).encode("utf-8")) > MAX_PARAMS_BYTES:
        return False, "bad_request:params_too_large"
    if "req_id" not in p or not isinstance(p["req_id"], str) or not p["req_id"]:
        p["req_id"] = str(uuid.uuid4())
    if "ts" not in p:
        p["ts"] = now_iso()
    p["params"] = params
    return True, None

def make_ack(req_id: str, ok: bool, action: str, actor: str | None = None,
             code: str = "OK", error: str | None = None, details: Dict[str, Any] | None = None):
    return {
        "req_id": req_id,
        "ok": bool(ok),
        "code": code if ok else (code or "ERROR"),
        "action": action,
        "actor": actor,
        "ts": now_iso(),
        "error": error,
        "details": details or {},
    }

# Topic builders — use these to generate exact topic strings
def t_device_status(device_id): return DEVICE_T.format(device_id=device_id) + "/status"
def t_device_meta(device_id):   return DEVICE_T.format(device_id=device_id) + "/meta"
def t_device_cmd(device_id):    return DEVICE_T.format(device_id=device_id) + "/cmd"
def t_device_evt(device_id):    return DEVICE_T.format(device_id=device_id) + "/evt"

def t_module_cmd(device_id, module):    return MODULE_T.format(device_id=device_id, module=module) + "/cmd"
def t_module_cfg(device_id, module):    return MODULE_T.format(device_id=device_id, module=module) + "/cfg"
def t_module_status(device_id, module): return MODULE_T.format(device_id=device_id, module=module) + "/status"
def t_module_evt(device_id, module):    return MODULE_T.format(device_id=device_id, module=module) + "/evt"

def t_orch_cmd(module): return ORCH_T.format(module=module) + "/cmd"
def t_orch_evt(module): return ORCH_T.format(module=module) + "/evt"
def t_registry():       return LAB_PREFIX + "/orchestrator/registry"
