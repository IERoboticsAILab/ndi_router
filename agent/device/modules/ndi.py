from typing import Dict, Any
from .base import Module
import subprocess, shlex, os, signal, time

class NDIModule(Module):
    name = "ndi"

    def __init__(self, device_id: str, cfg: Dict[str, Any] | None = None):
        super().__init__(device_id, cfg)
        self.viewer_pid: int | None = None
        self.rec_pid: int | None = None

    def on_agent_connect(self) -> None:
        """Export NDI_PATH and adjust LD_LIBRARY_PATH when the agent connects."""
        ndi_path = self.cfg.get("ndi_path")
        ndi_env = self.cfg.get("ndi_env", self.cfg.get("env", {})) or {}
        if isinstance(ndi_path, str) and ndi_path:
            os.environ["NDI_PATH"] = ndi_path
            if self.cfg.get("prepend_ld_library_path", True):
                base = os.path.dirname(ndi_path)
                lp = os.environ.get("LD_LIBRARY_PATH", "")
                os.environ["LD_LIBRARY_PATH"] = f"{base}:{lp}" if lp else base
        if isinstance(ndi_env, dict):
            for k, v in ndi_env.items():
                os.environ[str(k)] = str(v)

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        # Support both legacy keys and new ones
        ndi_path = self.cfg.get("ndi_path")
        if isinstance(ndi_path, str) and ndi_path:
            env["NDI_PATH"] = ndi_path
        return env

    def _spawn(self, cmd: str | list[str]) -> int:
        args = cmd if isinstance(cmd, list) else shlex.split(cmd)
        proc = subprocess.Popen(
            args,
            preexec_fn=os.setsid,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=self._env(),
        )
        return int(proc.pid)

    def _killpg(self, pid: int, sig: signal.Signals = signal.SIGTERM, grace: float = 2.0) -> None:
        if not pid:
            return
        try:
            pgid = os.getpgid(pid)
        except Exception:
            return
        try:
            os.killpg(pgid, sig)
            t0 = time.time()
            while time.time() - t0 < grace:
                try:
                    os.killpg(pgid, 0)
                except ProcessLookupError:
                    return
                time.sleep(0.1)
        except ProcessLookupError:
            return
        # Escalate
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def shutdown(self) -> None:
        if self.rec_pid:
            self._killpg(self.rec_pid, signal.SIGINT)
            self.rec_pid = None
        if self.viewer_pid:
            self._killpg(self.viewer_pid)
            self.viewer_pid = None
        self.state = "idle"
        self.fields.update({"input": None, "pid": None, "recording": False, "record_pid": None})

    def handle_cmd(self, action: str, params: Dict[str, Any]) -> tuple[bool, str | None, dict]:
        if action == "start":
            src = params.get("source")
            if not src:
                return False, "missing source", {}
            if self.viewer_pid:
                self._killpg(self.viewer_pid)
                self.viewer_pid = None
            cmd_t = self.cfg.get("start_cmd_template")
            if not cmd_t:
                return False, "start_cmd_template not set", {}
            cmd = cmd_t.format(source=src, device_id=self.device_id)
            self.viewer_pid = self._spawn(cmd)
            self.state = "running"
            self.fields.update({"input": src, "pid": self.viewer_pid})
            return True, None, {"pid": self.viewer_pid, "input": src}

        if action == "stop":
            if self.viewer_pid:
                self._killpg(self.viewer_pid)
                self.viewer_pid = None
            self.state = "idle"
            self.fields.update({"input": None, "pid": None})
            return True, None, {}

        if action == "set_input":
            src = params.get("source")
            if not src:
                return False, "missing source", {}
            self.fields["input"] = src
            if self.cfg.get("set_input_restart", True):
                if self.viewer_pid:
                    self._killpg(self.viewer_pid)
                    self.viewer_pid = None
                cmd_t = self.cfg.get("start_cmd_template")
                if not cmd_t:
                    return False, "start_cmd_template not set", {}
                cmd = cmd_t.format(source=src, device_id=self.device_id)
                self.viewer_pid = self._spawn(cmd)
                self.fields["pid"] = self.viewer_pid
            return True, None, {"input": src, "pid": self.viewer_pid}

        if action == "record_start":
            src = params.get("source", self.fields.get("input"))
            if not src:
                return False, "no source to record", {}
            if self.rec_pid:
                return True, None, {"recording": True, "record_pid": self.rec_pid}
            cmd_t = self.cfg.get("record_start_cmd_template")
            if not cmd_t:
                return False, "record_start_cmd_template not set", {}
            cmd = cmd_t.format(source=src, device_id=self.device_id)
            self.rec_pid = self._spawn(cmd)
            self.fields.update({"recording": True, "record_pid": self.rec_pid})
            return True, None, {"recording": True, "record_pid": self.rec_pid}

        if action == "record_stop":
            if self.rec_pid:
                self._killpg(self.rec_pid, signal.SIGINT)  # allow graceful finalize
                self.rec_pid = None
            self.fields.update({"recording": False, "record_pid": None})
            return True, None, {"recording": False}

        return False, f"unknown action: {action}", {}
