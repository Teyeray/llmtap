<p align="center">
  <img src="docs/img/banner.png" alt="llmtap" width="760">
</p>

<p align="center">
  <b>Terminal tester for LLM APIs.</b><br>
  Measure TTFT and throughput. Probe for model downgrade. Scan relay stations.<br>
  One tool, any OpenAI-compatible endpoint.
</p>

<p align="center">
  <a href="https://github.com/Teyeray/llmtap/actions/workflows/ci.yml"><img src="https://github.com/Teyeray/llmtap/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/llmtap/"><img src="https://img.shields.io/pypi/v/llmtap.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/llmtap/"><img src="https://img.shields.io/pypi/pyversions/llmtap.svg" alt="Python"></a>
  <a href="https://pepy.tech/project/llmtap"><img src="https://static.pepy.tech/badge/llmtap/month" alt="Downloads"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License"></a>
  <a href="README.zh-CN.md"><img src="https://img.shields.io/badge/文档-中文-red.svg" alt="中文"></a>
</p>

<p align="center">
  <img src="docs/img/demo.gif" alt="llmtap demo" width="860">
</p>

<p align="center"><sub>Recorded against the bundled fake server. No API key needed: <code>llmtap scan local7b</code></sub></p>

---

## Why

You pay for a flagship model on a relay. Is the relay really serving that model? How fast is it tonight? Which of your five API keys has the best TTFT?

`llmtap` answers these from the terminal. No dashboard, no signup, no data leaves your machine. Point it at OpenAI, DeepSeek, Moonshot, Qwen, OpenRouter, Ollama, LM Studio, vLLM, or any relay that speaks the OpenAI API.

## Features

- **Latency** — TTFT, time to first chunk, total time, inter-token latency with p50/p95.
- **Throughput** — decode speed (tok/s), overall speed, input/output tokens, straight from `usage`.
- **Bench** — N requests with configurable concurrency. Mean / p50 / p95 / min / max / stdev.
- **Downgrade probe** — 6 fixed checks, regex-scored, no judge model. Score 0–100.
- **Relay scan** — discover every model on an endpoint via `GET /models`, test each one.
- **Cost** — optional per-model pricing, cost per request and per run.
- **TUI** — every model and every setting in one table, live tok/s while streaming.
- **Bilingual** — English and Chinese UI, `--help` included. Switch with `t` in the TUI or `LLMTAP_LANG`.

## Install

Python 3.10 or newer.

```bash
uv tool install llmtap   # recommended
# or
pipx install llmtap
pip install llmtap
```

From source:

```bash
git clone https://github.com/Teyeray/llmtap && cd llmtap
uv venv && uv pip install -e .
uv run llmtap --help
```

## Quick start

A bare URL works as the first argument. No config file needed.

```bash
llmtap test https://api.deepseek.com/v1 -k sk-xxx -m deepseek-chat   # one request
llmtap test https://api.deepseek.com/v1 -k sk-xxx                    # picks a model
llmtap scan https://some-relay.com/v1 -k sk-xxx                      # scan every model
llmtap test http://127.0.0.1:11434/v1 -m qwen2.5:7b                  # local Ollama
```

`-m` is optional. When you omit it, llmtap lists the endpoint models and asks you to pick one. Keys come from `-k`, `--api-key-env NAME`, `$LLMTAP_API_KEY`, or `$OPENAI_API_KEY`.

Save an endpoint for later, without editing TOML:

```bash
llmtap init          # create ~/.config/llmtap/config.toml
llmtap add deepseek -u https://api.deepseek.com/v1 -k sk-xxx
llmtap test deepseek
```

<p align="center"><img src="docs/img/test.png" alt="llmtap test" width="900"></p>

## Config

Search order: `--config`, `$LLMTAP_CONFIG`, `./llmtap.toml`, `~/.config/llmtap/config.toml`. Full example: [examples/config.toml](examples/config.toml).

```toml
[defaults]
prompt = "Count from 1 to 20 slowly."
max_tokens = 512
temperature = 0.7
profile = "deepseek"               # used when PROFILE is omitted

[profiles.deepseek]                # one endpoint, one model
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"
model = "deepseek-chat"

[profiles.kimi]                    # one endpoint, several models
base_url = "https://api.moonshot.cn/v1"
api_key_env = "MOONSHOT_API_KEY"
models = ["kimi-k2-0905-preview", "moonshot-v1-8k"]

[pricing."deepseek-chat"]          # optional, USD per 1M tokens
input = 0.27
output = 1.10
```

With `models`, a profile expands to `kimi/kimi-k2-0905-preview` and so on. Unique prefixes work on the command line: `llmtap test kimi/k2`. When you omit PROFILE, llmtap uses the only profile, else the `[defaults] profile` entry, else it asks.

<p align="center"><img src="docs/img/list.png" alt="llmtap list" width="900"></p>

## Commands

| Command | What it does |
|---|---|
| `llmtap` | open the TUI (shows help when no config exists) |
| `llmtap init` | create `~/.config/llmtap/config.toml` |
| `llmtap add NAME -u URL [-k KEY] [-m MODEL]` | append a profile to the config |
| `llmtap list` | table of every configured model with every setting |
| `llmtap show PROFILE` | full config of one profile |
| `llmtap models PROFILE` | call `GET /models`, list endpoint model ids |
| `llmtap test PROFILE` | one request, all metrics, response preview |
| `llmtap bench PROFILE -n 10 -c 2` | load bench with full statistics |
| `llmtap bench --all` | bench every profile, comparison table |
| `llmtap probe PROFILE` | downgrade probe, 6 checks, score 0–100 |
| `llmtap scan PROFILE` | scan every model on the endpoint |
| `llmtap tui` | interactive TUI |

