from typing import Dict, Any
from .base import Module
import subprocess, shlex, os, signal

class NDIModule(Module):
    name = "ndi"

    def __init__(self, device_id: str, cfg: Dict[str, Any] | None = None):
        super().__init__(device_id, cfg)
        self.proc: subprocess.Popen | None = None
        self.rec_proc: subprocess.Popen | None = None
        self.current_source: str | None = None

    def _fmt(self, template: str, source: str | None = None) -> str:
        # Insert the source exactly as provided. 
        return (template or "").format(
            source=source or (self.current_source or ""),
            device_id=self.device_id
        )

    def _run_bg(self, cmd: str) -> subprocess.Popen:
        """Start a subprocess in its own process group (for clean termination).

        Applies environment overrides from module cfg, supporting either:
        - cfg["ndi_path"]: value or string like 'export NDI_PATH=/path/libndi.so'
        - cfg["env"]: dict of additional environment variables
        """
        env = os.environ.copy()
        ndi_path_cfg = self.cfg.get("ndi_path")
        if isinstance(ndi_path_cfg, str):
            val = ndi_path_cfg.strip()
            if val.startswith("export "):
                try:
                    key_val = val.split(None, 1)[1]
                    key, v = key_val.split("=", 1)
                    env[key.strip()] = v.strip().strip('"').strip("'")
                except Exception:
                    pass
            else:
                env["NDI_PATH"] = val
        # Arbitrary env overrides
        extra_env = self.cfg.get("env", {})
        if isinstance(extra_env, dict):
            for k, v in extra_env.items():
                try:
                    env[str(k)] = str(v)
                except Exception:
                    continue

        return subprocess.Popen(
            shlex.split(cmd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            env=env,
        )

    def _kill(self, proc: subprocess.Popen | None):
        """SIGTERM the whole process group if the process is present."""
        if not proc: return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass

    def handle_cmd(self, action: str, params: Dict[str, Any]) -> tuple[bool, str | None, dict]:
        if action == "start":
            src = params.get("source")
            if not src:
                return False, "missing source", {}
            cmd_t = self.cfg.get("start_cmd_template")
            if not cmd_t:
                return False, "start_cmd_template not set", {}
            self._kill(self.proc); self.proc = None
            cmd = self._fmt(cmd_t, source=src)
            self.proc = self._run_bg(cmd)
            self.current_source = src
            self.state = "running"
            self.fields.update({"input": src, "pid": self.proc.pid})
            return True, None, {}

        if action == "stop":
            self._kill(self.proc); self.proc = None
            stop_cmd = self.cfg.get("stop_cmd")
            if stop_cmd:
                self._run_bg(self._fmt(stop_cmd))
            self.state = "idle"
            self.fields.update({"input": None, "pid": None})
            return True, None, {}

        if action == "set_input":
            src = params.get("source")
            if not src:
                return False, "missing source", {}
            self.current_source = src
            self.fields.update({"input": src})
            if self.cfg.get("set_input_restart", True) and self.cfg.get("start_cmd_template"):
                self._kill(self.proc); self.proc = None
                cmd = self._fmt(self.cfg["start_cmd_template"], source=src)
                self.proc = self._run_bg(cmd)
                self.fields.update({"pid": self.proc.pid})
            return True, None, {}

        if action == "record_start":
            if self.rec_proc:
                return True, None, {"note": "recording already running"}
            cmd_t = self.cfg.get("record_start_cmd_template")
            if not cmd_t:
                return False, "record_start_cmd_template not set", {}
            src = params.get("source", self.current_source or "")
            if not src:
                return False, "no source to record", {}
            cmd = self._fmt(cmd_t, source=src)
            self.rec_proc = self._run_bg(cmd)
            self.fields.update({"recording": True, "record_pid": self.rec_proc.pid})
            return True, None, {}

        if action == "record_stop":
            stop_cmd = self.cfg.get("record_stop_cmd")
            if stop_cmd:
                self._run_bg(self._fmt(stop_cmd))
            self._kill(self.rec_proc); self.rec_proc = None
            self.fields.update({"recording": False, "record_pid": None})
            return True, None, {}

        return False, f"unknown action: {action}", {}
