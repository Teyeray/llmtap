"""llmtap command line interface."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console

from . import __version__
from .client import bench_run, chat_with_fallback, list_models, run_chat
from .config import (ConfigError, ModelTarget, adhoc_target, load_targets,
                     pick_target)
from .i18n import t
from .probe import run_probe
from .report import (bench_tables, compare_table, models_table,
                     response_preview, single_result_table, target_detail,
                     targets_table)
from .scan import scan_endpoint
from .stats import Agg, aggregate, apply_cost

app = typer.Typer(
    help="Terminal tester for LLM API endpoints. OpenAI-compatible.",
    no_args_is_help=True, add_completion=False,
    pretty_exceptions_enable=False,
)
console = Console()

CFG = typer.Option(None, "--config", help="Config file path "
                 "(default: ./llmtap.toml or ~/.config/llmtap/config.toml)")
PROFILE = typer.Argument(None, help="Profile name from the config file")
BASE_URL = typer.Option(None, "--base-url",
                        help="Ad-hoc base URL, e.g. http://127.0.0.1:11434/v1")
MODEL = typer.Option(None, "--model", help="Ad-hoc model id")
KEY_ENV = typer.Option(None, "--api-key-env",
                       help="Env var that holds the API key")
PROMPT = typer.Option(None, "--prompt", "-p", help="Override the prompt")
MAX_TOK = typer.Option(None, "--max-tokens", help="Override max output tokens")
TEMP = typer.Option(None, "--temperature", help="Override temperature")
STREAM = typer.Option(True, "--stream/--no-stream",
                      help="Use SSE streaming (default: stream)")


def _load(config: Optional[str]) -> list[ModelTarget]:
    try:
        return load_targets(config)
    except ConfigError as e:
        console.print(f"[red]{t('cli.config_error', msg=e)}[/red]")
        raise typer.Exit(1) from None


def _pick(profile: Optional[str], base_url: Optional[str],
          model: Optional[str], key_env: Optional[str],
          config: Optional[str], prompt: Optional[str]) -> ModelTarget:
    if base_url or model:
        if not (base_url and model):
            console.print(f"[red]{t('cli.flags_together')}[/red]")
            raise typer.Exit(1)
        return adhoc_target(base_url, model, key_env or "", prompt)
    if not profile:
        console.print(t("cli.need_profile"))
        raise typer.Exit(1)
    try:
        return pick_target(_load(config), profile)
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


def _fail_fast(result) -> None:
    if not result.ok:
        console.print(response_preview(result))
        raise typer.Exit(1)


@app.command()
def list(config: Optional[str] = CFG) -> None:
    """Show every configured model with every setting."""
    targets = _load(config)
    console.print(targets_table(targets))
    src = targets[0].source if targets else ""
    console.print(f"[dim]{t('cli.n_targets', n=len(targets), src=src)}[/dim]")


@app.command()
def show(profile: str, config: Optional[str] = CFG) -> None:
    """Show the full config of one profile."""
    try:
        target = pick_target(_load(config), profile)
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    console.print(target_detail(target))


@app.command()
def models(profile: Optional[str] = PROFILE, config: Optional[str] = CFG,
           base_url: Optional[str] = BASE_URL, model: Optional[str] = MODEL,
           key_env: Optional[str] = KEY_ENV) -> None:
    """Call GET /models on one endpoint and list the model ids."""
    target = _pick(profile, base_url, model, key_env, config, None)
    status, ids, err = asyncio.run(list_models(target))
    if err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(1)
    console.print(models_table(ids))
    console.print(f"[dim]{t('cli.n_models', n=len(ids), url=target.base_url,
                            status=status)}[/dim]")


@app.command()
def test(profile: Optional[str] = PROFILE, config: Optional[str] = CFG,
         base_url: Optional[str] = BASE_URL, model: Optional[str] = MODEL,
         key_env: Optional[str] = KEY_ENV, prompt: Optional[str] = PROMPT,
         max_tokens: Optional[int] = MAX_TOK,
         temperature: Optional[float] = TEMP,
         stream: bool = STREAM,
         full: bool = typer.Option(False, "--full", help="Print all text")) -> None:
    """Run one request and print all metrics plus a response preview."""
    target = _pick(profile, base_url, model, key_env, config, prompt)
    result = asyncio.run(run_chat(
        target, prompt=prompt, stream=stream,
        max_tokens=max_tokens, temperature=temperature))
    apply_cost([result], target)
    console.print(single_result_table(result, target))
    console.print(response_preview(result, limit=100000 if full else 500))
    _fail_fast(result)


@app.command()
def bench(profile: Optional[str] = PROFILE, config: Optional[str] = CFG,
          base_url: Optional[str] = BASE_URL, model: Optional[str] = MODEL,
          key_env: Optional[str] = KEY_ENV, prompt: Optional[str] = PROMPT,
          max_tokens: Optional[int] = MAX_TOK,
          temperature: Optional[float] = TEMP, stream: bool = STREAM,
          n: int = typer.Option(8, "--n", min=1, help="Number of requests"),
          concurrency: int = typer.Option(1, "--concurrency", "-c", min=1,
                                          help="Parallel requests"),
          all: bool = typer.Option(False, "--all",
                                   help="Benchmark every profile")) -> None:
    """Run n requests and print aggregated statistics (mean/p50/p95/min/max)."""
    if all:
        targets = _load(config)
    else:
        targets = [_pick(profile, base_url, model, key_env, config, prompt)]
    rows: list[tuple[str, Agg]] = []
    with console.status("[bold]running…[/bold]") as status:
        for i, target in enumerate(targets):
            status.update(f"[bold]{target.profile}[/bold] "
                          f"({i + 1}/{len(targets)})")
            results, wall = asyncio.run(bench_run(
                target, n=n, concurrency=concurrency, prompt=prompt,
                stream=stream, max_tokens=max_tokens,
                temperature=temperature))
            apply_cost(results, target)
            agg = aggregate(results, wall)
            rows.append((target.profile, agg))
            console.print(bench_tables(agg, target, n, concurrency, stream))
            console.print()
    if all:
        console.print(compare_table(rows))


@app.command()
def probe(profile: Optional[str] = PROFILE, config: Optional[str] = CFG,
          base_url: Optional[str] = BASE_URL, model: Optional[str] = MODEL,
          key_env: Optional[str] = KEY_ENV,
          timeout: float = typer.Option(120.0, "--timeout",
                                        help="Per-request timeout in seconds"),
          strict: bool = typer.Option(False, "--strict",
                                      help="Exit 1 when score is below 85")) -> None:
    """Downgrade probe: 6 fixed checks, regex-scored, no judge model."""
    target = _pick(profile, base_url, model, key_env, config, None)
    with console.status(f"[bold]{t('cli.probing', name=target.profile)}…[/bold]") as status:
        def on_progress(cr) -> None:
            mark = t("probe.pass") if cr.passed else t("probe.fail")
            status.update(f"[bold]{t('cli.probing', name=target.profile)}[/bold] "
                          f"({cr.name}: {mark})")
        report = asyncio.run(run_probe(target, timeout=timeout,
                                       on_progress=on_progress))
    from .probe import probe_tables
    console.print(probe_tables(report, target))
    if report.errors or (strict and (report.score or 0) < 85):
        raise typer.Exit(1)


@app.command()
def scan(profile: Optional[str] = PROFILE, config: Optional[str] = CFG,
         base_url: Optional[str] = BASE_URL, model: Optional[str] = MODEL,
         key_env: Optional[str] = KEY_ENV,
         concurrency: int = typer.Option(4, "--concurrency", "-c",
                                         help="Parallel model tests"),
         only: Optional[str] = typer.Option(None, "--only",
                                            help="Only models containing this "
                                                 "substring"),
         limit: Optional[int] = typer.Option(None, "--limit",
                                             help="Test at most N models"),
         timeout: float = typer.Option(20.0, "--timeout",
                                       help="Per-request timeout in seconds")) -> None:
    """Scan a relay: GET /models, then test every model for TTFT and status."""
    target = _pick(profile, base_url, model, key_env, config, None)
    with console.status(f"[bold]{t('cli.scanning', host=target.host)}…[/bold]") as status:
        done = [0]

        def on_progress(row) -> None:
            done[0] += 1
            mark = t("scan.ok") if row.ok else t("scan.fail")
            status.update(f"[bold]{t('cli.scanning', host=target.host)}[/bold] "
                          f"({done[0]}: {mark} {row.model})")
        report = asyncio.run(scan_endpoint(
            target, only=only, limit=limit, concurrency=concurrency,
            timeout=timeout, on_progress=on_progress))
    from .scan import scan_tables
    console.print(scan_tables(report, target))
    if report.fetch_error or not report.alive:
        raise typer.Exit(1)


@app.command()
def tui(config: Optional[str] = CFG) -> None:
    """Open the interactive TUI."""
    from .tui import LlmtapApp
    LlmtapApp(config_path=config).run()


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"llmtap {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
