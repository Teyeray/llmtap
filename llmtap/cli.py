"""llmtap command line interface."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

from . import __version__
from .client import bench_run, list_models, run_chat
from .config import (USER_CONFIG_PATH, ConfigError, ModelTarget, adhoc_target,
                     append_profile, find_config, load_targets, pick_target,
                     write_template)
from .i18n import t
from .theme import ACCENT, BAD, DIM, OK, WARN
from .probe import probe_tables, run_probe
from .report import (bench_tables, compare_table, models_table,
                     response_preview, single_result_table, target_detail,
                     targets_table)
from .scan import scan_endpoint, scan_tables
from .stats import Agg, aggregate, apply_cost

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False,
                  no_args_is_help=False, help=t("cli.h.app"))
console = Console()

CFG = typer.Option(None, "--config", help=t("cli.h.config"))
PROFILE = typer.Argument(None, help=t("cli.h.profile"))
BASE_URL = typer.Option(None, "-u", "--base-url", help=t("cli.h.base_url"))
MODEL = typer.Option(None, "-m", "--model", help=t("cli.h.model"))
API_KEY = typer.Option(None, "-k", "--api-key", help=t("cli.h.api_key"))
KEY_ENV = typer.Option(None, "--api-key-env", help=t("cli.h.key_env"))
PROMPT = typer.Option(None, "-p", "--prompt", help=t("cli.h.prompt"))
MAX_TOK = typer.Option(None, "--max-tokens", help=t("cli.h.max_tokens"))
TEMP = typer.Option(None, "--temperature", help=t("cli.h.temperature"))
STREAM = typer.Option(True, "--stream/--no-stream",
                      help=t("cli.h.stream"))


def _is_url(s: str | None) -> bool:
    return bool(s) and s.startswith(("http://", "https://"))


def _resolve_key(api_key: str | None, key_env: str | None) -> tuple[str, str]:
    """Return (key value, env var name). The flag wins over the env var."""
    if api_key:
        return api_key, ""
    if key_env:
        return os.environ.get(key_env, ""), key_env
    for name in ("LLMTAP_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(name):
            return os.environ[name], name
    return "", ""


def _interactive() -> bool:
    """True when a human can answer a prompt.

    Windows reports NUL as a tty, so stdout is checked as well.
    """
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _choose(items: list[str], title: str) -> str:
    """Ask the user to pick one item by number."""
    if not _interactive():
        raise ConfigError(t("err.pick_needs_tty", what=title,
                            names=", ".join(items)))
    console.print(f"{title}:")
    for i, name in enumerate(items, 1):
        console.print(f"  [{ACCENT}]{i}[/]. {name}")
    try:
        choice = Prompt.ask(t("cli.pick_prompt"), default="1")
    except (EOFError, KeyboardInterrupt):
        raise ConfigError(t("err.pick_needs_tty", what=title,
                            names=", ".join(items)))
    try:
        idx = int(choice)
        if not 1 <= idx <= len(items):
            raise ValueError
    except ValueError:
        raise ConfigError(t("err.pick_invalid", choice=choice))
    return items[idx - 1]


def _config_error(exc: ConfigError) -> None:
    console.print(f"[{BAD}]{t('cli.config_error', msg=exc)}[/]")
    raise typer.Exit(2)


def _load(config: str | None) -> list[ModelTarget]:
    try:
        return load_targets(config)
    except ConfigError as exc:
        _config_error(exc)
        raise  # unreachable, keeps type checkers happy


def _default_or_choice(targets: list[ModelTarget]) -> ModelTarget:
    """Use the only target, the config default, or ask the user."""
    if len(targets) == 1:
        return targets[0]
    marked = [x for x in targets if x.default]
    if len(marked) == 1:
        return marked[0]
    try:
        name = _choose([x.profile for x in targets], t("cli.pick_profile"))
        return pick_target(targets, name)
    except ConfigError as exc:
        _config_error(exc)


def _pick(profile: str | None = None, base_url: str | None = None,
          model: str | None = None, api_key: str | None = None,
          key_env: str | None = None, config: str | None = None,
          prompt: str | None = None, max_tokens: int | None = None,
          temperature: float | None = None,
          need_model: bool = True) -> ModelTarget:
    """Resolve the command line input into one ModelTarget.

    Accepts a profile name, a bare URL as the first argument, or the
    --base-url flags. In ad-hoc mode a missing model is read from
    GET /models and chosen interactively.
    """
    if _is_url(profile):
        base_url, profile = profile, None

    if base_url:
        key, env = _resolve_key(api_key, key_env)
        if not model and need_model:
            probe_target = adhoc_target(base_url, "", env, prompt, key)
            _, ids, err = asyncio.run(list_models(probe_target))
            if err or not ids:
                _config_error(ConfigError(t("err.no_models", url=base_url)))
            try:
                model = ids[0] if len(ids) == 1 else _choose(
                    ids, t("cli.pick_model"))
            except ConfigError as exc:
                _config_error(exc)
        target = adhoc_target(base_url, model or "", env, prompt, key)
        target.profile = f"adhoc:{target.host}"
        if max_tokens is not None:
            target.max_tokens = max_tokens
        if temperature is not None:
            target.temperature = temperature
        return target

    if api_key or key_env:
        _config_error(ConfigError(t("err.flags_need_url")))

    targets = _load(config)
    if profile:
        try:
            target = pick_target(targets, profile)
        except ConfigError as exc:
            _config_error(exc)
    else:
        target = _default_or_choice(targets)
    if prompt:
        target.prompt = prompt
    if max_tokens is not None:
        target.max_tokens = max_tokens
    if temperature is not None:
        target.temperature = temperature
    return target


def _error_hint(result) -> None:
    if result.status in (401, 403) and not result.ok:
        console.print(f"[{WARN}]{t('cli.hint_key')}[/]")


# ---- commands -------------------------------------------------------------

@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Entry point. The group help text lives in cli.h.app."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        found = find_config()
    except ConfigError:
        found = None
    if found:
        from .tui import LlmtapApp
        LlmtapApp(config_path=str(found)).run()
        return
    console.print(ctx.get_help())
    console.print(f"\n[{WARN}]{t('cli.no_config_hint')}[/]")


@app.command("list", help=t("cli.h.list"))
def list_cmd(config: Optional[str] = CFG) -> None:
    """Show every configured model with every setting."""
    targets = _load(config)
    console.print(targets_table(targets))
    note = t("cli.n_targets", n=len(targets), src=targets[0].source)
    if any(x.default for x in targets):
        note += f"  ·  {t('cli.default_note')}"
    console.print(f"[{DIM}]{note}[/]")


@app.command(help=t("cli.h.show"))
def show(profile: Optional[str] = PROFILE,
         base_url: Optional[str] = BASE_URL,
         model: Optional[str] = MODEL,
         api_key: Optional[str] = API_KEY,
         api_key_env: Optional[str] = KEY_ENV,
         config: Optional[str] = CFG) -> None:
    """Show the full config of one profile."""
    target = _pick(profile, base_url, model, api_key, api_key_env, config)
    console.print(target_detail(target))
    if target.source == "adhoc":
        console.print(f"[{DIM}]{t('cli.adhoc_no_config')}[/]")


@app.command(help=t("cli.h.models"))
def models(profile: Optional[str] = PROFILE,
           base_url: Optional[str] = BASE_URL,
           api_key: Optional[str] = API_KEY,
           api_key_env: Optional[str] = KEY_ENV,
           config: Optional[str] = CFG) -> None:
    """Call GET /models on one endpoint and list the model ids."""
    target = _pick(profile, base_url, None, api_key, api_key_env, config,
                   need_model=False)
    status, ids, err = asyncio.run(list_models(target))
    if err:
        console.print(f"[{BAD}]{t('cli.request_failed')}[/] {err}")
        _error_hint(type("R", (), {"status": status, "ok": False})())
        raise typer.Exit(1)
    console.print(models_table(ids))
    console.print(f"[{DIM}]{t('cli.n_models', n=len(ids), url=target.base_url, status=status)}[/]")


@app.command(help=t("cli.h.test"))
def test(profile: Optional[str] = PROFILE,
         base_url: Optional[str] = BASE_URL,
         model: Optional[str] = MODEL,
         api_key: Optional[str] = API_KEY,
         api_key_env: Optional[str] = KEY_ENV,
         prompt: Optional[str] = PROMPT,
         max_tokens: Optional[int] = MAX_TOK,
         temperature: Optional[float] = TEMP,
         stream: bool = STREAM,
         full: bool = typer.Option(False, "--full", help=t("cli.h.full")),
         config: Optional[str] = CFG) -> None:
    """Run one request and print all metrics plus a response preview."""
    target = _pick(profile, base_url, model, api_key, api_key_env, config,
                   prompt, max_tokens, temperature)
    with console.status(t("cli.running", name=target.profile)):
        result = asyncio.run(run_chat(target, stream=stream))
    apply_cost([result], target)
    console.print(single_result_table(result, target))
    console.print(response_preview(result,
                                   limit=100000 if full else 500))
    if not result.ok:
        _error_hint(result)
        raise typer.Exit(1)


@app.command(help=t("cli.h.bench"))
def bench(profile: Optional[str] = PROFILE,
          base_url: Optional[str] = BASE_URL,
          model: Optional[str] = MODEL,
          api_key: Optional[str] = API_KEY,
          api_key_env: Optional[str] = KEY_ENV,
          prompt: Optional[str] = PROMPT,
          max_tokens: Optional[int] = MAX_TOK,
          temperature: Optional[float] = TEMP,
          stream: bool = STREAM,
          n: int = typer.Option(8, "-n", "--n", min=1,
                                help=t("cli.h.n")),
          concurrency: int = typer.Option(1, "-c", "--concurrency", min=1,
                                          help=t("cli.h.concurrency")),
          all_profiles: bool = typer.Option(False, "--all",
                                           help=t("cli.h.all")),
          config: Optional[str] = CFG) -> None:
    """Run n requests and print aggregated statistics (mean/p50/p95/min/max)."""
    if all_profiles:
        targets = _load(config)
    else:
        targets = [_pick(profile, base_url, model, api_key, api_key_env,
                         config, prompt, max_tokens, temperature)]
    rows: list[tuple[str, Agg]] = []
    for i, target in enumerate(targets):
        label = t("cli.benching", name=target.profile, n=n, c=concurrency)
        if len(targets) > 1:
            label += f" ({i + 1}/{len(targets)})"
        with console.status(label):
            results, wall = asyncio.run(bench_run(
                target, n=n, concurrency=concurrency, stream=stream))
        apply_cost(results, target)
        agg = aggregate(results, wall)
        rows.append((target.profile, agg))
        console.print(bench_tables(agg, target, n, concurrency, stream))
        console.print()
        if agg.ok == 0:
            _error_hint(results[0])
    if all_profiles:
        console.print(compare_table(rows))
    if rows and all(a.ok == 0 for _, a in rows):
        raise typer.Exit(1)


@app.command(help=t("cli.h.probe"))
def probe(profile: Optional[str] = PROFILE,
          base_url: Optional[str] = BASE_URL,
          model: Optional[str] = MODEL,
          api_key: Optional[str] = API_KEY,
          api_key_env: Optional[str] = KEY_ENV,
          timeout: float = typer.Option(120.0, "--timeout",
                                        help=t("cli.h.timeout")),
          strict: bool = typer.Option(False, "--strict",
                                      help=t("cli.h.strict")),
          config: Optional[str] = CFG) -> None:
    """Downgrade probe: 6 fixed checks, regex-scored, no judge model."""
    target = _pick(profile, base_url, model, api_key, api_key_env, config)
    with console.status(t("cli.probing", name=target.profile)) as status:
        def on_progress(cr) -> None:
            mark = t("probe.pass") if cr.passed else t("probe.fail")
            status.update(f"{t('cli.probing', name=target.profile)} "
                          f"[{DIM}]({cr.name}: {mark})[/]")
        report = asyncio.run(run_probe(target, timeout=timeout,
                                       on_progress=on_progress))
    console.print(probe_tables(report, target))
    if report.errors or (strict and (report.score or 0) < 85):
        raise typer.Exit(1)


@app.command(help=t("cli.h.scan"))
def scan(profile: Optional[str] = PROFILE,
         base_url: Optional[str] = BASE_URL,
         api_key: Optional[str] = API_KEY,
         api_key_env: Optional[str] = KEY_ENV,
         concurrency: int = typer.Option(4, "-c", "--concurrency", min=1,
                                         help=t("cli.h.concurrency")),
         only: Optional[str] = typer.Option(None, "--only",
                                            help=t("cli.h.only")),
         limit: Optional[int] = typer.Option(None, "--limit",
                                             help=t("cli.h.limit")),
         timeout: float = typer.Option(20.0, "--timeout",
                                       help=t("cli.h.timeout")),
         config: Optional[str] = CFG) -> None:
    """Scan a relay: GET /models, then test every model for TTFT and status."""
    target = _pick(profile, base_url, None, api_key, api_key_env, config,
                   need_model=False)
    with console.status(t("cli.scanning", host=target.host)) as status:
        done = [0]

        def on_progress(row) -> None:
            done[0] += 1
            mark = t("scan.ok") if row.ok else t("scan.fail")
            status.update(f"{t('cli.scanning', host=target.host)} "
                          f"[{DIM}]({done[0]}: {mark} {row.model})[/]")
        report = asyncio.run(scan_endpoint(
            target, only=only, limit=limit, concurrency=concurrency,
            timeout=timeout, on_progress=on_progress))
    console.print(scan_tables(report, target))
    if report.fetch_error:
        raise typer.Exit(1)
    if not report.alive:
        raise typer.Exit(1)


@app.command(help=t("cli.h.tui"))
def tui(config: Optional[str] = CFG) -> None:
    """Open the interactive TUI."""
    try:
        from .tui import LlmtapApp
    except ImportError as exc:
        console.print(f"[{BAD}]{t('cli.tui_missing')}[/] {exc}")
        raise typer.Exit(1)
    LlmtapApp(config_path=config).run()


@app.command(help=t("cli.h.init"))
def init(path: Optional[str] = typer.Option(None, "--path",
                                           help=t("cli.h.path")),
         force: bool = typer.Option(False, "--force",
                                    help=t("cli.h.force"))) -> None:
    """Create a starter config file."""
    dest = Path(path).expanduser() if path else USER_CONFIG_PATH
    if not write_template(dest, force=force):
        console.print(f"[{WARN}]{t('cli.init_exists', path=dest)}[/]")
        raise typer.Exit(1)
    console.print(f"[{OK}]{t('cli.init_done', path=dest)}[/]")


@app.command(help=t("cli.h.add"))
def add(name: str = typer.Argument(..., help=t("cli.h.name")),
        base_url: str = typer.Option(..., "-u", "--base-url"),
        model: Optional[List[str]] = typer.Option(None, "-m", "--model",
                                                 help=t("cli.h.model")),
        api_key: Optional[str] = typer.Option(None, "-k", "--api-key"),
        api_key_env: Optional[str] = typer.Option(None, "--api-key-env"),
        config: Optional[str] = CFG) -> None:
    """Add a profile to the config file. Creates the file when missing."""
    path = Path(config).expanduser() if config else find_config()
    if path is None:
        path = USER_CONFIG_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_template(path)
    models = [*(model or [])]
    if not models:
        key, env = _resolve_key(api_key, api_key_env)
        listing = adhoc_target(base_url, "", env, api_key=key)
        _, ids, err = asyncio.run(list_models(listing))
        if err or not ids:
            console.print(f"[{BAD}]{t('err.no_models', url=base_url)}[/]")
            raise typer.Exit(1)
        models = [ids[0]] if len(ids) == 1 else [
            _choose(ids, t("cli.pick_model"))]
    try:
        append_profile(path, name, base_url, models,
                       api_key_env=api_key_env or "",
                       api_key=api_key or "")
    except ConfigError as exc:
        console.print(f"[{BAD}]{exc}[/]")
        raise typer.Exit(1)
    console.print(f"[{OK}]{t('cli.add_done', name=name, path=path)}[/]")
    if api_key:
        console.print(f"[{WARN}]{t('cli.key_plain_text', path=path)}[/]")
    console.print(f"[{DIM}]llmtap test {name}[/]")


@app.command(help=t("cli.h.version"))
def version() -> None:
    """Print the version."""
    console.print(f"llmtap {__version__}")


def _force_utf8_streams() -> None:
    """Windows pipes default to a legacy code page. Chinese help text
    then raises UnicodeEncodeError. Reconfigure the streams to UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and stream.encoding and \
                    stream.encoding.lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass


def main() -> None:
    _force_utf8_streams()
    app()


if __name__ == "__main__":
    main()
