"""Relay endpoint scan: test every model that GET /models lists."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .client import chat_with_fallback, list_models
from .config import ModelTarget
from .i18n import t
from .theme import BAD, HEADER, OK, WARN, table_box
from .stats import percentile

SCAN_PROMPT = "Reply with exactly: OK"


@dataclass
class ScanRow:
    model: str
    ok: bool = False
    status: int | None = None
    ttft_ms: float | None = None
    total_ms: float | None = None
    tokens: int | None = None
    tps: float | None = None
    error: str = ""


@dataclass
class ScanReport:
    rows: list[ScanRow] = field(default_factory=list)
    listed: int = 0
    fetch_status: int | None = None
    fetch_error: str = ""

    @property
    def alive(self) -> list[ScanRow]:
        return [r for r in self.rows if r.ok]


async def scan_endpoint(
    target: ModelTarget,
    *,
    only: str | None = None,
    limit: int | None = None,
    concurrency: int = 4,
    timeout: float = 20.0,
    max_tokens: int = 16,
    on_progress=None,
) -> ScanReport:
    """List the endpoint models, then test each one with one small request."""
    report = ScanReport()
    status, ids, err = await list_models(target, timeout=timeout)
    report.fetch_status = status
    if err:
        report.fetch_error = err
        return report
    report.listed = len(ids)
    if only:
        ids = [i for i in ids if only.lower() in i.lower()]
    if limit:
        ids = ids[:limit]

    sem = asyncio.Semaphore(max(1, concurrency))
    to = httpx.Timeout(timeout, connect=10.0)
    async with httpx.AsyncClient(
            timeout=to, trust_env=_trust_env_flag(target.base_url)) as client:
        async def one(model_id: str) -> ScanRow:
            async with sem:
                r = await chat_with_fallback(
                    target, prompt=SCAN_PROMPT, stream=True,
                    max_tokens=max_tokens, temperature=0.0,
                    timeout=timeout, client=client)
                row = ScanRow(
                    model=model_id, ok=r.ok, status=r.status,
                    ttft_ms=r.ttft_ms, total_ms=r.total_ms,
                    tokens=r.output_tokens,
                    tps=r.tps_decode or r.tps_overall,
                    error=r.error)
                if on_progress:
                    on_progress(row)
                return row
        report.rows = list(await asyncio.gather(*(one(i) for i in ids)))
    return report


def _trust_env_flag(url: str) -> bool:
    from .client import _trust_env
    return _trust_env(url)


def scan_tables(report: ScanReport, target: ModelTarget) -> Group:
    if report.fetch_error:
        return Group(Panel(Text(t("scan.fetch_failed",
                                  status=report.fetch_status,
                                  error=report.fetch_error),
                                style=BAD),
                           title=t("scan.title_short", host=target.host)))

    table = Table(title=t("scan.title", host=target.host,
                          n=len(report.rows), m=report.listed),
                  box=table_box(), header_style=HEADER)
    for key in ("col.model", "col.status", "col.ttft", "col.tps",
                "col.out_tok", "col.error"):
        table.add_column(t(key))
    for r in report.rows:
        mark = (f"[green]{t('scan.ok')}[/green]" if r.ok
                else f"[red]{t('scan.fail')}[/red]")
        table.add_row(
            r.model, mark,
            f"{r.ttft_ms:.0f} ms" if r.ttft_ms is not None else "-",
            f"{r.tps:.1f}" if r.tps is not None else "-",
            str(r.tokens) if r.tokens is not None else "-",
            " ".join(r.error.split())[:60] if r.error else "")
    return Group(table, _scan_summary(report))


def _scan_summary(report: ScanReport) -> Panel:
    alive = report.alive
    ttfts = [r.ttft_ms for r in alive if r.ttft_ms is not None]
    lines = [t("scan.alive", ok=len(alive), n=len(report.rows))]
    if ttfts:
        lines.append(t("scan.ttft_summary",
                       p50=f"{percentile(ttfts, 50):,.0f}",
                       p95=f"{percentile(ttfts, 95):,.0f}"))
    dead = [r.model for r in report.rows if not r.ok]
    if dead:
        lines.append(t("scan.dead", models=", ".join(dead)))
    style = OK if len(alive) == len(report.rows) and alive else \
        WARN if alive else BAD
    return Panel(Text("\n".join(lines)), border_style=style)
