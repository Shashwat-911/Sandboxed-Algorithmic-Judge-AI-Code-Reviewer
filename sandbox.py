"""
sandbox.py — Secure ephemeral Docker container executor.

Security constraints applied to EVERY execution container:
  • network_mode=none          — zero network access
  • mem_limit=128m             — hard memory ceiling
  • memswap_limit=128m         — no swap headroom
  • cpu_quota/cpu_period=1.0   — exactly 1 CPU core
  • pids_limit=50              — fork-bomb prevention
  • read_only=True             — immutable rootfs
  • cap_drop=["ALL"]           — no Linux capabilities
  • security_opt=no-new-priv   — no setuid escalation
  • user=nobody                — non-root execution

C++ / Java two-phase strategy:
  Phase 1 — Compile: separate container, timeout=SANDBOX_TIMEOUT, 256 MB RAM
             (GCC / javac are memory-hungry; compilation time NOT counted).
  Phase 2 — Execute: separate container, timeout=SANDBOX_TIMEOUT, 128 MB RAM
             Execution wall-clock time IS recorded.

The workspace directory lives under SANDBOX_BASE_DIR which is bind-mounted
identically in both the Celery worker container and exposed to the host Docker
daemon, so sibling containers can mount the same host path without any path
translation.
"""

import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional

import docker
from docker.errors import ContainerError, DockerException, NotFound
from docker.models.containers import Container

from config import settings

log = logging.getLogger(__name__)

# ─── Language image / command map ────────────────────────────────────────────

LANGUAGE_CONFIGS: dict[str, dict] = {
    "python": {
        "image": "python:3.11-alpine",
        "filename": "solution.py",
        "run_cmd": ["python3", "/tmp/workspace/solution.py"],
        "multi_phase": False,
    },
    "javascript": {
        "image": "node:20-alpine",
        "filename": "solution.js",
        "run_cmd": ["node", "/tmp/workspace/solution.js"],
        "multi_phase": False,
    },
    "cpp": {
        "image": "gcc:13",
        "filename": "solution.cpp",
        # Compile writes the binary into the shared workspace dir
        "compile_cmd": [
            "gcc",
            "/tmp/workspace/solution.cpp",
            "-o", "/tmp/workspace/solution",
            "-O2", "-std=c++17", "-lm",
        ],
        "run_cmd": ["/tmp/workspace/solution"],
        "multi_phase": True,
    },
    "java": {
        "image": "openjdk:21-slim",
        "filename": "Main.java",
        "compile_cmd": ["javac", "/tmp/workspace/Main.java"],
        "run_cmd": ["java", "-cp", "/tmp/workspace", "Main"],
        "multi_phase": True,
    },
}

# Max bytes we capture from stdout/stderr to prevent OOM from runaway output
MAX_OUTPUT_BYTES = 1024 * 16  # 16 KB


@dataclass
class SandboxResult:
    status: str                          # SUCCESS | FAILED | TIMEOUT | COMPILE_ERROR | ERROR
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    execution_time_ms: float = 0.0
    error: Optional[str] = None


