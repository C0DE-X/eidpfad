#!/usr/bin/env python3
"""Run the real Godot menu flow against an isolated local Eidpfad server."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_server(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(f"Server exited before readiness.\n{stdout}\n{stderr}")
        try:
            with urlopen(f"{url}/health/ready", timeout=1.0) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.1)
    raise TimeoutError("Server did not become ready within 20 seconds")


def stop(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        process.terminate()
        try:
            return process.communicate(timeout=8.0)
        except subprocess.TimeoutExpired:
            process.kill()
    return process.communicate()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="eidpfad-client-smoke-") as temporary:
        temp = Path(temporary)
        port = free_port()
        server_url = f"http://127.0.0.1:{port}"
        server_env = os.environ.copy()
        server_env.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": f"sqlite:///{temp / 'smoke.db'}",
                "PYTHONPATH": str(ROOT / "server"),
            }
        )
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=server_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_for_server(server_url, server)
            client_env = os.environ.copy()
            client_env.update(
                {
                    "HOME": str(temp / "home"),
                    "XDG_CONFIG_HOME": str(temp / "config"),
                    "XDG_DATA_HOME": str(temp / "data"),
                    "XDG_CACHE_HOME": str(temp / "cache"),
                }
            )
            result = subprocess.run(
                [
                    args.godot,
                    "--headless",
                    "--path",
                    str(ROOT / "client"),
                    "--script",
                    "res://tests/menu_flow_smoke.gd",
                    "--",
                    "--server-url",
                    server_url,
                ],
                cwd=ROOT,
                env=client_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120.0,
            )
        finally:
            server_stdout, server_stderr = stop(server)

    print(result.stdout, end="")
    if result.returncode != 0 or "CLIENT_MENU_FLOW_OK" not in result.stdout:
        print("Server stdout:\n" + server_stdout, file=sys.stderr)
        print("Server stderr:\n" + server_stderr, file=sys.stderr)
        return result.returncode or 1
    forbidden = ("SCRIPT ERROR", "Parse Error", "Failed to load script", "CLIENT_MENU_FLOW_FAILED")
    if any(marker in result.stdout for marker in forbidden):
        print("Godot reported an unexpected script error during the menu flow.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
