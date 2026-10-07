#!/usr/bin/env python3
"""Generate README screenshots (SVG) against the local fake server.

Start the fake server first: python scripts/fake_server.py
Then run: python scripts/make_docs.py
Writes SVG files into docs/img/.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("LLMTAP_CONFIG", str(ROOT / "tests" / "local.toml"))
os.environ["LLMTAP_LANG"] = "en"  # screenshots in English
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402

from llmtap.client import bench_run, run_chat  # noqa: E402
from llmtap.config import load_targets  # noqa: E402
from llmtap.probe import probe_tables, run_probe  # noqa: E402
from llmtap.report import (bench_tables, response_preview,  # noqa: E402
                           single_result_table, targets_table)
from llmtap.scan import scan_endpoint, scan_tables  # noqa: E402
from llmtap.stats import aggregate, apply_cost  # noqa: E402

IMG = ROOT / "docs" / "img"


def new_console() -> Console:
    return Console(record=True, width=100, force_terminal=True,
                   color_system="truecolor")


def save(con: Console, name: str, title: str) -> None:
    IMG.joinpath(name).write_text(con.export_svg(title=title),
                                  encoding="utf-8")
    print(f"wrote {IMG / name}")


async def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    targets = load_targets()
    t0 = targets[0]

    con = new_console()
    con.print(targets_table(targets))
    save(con, "list.svg", "llmtap list")

    con = new_console()
    r = await run_chat(t0)
    apply_cost([r], t0)
    con.print(single_result_table(r, t0))
    con.print(response_preview(r))
    save(con, "test.svg", "llmtap test")

    con = new_console()
    results, wall = await bench_run(t0, n=4, concurrency=2)
    apply_cost(results, t0)
    con.print(bench_tables(aggregate(results, wall), t0, 4, 2, True))
    save(con, "bench.svg", "llmtap bench")

    con = new_console()
    report = await run_probe(t0)
    con.print(probe_tables(report, t0))
    save(con, "probe.svg", "llmtap probe")

    con = new_console()
    scan = await scan_endpoint(t0)
    con.print(scan_tables(scan, t0))
    save(con, "scan.svg", "llmtap scan")

    from llmtap.tui import LlmtapApp
    app = LlmtapApp(config_path=str(ROOT / "tests" / "local.toml"))
    async with app.run_test(size=(170, 46)) as pilot:
        await pilot.pause(0.4)
        await pilot.press("r")
        await pilot.pause(2.2)
        IMG.joinpath("tui.svg").write_text(app.export_screenshot(),
                                           encoding="utf-8")
        print(f"wrote {IMG / 'tui.svg'}")


if __name__ == "__main__":
    asyncio.run(main())
