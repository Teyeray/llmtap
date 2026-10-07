"""Async client for OpenAI-compatible chat completions, with precise timing.

Measures, per request:
- time to response headers
- time to first SSE chunk
- TTFT: first content or reasoning token
- inter-token latency (ITL) for every token
- total time, usage tokens, finish reason

Never raises. Every failure lands in RequestResult.error.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from .config import ModelTarget


def _trust_env(url: str) -> bool:
    """Use system proxy settings? Never for loopback endpoints.

    External APIs may need the system proxy. Local servers never do.
    Set LLMTAP_TRUST_ENV=0 to disable proxies everywhere.
    """
    override = os.environ.get("LLMTAP_TRUST_ENV")
    if override in ("0", "false", "no"):
        return False
    host = (urlparse(url).hostname or "").lower()
    return host not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


@dataclass
class RequestResult:
    ok: bool = False
    status: int | None = None
    error: str = ""
    stream: bool = True

    # timings in ms
    headers_ms: float | None = None     # request start to response headers
    first_chunk_ms: float | None = None  # request start to first SSE data line
    ttft_ms: float | None = None         # request start to first token
    total_ms: float | None = None        # request start to stream end

    # tokens
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_estimated: bool = False
    reasoning_chars: int = 0
    itl_ms: list[float] = field(default_factory=list)

    text: str = ""
    finish_reason: str = ""
    model_reported: str = ""
    cost_usd: float | None = None

    @property
    def token_chunks(self) -> int:
        return len(self.itl_ms) + 1 if self.ttft_ms is not None else 0

    @property
    def tps_overall(self) -> float | None:
        """Output tokens per second over the whole request."""
        if self.total_ms and self.output_tokens:
            return self.output_tokens / (self.total_ms / 1000)
        return None

    @property
    def tps_decode(self) -> float | None:
        """Output tokens per second over the decode phase only."""
        if (self.total_ms and self.ttft_ms is not None
                and self.output_tokens and self.total_ms > self.ttft_ms):
            span = (self.total_ms - self.ttft_ms) / 1000
            return self.output_tokens / span if span > 0 else None
        return None


def _headers(target: ModelTarget) -> dict:
    h = {"Content-Type": "application/json"}
    if target.api_key:
        h["Authorization"] = f"Bearer {target.api_key}"
    h.update(target.headers)
    return h


def _payload(target: ModelTarget, prompt: str, stream: bool,
             max_tokens: int | None, temperature: float | None,
             include_usage: bool) -> dict:
    p: dict = {
        "model": target.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }
    if max_tokens is not None:
        p["max_tokens"] = max_tokens
    if temperature is not None:
        p["temperature"] = temperature
    if stream and include_usage:
        p["stream_options"] = {"include_usage": True}
    return p


def _http_err(status: int, body: str) -> str:
    body = " ".join(body.split())[:300]
    return f"HTTP {status}: {body}" if body else f"HTTP {status}"


def _consume_chunk(res: RequestResult, chunk: dict, t0: float,
                   last_t: list, on_event) -> None:
    if chunk.get("model"):
        res.model_reported = str(chunk["model"])
    usage = chunk.get("usage")
    if usage:
        res.input_tokens = usage.get("prompt_tokens", res.input_tokens)
        res.output_tokens = usage.get("completion_tokens", res.output_tokens)
        res.usage_estimated = False
    choices = chunk.get("choices") or []
    if not choices:
        return
    c0 = choices[0] or {}
    if c0.get("finish_reason"):
        res.finish_reason = str(c0["finish_reason"])
    delta = c0.get("delta") or {}
    content = delta.get("content") or ""
    reasoning = (delta.get("reasoning_content")
                 or delta.get("reasoning") or "")
    if not content and not reasoning:
        return
    now = time.perf_counter()
    if res.ttft_ms is None:
        res.ttft_ms = (now - t0) * 1000
    else:
        res.itl_ms.append((now - last_t[0]) * 1000)
    last_t[0] = now
    if content:
        res.text += content
    if reasoning:
        res.reasoning_chars += len(reasoning)
    if on_event:
        n_tok = res.token_chunks
        elapsed = (now - t0) * 1000
        span = elapsed - (res.ttft_ms or elapsed)
        tps = n_tok / (span / 1000) if span > 0 else 0.0
        on_event("token", {
            "text": content or reasoning,
            "tokens": n_tok,
            "elapsed_ms": elapsed,
            "tps": tps,
        })


def _fill_nonstream(res: RequestResult, data: dict) -> None:
    res.model_reported = str(data.get("model") or res.model_reported)
    usage = data.get("usage")
    if usage:
        res.input_tokens = usage.get("prompt_tokens")
        res.output_tokens = usage.get("completion_tokens")
        res.usage_estimated = False
    choices = data.get("choices") or []
    if choices:
        msg = (choices[0] or {}).get("message") or {}
        res.text += msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        if reasoning:
            res.reasoning_chars = len(reasoning)
        fr = (choices[0] or {}).get("finish_reason")
        if fr:
            res.finish_reason = str(fr)


async def run_chat(
    target: ModelTarget,
    *,
    prompt: str | None = None,
    stream: bool = True,
    max_tokens: int | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
    include_usage: bool = True,
    client: httpx.AsyncClient | None = None,
    on_event=None,
) -> RequestResult:
    """Run one chat completion and return a RequestResult with timings.

    max_tokens and temperature None mean "use the target value, or omit".
    """
    prompt = prompt if prompt is not None else target.prompt
    if max_tokens is None:
        max_tokens = target.max_tokens
    if temperature is None:
        temperature = target.temperature
    url = target.base_url.rstrip("/") + "/chat/completions"
    hdrs = _headers(target)
    to = httpx.Timeout(timeout or target.timeout_s, connect=15.0)

    payload = _payload(target, prompt, stream, max_tokens, temperature,
                       include_usage)
    attempts = [payload]
    if payload.get("stream_options"):
        # Some servers reject stream_options. Keep a fallback without it.
        attempts.append({k: v for k, v in payload.items()
                         if k != "stream_options"})

    own = client is None
    if own:
        client = httpx.AsyncClient(
            timeout=to, trust_env=_trust_env(target.base_url))

    res = RequestResult(stream=stream)
    try:
        for i, pl in enumerate(attempts):
            res = await _attempt(client, url, hdrs, to, pl, on_event)
            retryable = (
                i == 0
                and len(attempts) > 1
                and res.status == 400
                and ("stream_options" in res.error
                     or "unknown" in res.error.lower())
            )
            if not retryable:
                break
        _finalize(res)
    except httpx.TimeoutException as e:
        res.error = f"timeout: {type(e).__name__}"
    except httpx.HTTPError as e:
        res.error = f"network: {type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 - report, never crash the bench
        res.error = f"unexpected: {type(e).__name__}: {e}"
    finally:
        if own:
            await client.aclose()
    return res


async def _attempt(client: httpx.AsyncClient, url: str, hdrs: dict,
                   to: httpx.Timeout, payload: dict,
                   on_event) -> RequestResult:
    res = RequestResult(stream=bool(payload.get("stream")))
    t0 = time.perf_counter()
    if on_event:
        on_event("start", {})
    if res.stream:
        async with client.stream("POST", url, json=payload,
                                 headers=hdrs, timeout=to) as r:
            res.headers_ms = (time.perf_counter() - t0) * 1000
            res.status = r.status_code
            if r.status_code >= 400:
                body = (await r.aread()).decode("utf-8", "ignore")
                res.error = _http_err(r.status_code, body)
                res.total_ms = (time.perf_counter() - t0) * 1000
                return res
            raw_lines: list[str] = []
            last_t = [t0]
            async for line in r.aiter_lines():
                if not line:
                    continue
                if line.startswith(":"):
                    continue  # SSE keep-alive comment
                if not line.startswith("data:"):
                    continue
                data_s = line[5:].strip()
                if data_s == "[DONE]":
                    break
                if res.first_chunk_ms is None:
                    res.first_chunk_ms = (time.perf_counter() - t0) * 1000
                raw_lines.append(data_s)
                try:
                    chunk = json.loads(data_s)
                except json.JSONDecodeError:
                    continue
                _consume_chunk(res, chunk, t0, last_t, on_event)
            res.total_ms = (time.perf_counter() - t0) * 1000
            res._raw_stream = raw_lines  # noqa: SLF001 - fallback parse
    else:
        r = await client.post(url, json=payload, headers=hdrs, timeout=to)
        res.headers_ms = res.total_ms = (time.perf_counter() - t0) * 1000
        res.status = r.status_code
        if r.status_code >= 400:
            res.error = _http_err(r.status_code, r.text)
            return res
        try:
            _fill_nonstream(res, r.json())
        except json.JSONDecodeError:
            res.error = _http_err(200, "body is not valid JSON")
    return res


def _finalize(res: RequestResult) -> None:
    """Estimate tokens when the server sent no usage. Set the ok flag."""
    raw = getattr(res, "_raw_stream", None)
    if (res.status is not None and res.status < 400 and res.stream
            and res.first_chunk_ms is None and raw):
        # Server ignored SSE. Try to parse the whole body as one JSON object.
        try:
            data = json.loads("".join(raw))
        except json.JSONDecodeError:
            data = None
        if data:
            _fill_nonstream(res, data)
            res.ttft_ms = None
    res.ok = bool(
        res.status is not None
        and res.status < 400
        and not res.error
        and (res.text or res.reasoning_chars
             or (res.stream and res.first_chunk_ms is not None)
             or (not res.stream and res.total_ms is not None))
    )
    if res.ok and res.stream and res.first_chunk_ms is None and not res.text:
        res.ok = False
        res.error = res.error or "empty stream: no SSE data received"
    if res.ok and res.output_tokens is None:
        if res.token_chunks > 0:
            res.output_tokens = res.token_chunks
            res.usage_estimated = True
        elif res.text:
            res.output_tokens = max(1, len(res.text) // 4)
            res.usage_estimated = True


async def bench_run(
    target: ModelTarget,
    n: int,
    concurrency: int = 1,
    on_progress=None,
    **kw,
) -> tuple[list[RequestResult], float]:
    """Run n requests with a concurrency limit. Return results and wall time."""
    sem = asyncio.Semaphore(max(1, concurrency))
    timeout = kw.pop("timeout", None)
    to = httpx.Timeout(timeout or target.timeout_s, connect=15.0)
    async with httpx.AsyncClient(
            timeout=to,
            trust_env=_trust_env(target.base_url)) as client:
        async def one(i: int) -> RequestResult:
            async with sem:
                r = await run_chat(target, client=client, **kw)
                if on_progress:
                    on_progress(i, r)
                return r
        t0 = time.perf_counter()
        results = await asyncio.gather(*(one(i) for i in range(n)))
        wall = time.perf_counter() - t0
    return list(results), wall


async def chat_with_fallback(
    target: ModelTarget,
    *,
    prompt: str,
    stream: bool = True,
    max_tokens: int | None = 16,
    temperature: float | None = 0.0,
    timeout: float | None = None,
    include_usage: bool = True,
    client: httpx.AsyncClient | None = None,
    on_event=None,
) -> RequestResult:
    """run_chat plus retries for servers that reject some parameters.

    Some models (o-series, a few relays) reject temperature or max_tokens.
    Retry step by step: drop temperature, then drop max_tokens.
    """
    plans = [(temperature, max_tokens), (None, max_tokens), (None, None)]
    r = None
    for temp, mt in plans:
        r = await run_chat(target, prompt=prompt, stream=stream,
                           max_tokens=mt, temperature=temp, timeout=timeout,
                           include_usage=include_usage, client=client,
                           on_event=on_event)
        if r.ok or r.status != 400:
            break
        e = r.error.lower()
        if temp is not None and "temperature" in e:
            continue
        if mt is not None and ("max_tokens" in e
                               or "max_completion_tokens" in e):
            continue
        if ("unsupported" in e or "unknown" in e or "unrecognized" in e) \
                and (temp is not None or mt is not None):
            continue
        break
    return r


async def list_models(
    target: ModelTarget,
    timeout: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[int, list[str], str]:
    """GET {base_url}/models. Return (status, model ids, error text)."""
    url = target.base_url.rstrip("/") + "/models"
    hdrs = _headers(target)
    to = httpx.Timeout(timeout or target.timeout_s, connect=15.0)
    own = client is None
    if own:
        client = httpx.AsyncClient(
            timeout=to, trust_env=_trust_env(target.base_url))
    try:
        r = await client.get(url, headers=hdrs, timeout=to)
        if r.status_code != 200:
            return r.status_code, [], _http_err(r.status_code, r.text)
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else None
        ids = [str(m.get("id")) for m in (items or []) if m.get("id")]
        return 200, ids, ""
    except httpx.HTTPError as e:
        return 0, [], f"network: {type(e).__name__}: {e}"
    finally:
        if own:
            await client.aclose()
