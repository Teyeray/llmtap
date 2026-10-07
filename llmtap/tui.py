"""Textual TUI: model config table, live test view, stats panel."""

from __future__ import annotations

import time

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, RichLog, Static

from .client import bench_run, list_models, run_chat
from .config import ConfigError, ModelTarget, load_targets
from .report import bench_tables, single_result_table
from .stats import aggregate, apply_cost

CSS = """
#table { height: 45%; }
#panes { height: 1fr; }
#log { width: 2fr; border: round $primary; padding: 0 1; }
#stats { width: 1fr; border: round $secondary; }
#stats Static { padding: 0 1; }
DetailsScreen { align: center middle; }
#details { width: 72; max-height: 80%; border: thick $accent; padding: 1 2; background: $surface; }
"""

BENCH_N = 5


class DetailsScreen(ModalScreen[None]):
    """Modal that shows the full config of one target."""

    BINDINGS = [
        Binding("enter,escape,q", "dismiss_screen", "Close"),
    ]

    def __init__(self, target: ModelTarget) -> None:
        super().__init__()
        self.target = target

    def compose(self) -> ComposeResult:
        from rich.pretty import Pretty
        yield Static(Pretty(self.target.safe_dict()), id="details",
                     expand=True)

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


class LlmtapApp(App[None]):
    TITLE = "llmtap — LLM API tester"
    SUB_TITLE = "r test · b bench · enter details · m models · l reload"

    BINDINGS = [
        Binding("r", "run_test", "Test"),
        Binding("b", "bench", f"Bench x{BENCH_N}"),
        Binding("m", "models", "Models"),
        Binding("l", "reload", "Reload"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, config_path: str | None = None) -> None:
        super().__init__()
        self.config_path = config_path
        self.targets: list[ModelTarget] = []
        self.busy = False

    # ---------- layout ----------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
        with Horizontal(id="panes"):
            yield RichLog(id="log", markup=True, wrap=True)
            yield Static(id="stats")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        for col in ("profile", "model", "base_url", "api key", "temp",
                    "max_tok", "timeout", "$in/1M", "$out/1M"):
            table.add_column(col)
        self.reload_config()

    def reload_config(self) -> None:
        try:
            self.targets = load_targets(self.config_path)
        except ConfigError as e:
            self.targets = []
            self.log_line(f"[red]config error: {e}[/red]")
            return
        table = self.query_one("#table", DataTable)
        table.clear()
        for t in self.targets:
            temp = "-" if t.temperature is None else f"{t.temperature}"
            mt = "-" if t.max_tokens is None else f"{t.max_tokens}"
            pin = "-" if t.price_in is None else f"{t.price_in}"
            pout = "-" if t.price_out is None else f"{t.price_out}"
            table.add_row(t.profile, t.model, t.base_url, t.key_display,
                          temp, mt, f"{t.timeout_s:.0f}", pin, pout,
                          key=t.profile)
        self.log_line(f"[dim]loaded {len(self.targets)} targets "
                      f"from {self.targets[0].source}[/dim]")

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
        self.query_one("#stats", Static).update(renderable)

    # ---------- actions ----------

    def action_reload(self) -> None:
        self.reload_config()

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

    def action_models(self) -> None:
        target = self.current_target
        if target and not self.busy:
            self.run_worker(self._run_models(target), exclusive=True)

    # ---------- workers ----------

    async def _run_single(self, target: ModelTarget) -> None:
        self.busy = True
        self.sub_title = f"testing {target.profile}…"
        self.show_stats(Panel(f"[b]{target.profile}[/b]\nwaiting for tokens…"))
        last_ui = [0.0]

        def on_event(kind: str, data: dict) -> None:
            if kind != "token":
                return
            now = time.monotonic()
            if now - last_ui[0] < 0.15:
                return
            last_ui[0] = now
            line = (f"[b]{target.profile}[/b]  "
                    f"{data['tokens']} tok  "
                    f"{data['elapsed_ms']:.0f} ms  "
                    f"[cyan]{data['tps']:.1f} tok/s[/cyan]")
            self.show_stats(Panel(Text.from_markup(line)))

        result = await run_chat(target, on_event=on_event)
        apply_cost([result], target)
        self.show_stats(single_result_table(result, target))
        status = "[green]ok[/green]" if result.ok else "[red]failed[/red]"
        self.log_line(f"{target.profile}: {status} "
                      f"ttft={result.ttft_ms or 0:.0f}ms "
                      f"total={result.total_ms or 0:.0f}ms")
        if result.ok:
            preview = result.text[:200] or f"({result.reasoning_chars} reasoning chars)"
            self.log_line(f"[dim]{preview}[/dim]")
        elif result.error:
            self.log_line(f"[red]{result.error}[/red]")
        self.busy = False
        self.sub_title = ""

    async def _run_bench(self, target: ModelTarget) -> None:
        self.busy = True
        self.sub_title = f"bench {target.profile} x{BENCH_N}…"
        done = [0]

        def on_progress(i: int, r) -> None:
            done[0] += 1
            mark = "ok" if r.ok else "ERR"
            self.log_line(f"[dim]{done[0]}/{BENCH_N}[/dim] {mark} "
                          f"ttft={r.ttft_ms or 0:.0f}ms "
                          f"total={r.total_ms or 0:.0f}ms")

        results, wall = await bench_run(
            target, n=BENCH_N, concurrency=1, on_progress=on_progress)
        apply_cost(results, target)
        agg = aggregate(results, wall)
        self.show_stats(bench_tables(agg, target, BENCH_N, 1, True))
        self.log_line(f"[b]{target.profile}[/b] bench done: "
                      f"{agg.ok}/{agg.n} ok")
        self.busy = False
        self.sub_title = ""

    async def _run_models(self, target: ModelTarget) -> None:
        self.busy = True
        self.sub_title = f"GET /models on {target.host}…"
        status, ids, err = await list_models(target)
        if err:
            self.log_line(f"[red]{err}[/red]")
        else:
            self.log_line(f"[b]{target.host}[/b]: {len(ids)} models")
            self.log_line(", ".join(ids))
            table = Table(title="GET /models", box=None)
            table.add_column("model id")
            for i in ids:
                table.add_row(i)
            self.show_stats(table)
        self.busy = False
        self.sub_title = ""


if __name__ == "__main__":
    LlmtapApp().run()
