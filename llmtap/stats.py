"""Aggregation of RequestResult objects into benchmark statistics."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .client import RequestResult
from .config import ModelTarget


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolated percentile. p is 0..100."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def stats(values: list[float]) -> dict | None:
    """Mean, p50, p95, min, max and sample stdev for a value list."""
    if not values:
        return None
    n = len(values)
    mean = sum(values) / n
    var = (sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
    return {
        "n": n,
        "mean": mean,
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "min": min(values),
        "max": max(values),
        "stdev": math.sqrt(var),
    }


@dataclass
class Agg:
    n: int
    ok: int
    wall_s: float
    ttft_ms: dict | None = None
    total_ms: dict | None = None
    itl_ms: dict | None = None
    tps: dict | None = None
    out_tokens: dict | None = None
    in_tokens_total: int = 0
    out_tokens_total: int = 0
    cost_total: float | None = None
    errors: list[str] = None  # type: ignore[assignment]

    @property
    def error_rate(self) -> float:
        return (self.n - self.ok) / self.n if self.n else 0.0

    @property
    def req_per_s(self) -> float:
        return self.ok / self.wall_s if self.wall_s > 0 else 0.0


def apply_cost(results: list[RequestResult], target: ModelTarget) -> None:
    """Fill cost_usd on each result from the target pricing, when known."""
    if target.price_in is None and target.price_out is None:
        return
    for r in results:
        if not r.ok:
            continue
        cost = 0.0
        known = False
        if r.input_tokens is not None and target.price_in is not None:
            cost += r.input_tokens / 1e6 * target.price_in
            known = True
        if r.output_tokens is not None and target.price_out is not None:
            cost += r.output_tokens / 1e6 * target.price_out
            known = True
        if known:
            r.cost_usd = cost


def aggregate(results: list[RequestResult], wall_s: float) -> Agg:
    """Compute the benchmark statistics developers care about."""
    ok = [r for r in results if r.ok]

    def col(fn) -> list[float]:
        return [v for r in ok if (v := fn(r)) is not None]

    ttft = stats(col(lambda r: r.ttft_ms))
    total = stats(col(lambda r: r.total_ms))
    itl = stats([x for r in ok for x in r.itl_ms])
    tps = stats(col(lambda r: r.tps_decode or r.tps_overall))
    out = stats(col(lambda r: float(r.output_tokens)
                    if r.output_tokens is not None else None))
    cost_vals = [r.cost_usd for r in ok if r.cost_usd is not None]
    errors = [f"[{r.status}] {r.error}".replace("[None] ", "")
              for r in results if not r.ok]
    return Agg(
        n=len(results),
        ok=len(ok),
        wall_s=wall_s,
        ttft_ms=ttft,
        total_ms=total,
        itl_ms=itl,
        tps=tps,
        out_tokens=out,
        in_tokens_total=sum(r.input_tokens or 0 for r in ok),
        out_tokens_total=sum(r.output_tokens or 0 for r in ok),
        cost_total=sum(cost_vals) if cost_vals else None,
        errors=errors,
    )
