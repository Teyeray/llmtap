"""Textual TUI: model config table, live output, stats and sparkline.

Layout follows mature Textual apps: a Header, one card per area with
rounded borders and titles, a Footer that lists the keys. Press ? for
a full key guide, t to switch the UI language at any time.
"""

from __future__ import annotations

import time

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (DataTable, Footer, Header, ProgressBar,
                             RichLog, Sparkline, Static)

from .client import bench_run, list_models, run_chat
from .config import ConfigError, ModelTarget, load_targets
from .i18n import t, toggle_lang
from .probe import probe_tables, run_probe
from .report import bench_tables, single_result_table, target_detail
from .scan import scan_endpoint, scan_tables
from .stats import aggregate, apply_cost
from .theme import ACCENT, BAD, DIM, OK, tui_theme


BENCH_N = 5
SPARK_SAMPLES = 80

COL_KEYS = ("col.profile", "col.model", "col.base_url", "col.api_key",
            "col.temp", "col.max_tok", "col.timeout", "col.price_in",
            "col.price_out")


def _help_table() -> Table:
    """Key guide used by the help screen."""
    table = Table(box=None, padding=(0, 2, 0, 0), show_header=False)
    table.add_column(style=f"bold {ACCENT}", justify="center")
    table.add_column()
    rows = [
        ("r", "tui.help.test"), ("b", "tui.help.bench"),
        ("p", "tui.help.probe"), ("s", "tui.help.scan"),
        ("m", "tui.help.models"), ("enter", "tui.help.enter"),
        ("l", "tui.help.reload"), ("t", "tui.help.lang"),
        ("?", "tui.help.help"), ("q", "tui.help.quit"),
    ]
    for key, desc in rows:
        table.add_row(key, t(desc))
    return table