class DockerSandbox:
    """
    Launches ephemeral sibling Docker containers to execute untrusted code.

    The client connects to the docker-socket-proxy TCP endpoint defined by
    DOCKER_HOST in the environment — never to the raw /var/run/docker.sock.
    """

    def __init__(self) -> None:
        # docker.from_env() honours the DOCKER_HOST env var automatically.
        # In the worker service DOCKER_HOST=tcp://docker-socket-proxy:2375.
        self.client = docker.from_env()
        os.makedirs(settings.SANDBOX_BASE_DIR, exist_ok=True)

    # ─── Public API ──────────────────────────────────────────────────────────

    def run(self, code: str, language: str) -> SandboxResult:
        """Entry point: choose single or two-phase execution."""
        cfg = LANGUAGE_CONFIGS.get(language)
        if cfg is None:
            return SandboxResult(
                status="ERROR",
                error=f"Unsupported language: {language}",
            )

        workspace = tempfile.mkdtemp(dir=settings.SANDBOX_BASE_DIR)
        try:
            # Write source file
            src_path = os.path.join(workspace, cfg["filename"])
            with open(src_path, "w", encoding="utf-8") as fh:
                fh.write(code)

            if cfg["multi_phase"]:
                return self._run_two_phase(cfg, workspace)
            else:
                return self._run_single_phase(cfg, workspace)
        except Exception as exc:
            log.exception("Unexpected sandbox error")
            return SandboxResult(status="ERROR", error=str(exc))
        finally:
            # Always nuke the workspace directory on the host
            shutil.rmtree(workspace, ignore_errors=True)

    # ─── Execution strategies ─────────────────────────────────────────────────

    def _run_single_phase(self, cfg: dict, workspace: str) -> SandboxResult:
        """Python / JavaScript — one container, measure its wall-clock time."""
        result = self._run_container(
            image=cfg["image"],
            command=cfg["run_cmd"],
            workspace=workspace,
            mem_limit="128m",
            measure_time=True,
        )
        if result.exit_code == 0:
            result.status = "SUCCESS"
        elif result.status != "TIMEOUT":
            result.status = "FAILED"
        return result

    def _run_two_phase(self, cfg: dict, workspace: str) -> SandboxResult:
        """
        C++ / Java — two separate containers:
          1. Compile  → 256 MB RAM, 5 s timeout, time NOT counted.
          2. Execute  → 128 MB RAM, 5 s timeout, time IS counted.
        """
        # ── Phase 1: Compile ──────────────────────────────────────────────
        compile_result = self._run_container(
            image=cfg["image"],
            command=cfg["compile_cmd"],
            workspace=workspace,
            mem_limit="256m",   # GCC/javac are memory-hungry
            measure_time=False,
        )

        if compile_result.status == "TIMEOUT":
            return SandboxResult(
                status="COMPILE_ERROR",
                stderr="Compilation timed out after "
                       f"{settings.SANDBOX_TIMEOUT} seconds.",
                exit_code=compile_result.exit_code,
            )

        if compile_result.exit_code != 0:
            return SandboxResult(
                status="COMPILE_ERROR",
                stderr=compile_result.stderr,
                exit_code=compile_result.exit_code,
            )

        log.info("Compilation succeeded — launching execution container.")

        # ── Phase 2: Execute ──────────────────────────────────────────────
        run_result = self._run_container(
            image=cfg["image"],
            command=cfg["run_cmd"],
            workspace=workspace,
            mem_limit="128m",
            measure_time=True,
        )

        if run_result.exit_code == 0:
            run_result.status = "SUCCESS"
        elif run_result.status != "TIMEOUT":
            run_result.status = "FAILED"
        return run_result

    # ─── Low-level container runner ───────────────────────────────────────────

    def _run_container(
        self,
        *,
        image: str,
        command: list[str],
        workspace: str,
        mem_limit: str,
        measure_time: bool,
    ) -> SandboxResult:
        """
        Spin up a single hardened container, wait for it (with timeout),
        capture logs, and guarantee removal.
        """
        container: Optional[Container] = None
        timed_out = False
        start_ns = 0.0

        try:
            container = self.client.containers.run(
                image=image,
                command=command,
                # ── Workspace bind-mount (host path ↔ container /tmp/workspace) ──
                # workspace is under SANDBOX_BASE_DIR which is bind-mounted
                # identically in the worker and visible to the Docker daemon.
                volumes={
                    workspace: {"bind": "/tmp/workspace", "mode": "rw"}
                },
                # ── Network ──────────────────────────────────────────────────
                network_mode="none",
                # ── Memory ───────────────────────────────────────────────────
                mem_limit=mem_limit,
                memswap_limit=mem_limit,   # Prevent swap bypass
                # ── CPU — exactly 1 core ──────────────────────────────────────
                cpu_quota=100_000,
                cpu_period=100_000,
                # ── Process limit (fork-bomb mitigation) ──────────────────────
                pids_limit=50,
                # ── Filesystem ────────────────────────────────────────────────
                read_only=True,
                tmpfs={"/tmp": "size=10m,exec"},  # Runtime scratch; workspace overlays this
                # ── Privilege hardening ───────────────────────────────────────
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                user="nobody",
                # ── Lifecycle ─────────────────────────────────────────────────
                detach=True,
                remove=False,   # We remove manually in finally so we can read logs
            )

            if measure_time:
                start_ns = time.monotonic()

            exit_info = container.wait(timeout=settings.SANDBOX_TIMEOUT)
            elapsed_ms = (time.monotonic() - start_ns) * 1000 if measure_time else 0.0
            exit_code: int = exit_info.get("StatusCode", -1)

        except Exception as exc:
            # docker SDK raises requests.exceptions.ReadTimeout on wait() timeout
            exc_name = type(exc).__name__
            if "Timeout" in exc_name or "ReadTimeout" in exc_name:
                timed_out = True
                elapsed_ms = settings.SANDBOX_TIMEOUT * 1000.0
                exit_code = -1
            else:
                log.exception("Container run error: %s", exc)
                return SandboxResult(status="ERROR", error=str(exc))
        finally:
            if container is not None:
                try:
                    container.kill()
                except Exception:
                    pass  # Already dead — ignore
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        if timed_out:
            return SandboxResult(
                status="TIMEOUT",
                stdout="",
                stderr=f"Execution exceeded {settings.SANDBOX_TIMEOUT} second timeout.",
                exit_code=-1,
                execution_time_ms=elapsed_ms,
            )

        # Capture and truncate output
        raw_logs = container.logs(stdout=True, stderr=True) if container else b""  # noqa: F821
        # After remove() container obj still holds the log data fetched before removal
        # Re-fetch individually for cleaner separation:
        try:
            stdout_raw = container.logs(stdout=True, stderr=False)[-MAX_OUTPUT_BYTES:]
            stderr_raw = container.logs(stdout=False, stderr=True)[-MAX_OUTPUT_BYTES:]
        except Exception:
            stdout_raw = raw_logs[-MAX_OUTPUT_BYTES:]
            stderr_raw = b""

        return SandboxResult(
            status="PENDING",   # Caller sets final status
            stdout=stdout_raw.decode("utf-8", errors="replace").strip(),
            stderr=stderr_raw.decode("utf-8", errors="replace").strip(),
            exit_code=exit_code,
            execution_time_ms=round(elapsed_ms, 3) if measure_time else 0.0,
        )
