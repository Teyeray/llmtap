"""Offline smoke test: CLI against the fake server, TUI headless."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from llmtap.config import load_targets  # noqa: E402
from llmtap.stats import percentile  # noqa: E402


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def test_percentile() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert percentile([], 50) is None


def test_config_expand(tmp_path: Path) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text("""
[profiles.p]
base_url = "http://x/v1"
models = ["a", "b"]
[profiles.q]
base_url = "http://y/v1"
model = "c"
""")
    targets = load_targets(str(cfg))
    names = [t.profile for t in targets]
    assert names == ["p/a", "p/b", "q"]


def test_cli_end_to_end() -> None:
    env = dict(os.environ, LLMTAP_CONFIG=str(ROOT / "tests" / "local.toml"))
    if not _port_open(8765):
        server = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "fake_server.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.8)
    else:
        server = None
    try:
        exe = [sys.executable, "-m", "llmtap.cli"]
        out = subprocess.run(exe + ["list"], env=env, capture_output=True,
                             text=True, cwd=str(ROOT))
        assert "local7b" in out.stdout, out.stdout + out.stderr
        out = subprocess.run(exe + ["test", "local7b"], env=env,
                             capture_output=True, text=True, cwd=str(ROOT))
        assert "TTFT" in out.stdout, out.stdout + out.stderr
        out = subprocess.run(exe + ["bench", "local7b", "--n", "3", "-c", "2"],
                             env=env, capture_output=True, text=True,
                             cwd=str(ROOT))
        assert "p95" in out.stdout, out.stdout + out.stderr
        out = subprocess.run(exe + ["models", "local7b"], env=env,
                             capture_output=True, text=True, cwd=str(ROOT))
        assert "fake-72b" in out.stdout, out.stdout + out.stderr
    finally:
        if server:
            server.terminate()


def test_tui_headless() -> None:
    from llmtap.tui import LlmtapApp

    async def run() -> None:
        app = LlmtapApp(config_path=str(ROOT / "tests" / "local.toml"))
        async with app.run_test() as pilot:
            await pilot.pause(0.3)
            assert app.targets, "targets not loaded in TUI"
            await pilot.press("q")

    asyncio.run(run())
