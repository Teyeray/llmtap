"""Rich renderables for CLI and TUI output."""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text

from .client import RequestResult
from .config import ModelTarget
from .stats import Agg

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
    t = Table(title="Configured models", box=None, header_style="bold cyan")
    for col in ("profile", "model", "base_url", "api key", "temp",
                "max_tok", "timeout", "$in/1M", "$out/1M"):
        t.add_column(col)
    for tg in targets:
        t.add_row(
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
    return t


def target_detail(target: ModelTarget) -> Panel:
    """Full config of one target, API key value removed."""
    body = Pretty(target.safe_dict())
    return Panel(body, title=f"Config: {target.profile}",
                 subtitle=f"source: {target.source or NA}", border_style="cyan")


def single_result_table(r: RequestResult, target: ModelTarget) -> Table:
    t = Table(title=f"{target.profile} — single request",
              box=None, header_style="bold cyan")
    t.add_column("metric")
    t.add_column("value", justify="right")
    t.add_column("note")

    def add(metric, value, note=""):
        t.add_row(metric, value, note)

    add("status", str(r.status), "ok" if r.ok else "failed")
    add("model (reported)", r.model_reported or NA, target.model)
    add("time to headers", _ms(r.headers_ms), "ms")
    add("time to first chunk", _ms(r.first_chunk_ms), "ms")
    add("TTFT", _ms(r.ttft_ms), "first token, ms"
        + ("" if r.stream else " (non-stream: n/a)"))
    add("total time", _ms(r.total_ms), "ms")
    if r.itl_ms:
        from .stats import percentile
        add("ITL avg", _ms(sum(r.itl_ms) / len(r.itl_ms)),
            f"p50 {_ms(percentile(r.itl_ms, 50))} / "
            f"p95 {_ms(percentile(r.itl_ms, 95))} ms")
    add("input tokens", str(r.input_tokens or NA),
        "estimated" if r.usage_estimated else "from usage")
    add("output tokens", str(r.output_tokens or NA),
        "estimated" if r.usage_estimated else "from usage")
    tps_d = r.tps_decode if r.stream else None
    add("decode speed", _f(tps_d, 1), "tok/s after first token")
    add("overall speed", _f(r.tps_overall, 1), "tok/s over full request")
    add("finish reason", r.finish_reason or NA)
    if r.reasoning_chars:
        add("reasoning chars", str(r.reasoning_chars))
    add("cost", _f(r.cost_usd * 1000, 4) + " m$" if r.cost_usd is not None
        else NA, "USD x1000")
    return t


def response_preview(r: RequestResult, width: int = 76,
                     limit: int = 500) -> Panel:
    if r.error and not r.ok:
        body = Text(r.error, style="bold red")
    else:
        text = r.text if r.text else f"({r.reasoning_chars} reasoning chars)"
        text = text if len(text) <= limit else text[:limit] + " …"
        body = Text(text)
    title = "response" if r.ok else "error"
    return Panel(body, title=title, border_style="green" if r.ok else "red",
                 width=min(width, 90))


def bench_tables(agg: Agg, target: ModelTarget, n: int, concurrency: int,
                 stream: bool) -> Group:
    """Benchmark result: per-metric stats plus a run summary."""
    t = Table(title=f"{target.profile} — {n} requests "
                    f"(concurrency {concurrency}, "
                    f"{'stream' if stream else 'non-stream'})",
              box=None, header_style="bold cyan")
    for col in ("metric", "mean", "p50", "p95", "min", "max"):
        t.add_column(col, justify="right" if col != "metric" else "left")
    t.add_row("TTFT (ms)", *_row(agg.ttft_ms))
    t.add_row("total (ms)", *_row(agg.total_ms))
    t.add_row("ITL (ms)", *_row(agg.itl_ms))
    t.add_row("decode speed (tok/s)", *_row(agg.tps, nd=1))
    t.add_row("output tokens", *_row(agg.out_tokens, nd=0))

    s = Table(box=None, show_header=False)
    s.add_column()
    s.add_column(justify="right")
    s.add_row("ok / total", f"{agg.ok}/{agg.n}")
    s.add_row("error rate", f"{agg.error_rate * 100:.1f}%")
    s.add_row("wall time", f"{agg.wall_s:.1f} s")
    s.add_row("throughput", f"{agg.req_per_s:.2f} req/s")
    s.add_row("tokens in/out", f"{agg.in_tokens_total}/{agg.out_tokens_total}")
    if agg.cost_total is not None:
        s.add_row("total cost", f"${agg.cost_total:.4f}")
    parts: list = [t, s]
    if agg.errors:
        err_list = "\n".join(dict.fromkeys(agg.errors))
        parts.append(Panel(Text(err_list, style="red"), title="errors"))
    return Group(*parts)


def compare_table(rows: list[tuple[str, Agg]]) -> Table:
    """One row per profile for `bench --all` runs."""
    t = Table(title="Comparison", box=None, header_style="bold cyan")
    for col in ("profile", "ok", "err%", "TTFT p50", "total p50",
                "tok/s p50", "cost"):
        t.add_column(col, justify="right" if col != "profile" else "left")
    for name, a in rows:
        t.add_row(
            name,
            f"{a.ok}/{a.n}",
            f"{a.error_rate * 100:.0f}",
            _ms(a.ttft_ms["p50"]) if a.ttft_ms else NA,
            _ms(a.total_ms["p50"]) if a.total_ms else NA,
            _f(a.tps["p50"], 1) if a.tps else NA,
            _f(a.cost_total, 4) if a.cost_total is not None else NA,
        )
    return t


def models_table(ids: list[str]) -> Table:
    t = Table(title="GET /models", box=None, header_style="bold cyan")
    t.add_column("model id")
    for i in ids:
        t.add_row(i)
    return t
