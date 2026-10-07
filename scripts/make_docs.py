#!/usr/bin/env python3
"""Generate the README screenshots against the local fake server.

Start the fake server first:
    python scripts/fake_server.py &
Then run:
    python scripts/make_docs.py
Writes SVG and PNG files into docs/img/.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("LLMTAP_CONFIG", str(ROOT / "tests" / "local.toml"))
os.environ["LLMTAP_LANG"] = "en"  # screenshots in English
sys.path.insert(0, str(ROOT))

from rich import box  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402

from llmtap.client import bench_run, run_chat  # noqa: E402
from llmtap.config import load_targets  # noqa: E402
from llmtap.probe import probe_tables, run_probe  # noqa: E402
from llmtap.report import (bench_tables, response_preview,  # noqa: E402
                           single_result_table, targets_table)
from llmtap.scan import scan_endpoint, scan_tables  # noqa: E402
from llmtap.stats import aggregate, apply_cost  # noqa: E402
from llmtap.theme import ACCENT, DIM  # noqa: E402

IMG = ROOT / "docs" / "img"
WIDTH = 118


def new_console() -> Console:
    return Console(record=True, width=WIDTH, force_terminal=True,
                   color_system="truecolor", highlight=False)


def save(con: Console, name: str, title: str) -> None:
    svg = IMG / f"{name}.svg"
    svg.write_text(con.export_svg(title=title), encoding="utf-8")
    print(f"wrote {svg.relative_to(ROOT)}")
    if shutil.which("rsvg-convert"):
        png = IMG / f"{name}.png"
        subprocess.run(["rsvg-convert", "--zoom", "2", "-o", str(png),
                        str(svg)], check=True)
        print(f"wrote {png.relative_to(ROOT)}")


def banner(con: Console, text: str) -> None:
    """Small prompt-like header, so each image reads like a real session."""
    con.print(Panel.fit(f"[{ACCENT}]$ {text}[/]", box=box.ROUNDED,
                        border_style=DIM, padding=(0, 1)))


async def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    targets = load_targets()
    t0 = targets[0]

    con = new_console()
    banner(con, "llmtap list")
    con.print(targets_table(targets))
    save(con, "list", "llmtap list")

    con = new_console()
    banner(con, "llmtap test local7b")
    r = await run_chat(t0)
    apply_cost([r], t0)
    con.print(single_result_table(r, t0))
    con.print(response_preview(r, width=90))
    save(con, "test", "llmtap test")

    con = new_console()
    banner(con, "llmtap bench local7b -n 4 -c 2")
    results, wall = await bench_run(t0, n=4, concurrency=2)
    apply_cost(results, t0)
    con.print(bench_tables(aggregate(results, wall), t0, 4, 2, True))
    save(con, "bench", "llmtap bench")

    con = new_console()
    banner(con, "llmtap probe local7b")
    report = await run_probe(t0)
    con.print(probe_tables(report, t0))
    save(con, "probe", "llmtap probe")

    con = new_console()
    banner(con, "llmtap scan local7b")
    scan = await scan_endpoint(t0)
    con.print(scan_tables(scan, t0))
    save(con, "scan", "llmtap scan")

    from llmtap.tui import LlmtapApp
    app = LlmtapApp(config_path=str(ROOT / "tests" / "local.toml"))
    async with app.run_test(size=(190, 48)) as pilot:
        await pilot.pause(0.4)
        await pilot.press("r")
        await pilot.pause(2.4)
        (IMG / "tui.svg").write_text(app.export_screenshot(),
                                     encoding="utf-8")
        print("wrote docs/img/tui.svg")
    if shutil.which("rsvg-convert"):
        subprocess.run(["rsvg-convert", "--zoom", "2", "-o",
                        str(IMG / "tui.png"), str(IMG / "tui.svg")], check=True)
        print("wrote docs/img/tui.png")


if __name__ == "__main__":
    asyncio.run(main())
