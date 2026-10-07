"""Rich renderables for CLI and TUI output. All text goes through i18n."""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text

from .client import RequestResult
from .config import ModelTarget
from .i18n import t
from .stats import Agg, percentile

NA = "-"


def _ms(v: float | None) -> str:
    return f"{v:,.0f}" if v is not None else NA


def _f(v: float | None, nd: int = 1) -> str:
    return f"{v:.{nd}f}" if v is not None else NA


def _row(s: dict | None, nd: int = 0) -> list[str]:
    if s is None:
        return [NA] * 5
    fmt = (lambda v: _ms(v)) if nd == 0 else (lambda v: _f(v, nd))
    return [fmt(s["mean"]), fmt(s["p50"]), fmt(s["p95"]),
            fmt(s["min"]), fmt(s["max"])]


def targets_table(targets: list[ModelTarget]) -> Table:
    """Every model with every key setting, one row per target."""
    table = Table(title=t("report.configured_models"), box=None,
                  header_style="bold cyan")
    for key in ("col.profile", "col.model", "col.base_url", "col.api_key",
                "col.temp", "col.max_tok", "col.timeout", "col.price_in",
                "col.price_out"):
        table.add_column(t(key))
    for tg in targets:
        table.add_row(
            tg.profile,
            tg.model,
            tg.base_url,
            tg.key_display,
            NA if tg.temperature is None else _f(tg.temperature),
            NA if tg.max_tokens is None else str(tg.max_tokens),
            _f(tg.timeout_s, 0),
            _f(tg.price_in, 2) if tg.price_in is not None else NA,
            _f(tg.price_out, 2) if tg.price_out is not None else NA,
        )
    return table


def target_detail(target: ModelTarget) -> Panel:
    """Full config of one target, API key value removed."""
    body = Pretty(target.safe_dict())
    return Panel(body, title=t("report.config_of", profile=target.profile),
                 subtitle=t("report.source", src=target.source or NA),
                 border_style="cyan")


def single_result_table(r: RequestResult, target: ModelTarget) -> Table:
    table = Table(title=t("report.single_title", profile=target.profile),
                  box=None, header_style="bold cyan")
    table.add_column(t("report.metric"))
    table.add_column(t("col.value"), justify="right")
    table.add_column(t("col.note"))

    def add(metric, value, note=""):
        table.add_row(metric, value, note)

    add(t("m.status"), str(r.status),
        t("n.ok") if r.ok else t("n.failed"))
    add(t("m.model_reported"), r.model_reported or NA, target.model)
    add(t("m.headers"), _ms(r.headers_ms), "ms")
    add(t("m.first_chunk"), _ms(r.first_chunk_ms), "ms")
    ttft_note = t("n.first_token_ms") if r.stream else t("n.nonstream_na")
    add(t("m.ttft"), _ms(r.ttft_ms), ttft_note)
    add(t("m.total"), _ms(r.total_ms), "ms")
    if r.itl_ms:
        add(t("m.itl_avg"), _ms(sum(r.itl_ms) / len(r.itl_ms)),
            f"p50 {_ms(percentile(r.itl_ms, 50))} / "
            f"p95 {_ms(percentile(r.itl_ms, 95))} ms")
    add(t("m.input_tokens"), str(r.input_tokens or NA),
        t("n.estimated") if r.usage_estimated else t("n.from_usage"))
    add(t("m.output_tokens"), str(r.output_tokens or NA),
        t("n.estimated") if r.usage_estimated else t("n.from_usage"))
    tps_d = r.tps_decode if r.stream else None
    add(t("m.decode"), _f(tps_d, 1), t("n.decode"))
    add(t("m.overall"), _f(r.tps_overall, 1), t("n.overall"))
    add(t("m.finish"), r.finish_reason or NA)
    if r.reasoning_chars:
        add(t("m.reasoning"), str(r.reasoning_chars))
    cost = _f(r.cost_usd * 1000, 4) + " m$" if r.cost_usd is not None else NA
    add(t("m.cost"), cost, "USD x1000")
    return table


def response_preview(r: RequestResult, width: int = 76,
                     limit: int = 500) -> Panel:
    if r.error and not r.ok:
        body = Text(r.error, style="bold red")
    else:
        text = r.text if r.text else f"({r.reasoning_chars} reasoning chars)"
        text = text if len(text) <= limit else text[:limit] + " …"
        body = Text(text)
    title = t("report.response") if r.ok else t("report.error")
    return Panel(body, title=title,
                 border_style="green" if r.ok else "red",
                 width=min(width, 90))


def bench_tables(agg: Agg, target: ModelTarget, n: int, concurrency: int,
                 stream: bool) -> Group:
    """Benchmark result: per-metric stats plus a run summary."""
    mode = t("report.mode_stream" if stream else "report.mode_nonstream")
    table = Table(title=t("report.bench_title", profile=target.profile, n=n,
                          c=concurrency, mode=mode),
                  box=None, header_style="bold cyan")
    table.add_column(t("report.metric"))
    for col in ("mean", "p50", "p95", "min", "max"):
        table.add_column(col, justify="right")
    table.add_row(t("b.ttft"), *_row(agg.ttft_ms))
    table.add_row(t("b.total"), *_row(agg.total_ms))
    table.add_row(t("b.itl"), *_row(agg.itl_ms))
    table.add_row(t("b.decode"), *_row(agg.tps, nd=1))
    table.add_row(t("b.out_tokens"), *_row(agg.out_tokens, nd=0))

    s = Table(box=None, show_header=False)
    s.add_column()
    s.add_column(justify="right")
    s.add_row(t("b.ok_total"), f"{agg.ok}/{agg.n}")
    s.add_row(t("b.error_rate"), f"{agg.error_rate * 100:.1f}%")
    s.add_row(t("b.wall"), f"{agg.wall_s:.1f} s")
    s.add_row(t("b.throughput"), f"{agg.req_per_s:.2f} req/s")
    s.add_row(t("b.tokens"), f"{agg.in_tokens_total}/{agg.out_tokens_total}")
    if agg.cost_total is not None:
        s.add_row(t("b.cost"), f"${agg.cost_total:.4f}")
    parts: list = [table, s]
    if agg.errors:
        err_list = "\n".join(dict.fromkeys(agg.errors))
        parts.append(Panel(Text(err_list, style="red"),
                           title=t("report.errors")))
    return Group(*parts)


def compare_table(rows: list[tuple[str, Agg]]) -> Table:
    """One row per profile for `bench --all` runs."""
    table = Table(title=t("report.comparison"), box=None,
                  header_style="bold cyan")
    for key in ("col.profile", "col.ok", "col.err_pct", "col.ttft_p50",
                "col.total_p50", "col.tps_p50", "col.cost"):
        table.add_column(t(key),
                         justify="left" if key == "col.profile" else "right")
    for name, a in rows:
        table.add_row(
            name,
            f"{a.ok}/{a.n}",
            f"{a.error_rate * 100:.0f}",
            _ms(a.ttft_ms["p50"]) if a.ttft_ms else NA,
            _ms(a.total_ms["p50"]) if a.total_ms else NA,
            _f(a.tps["p50"], 1) if a.tps else NA,
            _f(a.cost_total, 4) if a.cost_total is not None else NA,
        )
    return table


def models_table(ids: list[str]) -> Table:
    table = Table(title=t("report.get_models"), box=None,
                  header_style="bold cyan")
    table.add_column(t("col.model_id"))
    for i in ids:
        table.add_row(i)
    return table