PROFILE is a profile name, a unique prefix, or a bare URL. Common options: `-u` URL, `-m` model, `-k` key, `-p` prompt, `--max-tokens`, `--temperature`, `--no-stream`, `--full`.

<p align="center"><img src="docs/img/bench.png" alt="llmtap bench" width="900"></p>

## Metrics

| Metric | Meaning |
|---|---|
| time to headers | request sent to response headers received |
| time to first chunk | first SSE data chunk |
| TTFT | first token (content or reasoning). What the user waits for |
| ITL | gap between two tokens. A high p95 means stutter |
| decode speed | tok/s after the first token |
| overall speed | tok/s over the whole request |
| tokens in/out | from `usage` when present, else estimated (marked as such) |
| cost | from the optional pricing table |

## Probe: is this really the model I paid for?

Six fixed English questions, each with exactly one checkable answer. Answers are matched by string and regex rules, so no judge model is needed. `temperature=0`, non-stream, fixed `max_tokens`: runs stay comparable.

| Check | Weight | Pass rule |
|---|---|---|
| Instruction following (reply only APPLE) | 10 | equals `APPLE` after cleanup |
| Base64 decode | 15 | contains the decoded text |
| Needle in haystack (4-digit code in filler) | 20 | contains the code |
| Bat and ball (the $1.10 trap) | 15 | `0.05` or `5 cents` |
| Multiplication 17 × 24 | 20 | exactly `408` |
| Set dedup `[1,1,2,3,3,3]` | 20 | exactly `3` |

Score 85+ = pass, 60–84 = suspect, below 60 = strong signs of downgrade. Any request failure (401/429/5xx/timeout) marks the run inconclusive and it is not scored. `--strict` exits 1 below 85, for CI.

Honest limitation: the checks are easy. Any cheap model can pass them all. A pass means "no obvious downgrade", not "this really is the flagship model".

<p align="center"><img src="docs/img/probe.png" alt="llmtap probe" width="900"></p>

## Scan: what is actually on this endpoint?

`GET /models` lists every model id. Each model then gets one minimal streaming request (fixed prompt, `max_tokens=16`). The scan records status, TTFT, total time, tok/s and errors. Output: alive count, TTFT p50/p95, dead model list.

Use `--only` to filter by substring, `--limit` to cap the count, `-c` for concurrency. Endpoints that reject `temperature` or `max_tokens` (o-series style) are retried with defaults.

<p align="center"><img src="docs/img/scan.png" alt="llmtap scan" width="900"></p>

## TUI

```bash
llmtap
```

<p align="center"><img src="docs/img/tui.png" alt="llmtap TUI" width="980"></p>

| Key | Action |
|---|---|
| `r` | single test, live tok/s on the right |
| `b` | bench ×5, stats table |
| `p` | downgrade probe |
| `s` | scan every model on the endpoint |
| `Enter` | full config popup |
| `m` | list endpoint models |
| `?` | full key guide |
| `l` | reload config |
| `t` | switch language (English / Chinese) |
| `q` | quit |

## Language

English by default. Chinese when the system locale is Chinese.

```bash
export LLMTAP_LANG=zh   # or en
```

Tables, verdicts, the TUI and the `--help` output all follow the setting.

## Try it offline

No API key, no network:

```bash
python scripts/fake_server.py &
export LLMTAP_CONFIG=tests/local.toml
llmtap list
llmtap test local7b
llmtap bench local7b -n 5 -c 2
llmtap probe local7b
llmtap scan local7b
llmtap
```

Shape the fake latency with `FAKE_TTFT_MS=200 FAKE_ITL_MS=30 python scripts/fake_server.py`.

## How it compares

| Tool | Perf stats | Downgrade probe | Relay scan | TUI | Multi-endpoint config |
|---|---|---|---|---|---|
| **llmtap** | ✅ | ✅ | ✅ | ✅ | ✅ |
| [token-speed-tester](https://github.com/Cansiny0320/token-speed-tester) | ✅ | ❌ | ❌ | ❌ | ❌ |
| [llm-relay-tester](https://github.com/WJAnnie/llm-relay-tester) | partial | ❌ | ✅ | ❌ | partial |
| [cocodot-llmprobe](https://github.com/cocodot2026/cocodot-llmprobe) | ❌ | ✅ | ❌ | ❌ | ❌ |
| [LMeterX](https://github.com/MigoXLab/LMeterX) | ✅ | ❌ | ❌ | ❌ | ✅ |

## Contributing

Bug reports, new probe checks and translations are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
uv venv && uv pip install -e . --group dev
uv run pytest -q          # runs against a local fake server, no key needed
uv run python scripts/make_docs.py   # regenerate docs/img
```

## Star history

<a href="https://star-history.com/#Teyeray/llmtap&Date">
  <img src="https://api.star-history.com/svg?repos=Teyeray/llmtap&type=Date" alt="Star history" width="700">
</a>

## License

MIT © 2026 llmtap contributors