class DetailsScreen(ModalScreen[None]):
    """Modal that shows the full config of one target."""

    BINDINGS = [
        Binding("enter,escape,q", "dismiss_screen", "Close"),
    ]

    def __init__(self, target: ModelTarget) -> None:
        super().__init__()
        self.target = target

    def compose(self) -> ComposeResult:
        yield Static(target_detail(self.target), id="details", expand=True)

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    """Modal with the full key guide."""

    BINDINGS = [
        Binding("escape,q,question_mark", "dismiss_screen", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-card"):
            with VerticalScroll():
                yield Static(_help_table(), id="help")

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


class LlmtapApp(App[None]):
    """Terminal UI for llmtap."""

    CSS = """#table-card { height: 40%; border: round $panel; background: $surface;
              padding: 0 1; }
#table { height: 1fr; }

#panes { height: 1fr; }
#log-card { width: 2fr; border: round $panel; background: $surface;
            padding: 0 1; }
#log { height: 1fr; }

#stats-col { width: 1fr; }
#stats-card { height: 1fr; border: round $panel; background: $surface;
              padding: 0 1; }
#stats-card > VerticalScroll { height: 1fr; }
#spark-card { height: 8; border: round $panel; background: $surface; }
#spark { height: 1fr; }
#progress { height: 3; display: none; padding: 0 1; }

ModalScreen { align: center middle; }
#details { width: 84; max-height: 85%; background: $surface;
            border: round $accent; padding: 0 1; }
#help-card { width: 84; max-height: 85%; background: $surface;
             border: round $accent; padding: 0 2; }
#help-card > VerticalScroll { height: auto; max-height: 80%; }
"""

    TITLE = "llmtap"

    # Footer descriptions resolve at import, from the startup language.
    BINDINGS = [
        Binding("r", "run_test", t("tui.key.test")),
        Binding("b", "bench", t("tui.key.bench")),
        Binding("p", "probe", t("tui.key.probe")),
        Binding("s", "scan", t("tui.key.scan")),
        Binding("m", "models", t("tui.key.models")),
        Binding("l", "reload", t("tui.key.reload")),
        Binding("t", "toggle_lang", t("tui.key.lang")),
        Binding("question_mark", "help", t("tui.key.help")),
        Binding("q", "quit", t("tui.key.quit")),
    ]

    def __init__(self, config_path: str | None = None) -> None:
        super().__init__()
        theme = tui_theme()
        if theme is not None:
            self.register_theme(theme)
        self.theme = "llmtap"
        self.config_path = config_path
        self.targets: list[ModelTarget] = []
        self.busy = False
        self._tps_samples: list[float] = []

    # ---------- layout ----------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="table-card"):
            yield DataTable(id="table", cursor_type="row",
                            zebra_stripes=True)
        with Horizontal(id="panes"):
            with Vertical(id="log-card"):
                yield RichLog(id="log", markup=True, wrap=True, max_lines=400)
            with Vertical(id="stats-col"):
                with Vertical(id="stats-card"):
                    with VerticalScroll():
                        yield Static(id="stats_inner")
                with Vertical(id="spark-card"):
                    yield Sparkline([], id="spark")
                yield ProgressBar(id="progress", show_eta=False)
        yield Footer()

    def on_mount(self) -> None:
        self._apply_texts()
        self._build_table()
        self.reload_config()
        self.query_one("#table", DataTable).focus()

    def _apply_texts(self) -> None:
        """Set every pane title from the current language."""
        self.sub_title = t("tui.subtitle")
        self.query_one("#table-card", Vertical).border_title = \
            t("tui.title_table")
        self.query_one("#log-card", Vertical).border_title = \
            t("tui.title_log")
        self.query_one("#stats-card", Vertical).border_title = \
            t("tui.title_stats")
        self.query_one("#spark-card", Vertical).border_title = \
            t("tui.title_spark")

    def _build_table(self) -> None:
        table = self.query_one("#table", DataTable)
        table.clear(columns=True)
        for key in COL_KEYS:
            table.add_column(t(key))
        for target in self.targets:
            temp = "-" if target.temperature is None else f"{target.temperature}"
            mt = "-" if target.max_tokens is None else f"{target.max_tokens}"
            pin = "-" if target.price_in is None else f"{target.price_in}"
            pout = "-" if target.price_out is None else f"{target.price_out}"
            table.add_row(target.profile, target.model, target.base_url,
                          target.key_display, temp, mt,
                          f"{target.timeout_s:.0f}", pin, pout,
                          key=target.profile)

    def reload_config(self) -> None:
        try:
            self.targets = load_targets(self.config_path)
        except ConfigError as e:
            self.targets = []
            self.log_line(f"[{BAD}]{t('tui.config_error', msg=e)}[/]")
            return
        self._build_table()
        src = self.targets[0].source
        self.log_line(f"[{DIM}]{t('tui.loaded', n=len(self.targets), src=src)}[/]")

    # ---------- helpers ----------

    @property
    def current_target(self) -> ModelTarget | None:
        table = self.query_one("#table", DataTable)
        if not self.targets:
            return None
        row = min(table.cursor_row, len(self.targets) - 1)
        return self.targets[row]

    def log_line(self, text: str) -> None:
        self.query_one("#log", RichLog).write(Text.from_markup(text))

    def show_stats(self, renderable) -> None:
        self.query_one("#stats_inner", Static).update(renderable)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        progress = self.query_one("#progress", ProgressBar)
        if not busy:
            progress.display = False

    def _progress_start(self, total: float | None) -> None:
        progress = self.query_one("#progress", ProgressBar)
        progress.update(total=total, progress=0)
        progress.display = True

    def _progress_tick(self) -> None:
        self.query_one("#progress", ProgressBar).advance()

    # ---------- actions ----------

    def action_reload(self) -> None:
        self.reload_config()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_toggle_lang(self) -> None:
        lang = toggle_lang()
        self._apply_texts()
        self._build_table()
        name = t("lang.zh") if lang == "zh" else t("lang.en")
        self.notify(t("tui.lang_switched", lang=name), timeout=3)

    def on_data_table_row_selected(self, event) -> None:
        target = self.current_target
        if target:
            self.push_screen(DetailsScreen(target))

    def action_run_test(self) -> None:
        target = self.current_target
        if target and not self.busy:
            self.run_worker(self._run_single(target), exclusive=True)

    def action_bench(self) -> None:
        target = self.current_target
        if target and not self.busy:
            self.run_worker(self._run_bench(target), exclusive=True)

    def action_probe(self) -> None:
        target = self.current_target
        if target and not self.busy:
            self.run_worker(self._run_probe(target), exclusive=True)

    def action_scan(self) -> None:
        target = self.current_target
        if target and not self.busy:
            self.run_worker(self._run_scan(target), exclusive=True)

    def action_models(self) -> None:
        target = self.current_target
        if target and not self.busy:
            self.run_worker(self._run_models(target), exclusive=True)

    # ---------- workers ----------

    async def _run_single(self, target: ModelTarget) -> None:
        self._set_busy(True)
        self.sub_title = f"{t('tui.testing', name=target.profile)}"
        self._tps_samples = []
        self.query_one("#spark", Sparkline).data = []
        self.show_stats(Panel(f"[b]{target.profile}[/b]\n"
                              f"{t('tui.waiting')}"))
        last_ui = [0.0]

        def on_event(kind: str, data: dict) -> None:
            if kind != "token":
                return
            self._tps_samples.append(data["tps"])
            now = time.monotonic()
            if now - last_ui[0] < 0.15:
                return
            last_ui[0] = now
            line = (f"[b]{target.profile}[/b]\n"
                    f"{data['tokens']} tok  {data['elapsed_ms']:.0f} ms\n"
                    f"[{ACCENT}]{data['tps']:.1f} tok/s[/]")
            self.show_stats(Panel(Text.from_markup(line)))
            spark = self.query_one("#spark", Sparkline)
            spark.data = self._tps_samples[-SPARK_SAMPLES:]

        result = await run_chat(target, on_event=on_event)
        apply_cost([result], target)
        if self._tps_samples:
            self.query_one("#spark", Sparkline).data = \
                self._tps_samples[-SPARK_SAMPLES:]
        self.show_stats(single_result_table(result, target))
        mark = f"[{OK}]{t('n.ok')}[/]" if result.ok \
            else f"[{BAD}]{t('n.failed')}[/]"
        self.log_line(f"{target.profile}: {mark} "
                      f"ttft={result.ttft_ms or 0:.0f}ms "
                      f"total={result.total_ms or 0:.0f}ms")
        if result.ok:
            preview = result.text[:200] \
                or f"({result.reasoning_chars} reasoning chars)"
            self.log_line(f"[{DIM}]{preview}[/]")
        elif result.error:
            self.log_line(f"[{BAD}]{result.error}[/]")
            self.notify(result.error[:120], severity="error", timeout=5)
        self._set_busy(False)
        self.sub_title = t("tui.subtitle")

    async def _run_bench(self, target: ModelTarget) -> None:
        self._set_busy(True)
        self.sub_title = f"{t('tui.benching', name=target.profile, n=BENCH_N)}"
        self._progress_start(BENCH_N)
        self.show_stats(Panel(f"[b]{target.profile}[/b]\n"
                              f"{t('tui.benching', name='', n=BENCH_N)}"))
        done = [0]

        def on_progress(i: int, r) -> None:
            done[0] += 1
            self._progress_tick()
            mark = t("n.ok") if r.ok else t("n.failed")
            self.log_line(f"[{DIM}]{done[0]}/{BENCH_N}[/] {mark} "
                          f"ttft={r.ttft_ms or 0:.0f}ms "
                          f"total={r.total_ms or 0:.0f}ms")

        results, wall = await bench_run(
            target, n=BENCH_N, concurrency=1, on_progress=on_progress)
        apply_cost(results, target)
        agg = aggregate(results, wall)
        self.show_stats(bench_tables(agg, target, BENCH_N, 1, True))
        self.log_line(t("tui.bench_done", name=f"[b]{target.profile}[/b]",
                        ok=agg.ok, n=agg.n))
        self._set_busy(False)
        self.sub_title = t("tui.subtitle")

    async def _run_probe(self, target: ModelTarget) -> None:
        self._set_busy(True)
        self.sub_title = f"{t('tui.probing', name=target.profile)}"
        self._progress_start(6)
        self.show_stats(Panel(f"[b]{target.profile}[/b]\n"
                              f"{t('tui.probe_running')}"))
        done = [0]

        def on_progress(cr) -> None:
            done[0] += 1
            self._progress_tick()
            if cr.passed is None:
                mark = t("probe.err")
            elif cr.passed:
                mark = t("probe.pass")
            else:
                mark = t("probe.fail")
            ms_s = f" ({cr.ms:.0f} ms)" if cr.ms else ""
            self.log_line(f"[{DIM}]{done[0]}/6[/] {cr.name}: "
                          f"{mark}{ms_s}")

        report = await run_probe(target, on_progress=on_progress)
        self.show_stats(probe_tables(report, target))
        score = report.score
        score_s = f"{score:.0f}" if score is not None else "?"
        self.log_line(t("tui.probe_done", name=f"[b]{target.profile}[/b]",
                        score=score_s, verdict=report.verdict))
        self._set_busy(False)
        self.sub_title = t("tui.subtitle")

    async def _run_scan(self, target: ModelTarget) -> None:
        self._set_busy(True)
        self.sub_title = f"{t('tui.scanning', host=target.host)}"
        self.show_stats(Panel(f"[b]{target.host}[/b]\n"
                              f"{t('tui.listing')}"))
        done = [0]

        def on_progress(row) -> None:
            done[0] += 1
            mark = t("scan.ok") if row.ok else t("scan.fail")
            ttft = f"{row.ttft_ms:.0f}ms" if row.ttft_ms is not None else "-"
            self.log_line(f"[{DIM}]{done[0]}[/] {mark} {row.model} "
                          f"ttft={ttft}")

        report = await scan_endpoint(target, concurrency=4,
                                     on_progress=on_progress)
        self.show_stats(scan_tables(report, target))
        self.log_line(t("tui.scan_done", host=f"[b]{target.host}[/b]",
                        ok=len(report.alive), n=len(report.rows)))
        if report.fetch_error:
            self.log_line(f"[{BAD}]{report.fetch_error}[/]")
            self.notify(report.fetch_error[:120], severity="error",
                        timeout=5)
        self._set_busy(False)
        self.sub_title = t("tui.subtitle")

    async def _run_models(self, target: ModelTarget) -> None:
        self._set_busy(True)
        self.sub_title = f"{t('tui.getting_models', host=target.host)}"
        status, ids, err = await list_models(target)
        if err:
            self.log_line(f"[{BAD}]{err}[/]")
        else:
            self.log_line(t("tui.models_done",
                            host=f"[b]{target.host}[/b]", n=len(ids)))
            self.log_line(", ".join(ids))
            table = Table(title=t("report.get_models"), box=None)
            table.add_column(t("col.model_id"))
            for i in ids:
                table.add_row(i)
            self.show_stats(table)
        self._set_busy(False)
        self.sub_title = t("tui.subtitle")


if __name__ == "__main__":
    LlmtapApp().run()
