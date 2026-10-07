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
from llmtap.i18n import set_lang, t  # noqa: E402
from llmtap.probe import CHECKS, m_base64, m_batball, m_instruction, \
    m_math, m_needle, m_setlen  # noqa: E402
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


def test_probe_matchers() -> None:
    assert m_instruction("Apple")
    assert m_instruction('"APPLE!"')
    assert not m_instruction("The word is apple.")
    assert m_base64("decoded: banana-42")
    assert not m_base64("banana")
    assert m_needle("the code is 7391")
    assert not m_needle("739")
    assert m_batball("$0.05")
    assert m_batball("5 cents")
    assert not m_batball("$0.10")
    assert m_math("17 x 24 = 408")
    assert not m_math("1408")
    assert m_setlen("3")
    assert not m_setlen("13")


def test_probe_checks_weights_sum_100() -> None:
    assert sum(c["weight"] for c in CHECKS) == 100


def test_i18n_switch() -> None:
    set_lang("en")
    assert "downgrade" in t("probe.v.ok")
    set_lang("zh")
    assert "降智" in t("probe.v.ok")
    set_lang("en")


def test_cli_end_to_end(tmp_path) -> None:
    env = dict(os.environ, LLMTAP_CONFIG=str(ROOT / "tests" / "local.toml"),
               LLMTAP_LANG="en")
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
        out = subprocess.run(exe + ["scan", "local7b", "-c", "2"], env=env,
                             capture_output=True, text=True, cwd=str(ROOT))
        assert "2/2" in out.stdout, out.stdout + out.stderr
        out = subprocess.run(exe + ["probe", "local7b", "--timeout", "30"],
                             env=env, capture_output=True, text=True,
                             cwd=str(ROOT))
        assert "downgrade" in out.stdout.lower(), out.stdout + out.stderr

        # --- ergonomics: URL as first argument, no model needed ---
        url = "http://127.0.0.1:8765/v1"
        out = subprocess.run(exe + ["models", url], env=env,
                             capture_output=True, text=True, cwd=str(ROOT))
        assert "fake-72b" in out.stdout, out.stdout + out.stderr
        out = subprocess.run(exe + ["scan", url, "-c", "2"], env=env,
                             capture_output=True, text=True, cwd=str(ROOT))
        assert "2/2" in out.stdout, out.stdout + out.stderr
        out = subprocess.run(exe + ["test", url, "-m", "fake-7b",
                                    "--max-tokens", "8"], env=env,
                             capture_output=True, text=True, cwd=str(ROOT))
        assert "TTFT" in out.stdout, out.stdout + out.stderr
        # two models, no -m, no tty -> clear error, not a traceback
        out = subprocess.run(exe + ["test", url], env=env, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, cwd=str(ROOT))
        assert out.returncode == 2 and "fake-72b" in out.stdout
        assert "Traceback" not in out.stderr

        # --- init + add + default profile ---
        cfg = tmp_path / "c.toml"
        env2 = dict(env, LLMTAP_CONFIG=str(cfg))
        out = subprocess.run(exe + ["init", "--path", str(cfg)], env=env2,
                             capture_output=True, text=True, cwd=str(ROOT))
        assert cfg.exists(), out.stdout + out.stderr
        out = subprocess.run(exe + ["add", "demo", "-u", url, "-m", "fake-72b"],
                             env=env2, capture_output=True, text=True,
                             cwd=str(ROOT))
        assert "demo" in out.stdout, out.stdout + out.stderr
        # duplicate name is refused
        out = subprocess.run(exe + ["add", "demo", "-u", url, "-m", "x"],
                             env=env2, capture_output=True, text=True,
                             cwd=str(ROOT))
        assert out.returncode == 1
        text = cfg.read_text().replace('# profile = "ollama"',
                                       'profile = "demo"')
        cfg.write_text(text)
        out = subprocess.run(exe + ["list"], env=env2, capture_output=True,
                             text=True, cwd=str(ROOT))
        assert "demo *" in out.stdout, out.stdout + out.stderr
        # default profile is picked when PROFILE is omitted
        out = subprocess.run(exe + ["show"], env=env2, stdin=subprocess.DEVNULL,
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
            # ? opens the key guide, escape closes it
            await pilot.press("?")
            await pilot.pause(0.2)
            from llmtap.tui import HelpScreen
            assert isinstance(app.screen, HelpScreen), type(app.screen)
            await pilot.press("escape")
            await pilot.pause(0.2)
            # r runs a single test against the fake server
            await pilot.press("r")
            await pilot.pause(2.5)
            assert not app.busy
            await pilot.press("q")

    asyncio.run(run())


def test_cli_help_is_bilingual() -> None:
    """--help follows LLMTAP_LANG, in the group and the subcommands."""
    exe = [sys.executable, "-m", "llmtap.cli"]
    cases = {
        "--help": ("Terminal tester", "终端大模型 API 测试器"),
        "bench": ("Run n requests", "请求次数"),
        "probe": ("Downgrade probe", "降智检测"),
    }
    for cmd, (en_needle, zh_needle) in cases.items():
        args = ["--help"] if cmd == "--help" else [cmd, "--help"]
        env = dict(os.environ, LLMTAP_LANG="en")
        out = subprocess.run(exe + args, env=env, capture_output=True,
                             text=True, cwd=str(ROOT))
        assert en_needle in out.stdout, (cmd, out.stdout)
        env = dict(os.environ, LLMTAP_LANG="zh")
        out = subprocess.run(exe + args, env=env, capture_output=True,
                             text=True, cwd=str(ROOT))
        assert zh_needle in out.stdout, (cmd, out.stdout)
