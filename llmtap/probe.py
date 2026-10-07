"""Model quality probe: fixed questions with checkable answers.

Detects model downgrade on relay stations. Six checks, no judge model:
string and regex rules only. Score = sum of weights of passed checks.
Any request failure makes the run inconclusive, not scored.

All prompts are English on purpose: they are test data, not UI text.
"""

from __future__ import annotations

import base64
import random
import re
from dataclasses import dataclass, field

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .client import RequestResult, chat_with_fallback
from .config import ModelTarget
from .i18n import t
from .theme import HEADER, VERDICT, table_box

PROBE_MAX_TOKENS = 2048


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _numbers(s: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", s or "")


BASE64_PLAIN = "BANANA-42"
NEEDLE_CODE = "7391"

# --- answer matchers -------------------------------------------------------

def m_instruction(ans: str) -> bool:
    a = _norm(ans).strip("\"'`*。.!?!,、:： ")
    return a == "apple"


def m_base64(ans: str) -> bool:
    return "banana-42" in _norm(ans)


def m_needle(ans: str) -> bool:
    return NEEDLE_CODE in (ans or "")


def m_batball(ans: str) -> bool:
    a = _norm(ans)
    if any(n == "0.05" for n in _numbers(a)):
        return True
    if ("美分" in a or "cent" in a) and any(n == "5" for n in _numbers(a)):
        return True
    return False


def m_math(ans: str) -> bool:
    return any(n == "408" for n in _numbers(ans))


def m_setlen(ans: str) -> bool:
    return any(n == "3" for n in _numbers(ans))


# --- needle filler ---------------------------------------------------------

_FILLER = [
    "The weather report says rain is likely this afternoon.",
    "The library opens at eight in the morning and closes at ten.",
    "The restaurant across the street is famous for its eggplant.",
    "The south square of the train station is under repair.",
    "He runs five kilometers every morning and has done so for years.",
    "The meeting room is on the third floor, second door on the left.",
    "The supermarket sells milk at half price this week.",
    "Chapter three of the book covers the industrial revolution.",
    "The company health check is scheduled for the fifteenth.",
    "The cherry trees in the park are expected to bloom next week.",
    "The last subway train leaves at half past eleven.",
    "The printer on the second floor needs a new toner cartridge.",
]


def needle_text(code: str) -> str:
    """Deterministic English filler text with a 4-digit code in the middle."""
    rng = random.Random(42)
    parts = [rng.choice(_FILLER) for _ in range(120)]
    parts.insert(60, f"By the way, the access code for today is {code}. "
                     f"Please keep it private.")
    return " ".join(parts)


# --- check bank ------------------------------------------------------------

CHECKS: list[dict] = [
    {
        "id": "instruction", "name_key": "probe.instruction", "weight": 10,
        "prompt": "Reply with exactly this word and nothing else: APPLE",
        "expect": "APPLE", "match": m_instruction,
    },
    {
        "id": "base64", "name_key": "probe.base64", "weight": 15,
        "prompt": ("Decode this Base64 string. Reply with only the decoded "
                   "text:\n"
                   + base64.b64encode(BASE64_PLAIN.encode()).decode()),
        "expect": BASE64_PLAIN, "match": m_base64,
    },
    {
        "id": "needle", "name_key": "probe.needle", "weight": 20,
        "prompt": ("A four-digit access code is hidden in the text below. "
                   "Reply with only the four digits.\n\n"
                   + needle_text(NEEDLE_CODE)),
        "expect": NEEDLE_CODE, "match": m_needle,
    },
    {
        "id": "batball", "name_key": "probe.batball", "weight": 15,
        "prompt": ("A bat and a ball cost $1.10 in total. The bat costs "
                   "$1.00 more than the ball. How much does the ball cost? "
                   "Reply with only the price."),
        "expect": "0.05", "match": m_batball,
    },
    {
        "id": "math", "name_key": "probe.math", "weight": 20,
        "prompt": "What is 17 x 24? Reply with only the number.",
        "expect": "408", "match": m_math,
    },
    {
        "id": "setlen", "name_key": "probe.setlen", "weight": 20,
        "prompt": ("How many unique elements are in the list "
                   "[1, 1, 2, 3, 3, 3] after duplicates are removed? "
                   "Reply with only the number."),
        "expect": "3", "match": m_setlen,
    },
]


# --- runner ----------------------------------------------------------------

@dataclass
class CheckResult:
    check_id: str
    name: str
    weight: int
    passed: bool | None = None  # None = request failed
    expected: str = ""
    got: str = ""
    error: str = ""
    ms: float | None = None


@dataclass
class ProbeReport:
    results: list[CheckResult] = field(default_factory=list)
    model_reported: str = ""

    @property
    def total_weight(self) -> int:
        return sum(c.weight for c in self.results)

    @property
    def errors(self) -> list[str]:
        return [c.error for c in self.results if c.passed is None and c.error]

    @property
    def score(self) -> float | None:
        if self.errors:
            return None
        return sum(c.weight for c in self.results if c.passed)

    @property
    def verdict_key(self) -> str:
        if self.errors:
            return "inconclusive"
        s = self.score or 0
        if s >= 85:
            return "ok"
        if s >= 60:
            return "partial"
        return "fail"

    @property
    def verdict(self) -> str:
        return t(f"probe.v.{self.verdict_key}")


async def run_probe(target: ModelTarget, *, checks: list[dict] | None = None,
                    timeout: float | None = None,
                    on_progress=None) -> ProbeReport:
    """Run all checks sequentially. temperature=0, non-stream."""
    report = ProbeReport()
    for chk in (checks or CHECKS):
        r: RequestResult = await chat_with_fallback(
            target, prompt=chk["prompt"], stream=False,
            max_tokens=PROBE_MAX_TOKENS, temperature=0.0, timeout=timeout)
        if not r.ok:
            cr = CheckResult(chk["id"], t(chk["name_key"]), chk["weight"],
                             passed=None, expected=chk["expect"],
                             error=r.error, ms=r.total_ms)
        else:
            passed = bool(chk["match"](r.text))
            got = " ".join(r.text.split())
            cr = CheckResult(chk["id"], t(chk["name_key"]), chk["weight"],
                             passed=passed, expected=chk["expect"],
                             got=got[:80], ms=r.total_ms)
        if r.model_reported:
            report.model_reported = r.model_reported
        report.results.append(cr)
        if on_progress:
            on_progress(cr)
    return report


# --- render ----------------------------------------------------------------

_VERDICT_STYLE = VERDICT


def _mark(cr: CheckResult) -> str:
    if cr.passed is None:
        return f"[red]{t('probe.err')}[/red]"
    if cr.passed:
        return f"[green]{t('probe.pass')}[/green]"
    return f"[red]{t('probe.fail')}[/red]"


def probe_tables(report: ProbeReport, target: ModelTarget) -> Group:
    t_ = Table(title=t("probe.title", profile=target.profile,
                       n=len(report.results)),
               box=table_box(), header_style=HEADER)
    for key in ("col.check", "col.weight", "col.result", "col.latency",
                "col.expected", "col.got"):
        t_.add_column(t(key))
    for cr in report.results:
        t_.add_row(cr.name, str(cr.weight), _mark(cr),
                   f"{cr.ms:.0f} ms" if cr.ms else "-",
                   cr.expected, cr.got or " ".join(cr.error.split())[:60])

    score = report.score
    score_s = f"{score:.0f}" if score is not None else "?"
    style = _VERDICT_STYLE[report.verdict_key]
    lines = [t("probe.score", score=score_s, total=report.total_weight),
             t("probe.verdict", verdict=report.verdict)]
    if report.model_reported:
        lines.append(t("probe.model_reported", model=report.model_reported))
    if report.errors:
        lines.append(t("probe.errors", errors="; ".join(report.errors)[:200]))
    return Group(t_, Panel(Text.from_markup("\n".join(lines)),
                           border_style=style))
