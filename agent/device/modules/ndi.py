from typing import Dict, Any
from .base import Module
import subprocess, shlex, os, signal, time, logging

logger = logging.getLogger("device.ndi")

class NDIModule(Module):
    name = "ndi"

    def __init__(self, device_id: str, cfg: Dict[str, Any] | None = None):
        super().__init__(device_id, cfg)
        self.viewer_pid: int | None = None
        self.rec_pid: int | None = None

    def on_agent_connect(self) -> None:
        """Export NDI_PATH and inject custom env when the agent connects."""
        ndi_path = self.cfg.get("ndi_path")
        ndi_env = self.cfg.get("ndi_env", self.cfg.get("env", {})) or {}
        if isinstance(ndi_path, str) and ndi_path:
            os.environ["NDI_PATH"] = ndi_path
            logger.info("NDI env configured: NDI_PATH=%s", ndi_path)
        if isinstance(ndi_env, dict):
            for k, v in ndi_env.items():
                os.environ[str(k)] = str(v)
            if ndi_env:
                logger.info("Injected %d custom env vars for NDI", len(ndi_env))

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        # Support both legacy keys and new ones
        ndi_path = self.cfg.get("ndi_path")
        if isinstance(ndi_path, str) and ndi_path:
            env["NDI_PATH"] = ndi_path
        return env

    def _spawn(self, cmd: str | list[str]) -> int:
        args = cmd if isinstance(cmd, list) else shlex.split(cmd)
        logger.info("Spawning process: %s", " ".join(shlex.quote(a) for a in args))
        try:
            proc = subprocess.Popen(
                args,
                preexec_fn=os.setsid,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._env(),
            )
        except FileNotFoundError as e:
            logger.error("Executable not found when starting: %s", e)
            raise
        except Exception as e:
            logger.exception("Failed to start process: %s", e)
            raise
        pid = int(proc.pid)
        logger.info("Started process pid=%d", pid)
        return pid

    def _process_exists(self, pid: int) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process may exist but we cannot signal it
            return True

    def _killpg(self, pid: int, sig: signal.Signals = signal.SIGTERM, grace: float = 2.0) -> None:
        if not pid:
            return
        try:
            pgid = os.getpgid(pid)
        except Exception:
            return
        try:
            logger.info("Sending %s to pgid=%d (pid=%d)", sig.name if hasattr(sig, 'name') else str(sig), pgid, pid)
            os.killpg(pgid, sig)
            t0 = time.time()
            while time.time() - t0 < grace:
                try:
                    os.killpg(pgid, 0)
                except ProcessLookupError:
                    logger.info("Process group %d terminated", pgid)
                    return
                time.sleep(0.1)
        except ProcessLookupError:
            return
        # Escalate
        try:
            logger.warning("Escalating to SIGKILL for pgid=%d", pgid)
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
            logger.info("Starting NDI viewer for source=%s", src)
            try:
                self.viewer_pid = self._spawn(cmd)
            except Exception as e:
                return False, f"spawn_failed:{e}", {}
            # Briefly verify the process exists
            time.sleep(0.1)
            if not self._process_exists(self.viewer_pid):
                logger.error("Viewer process exited immediately (pid=%s)", str(self.viewer_pid))
                self.viewer_pid = None
                self.state = "idle"
                self.fields.update({"input": None, "pid": None})
                return False, "viewer_exited_early", {}
            self.state = "running"
            self.fields.update({"input": src, "pid": self.viewer_pid})
            logger.info("NDI viewer running pid=%d input=%s", self.viewer_pid, src)
            return True, None, {"pid": self.viewer_pid, "input": src}

        if action == "stop":
            if self.viewer_pid:
                self._killpg(self.viewer_pid)
                self.viewer_pid = None
            self.state = "idle"
            self.fields.update({"input": None, "pid": None})
            logger.info("NDI viewer stopped")
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
                logger.info("Restarting NDI viewer with new input=%s", src)
                try:
                    self.viewer_pid = self._spawn(cmd)
                except Exception as e:
                    return False, f"spawn_failed:{e}", {}
                time.sleep(0.1)
                if not self._process_exists(self.viewer_pid):
                    logger.error("Viewer process exited immediately after restart (pid=%s)", str(self.viewer_pid))
                    self.viewer_pid = None
                    self.fields["pid"] = None
                    return False, "viewer_exited_early", {"input": src}
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
            logger.info("Starting NDI recorder for source=%s", src)
            try:
                self.rec_pid = self._spawn(cmd)
            except Exception as e:
                return False, f"spawn_failed:{e}", {}
            time.sleep(0.1)
            if not self._process_exists(self.rec_pid):
                logger.error("Recorder process exited immediately (pid=%s)", str(self.rec_pid))
                self.rec_pid = None
                self.fields.update({"recording": False, "record_pid": None})
                return False, "recorder_exited_early", {}
            self.fields.update({"recording": True, "record_pid": self.rec_pid})
            return True, None, {"recording": True, "record_pid": self.rec_pid}

        if action == "record_stop":
            if self.rec_pid:
                self._killpg(self.rec_pid, signal.SIGINT)  # allow graceful finalize
                self.rec_pid = None
            self.fields.update({"recording": False, "record_pid": None})
            logger.info("NDI recorder stopped")
            return True, None, {"recording": False}

        return False, f"unknown action: {action}", {}
