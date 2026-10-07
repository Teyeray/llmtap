# Contributing

Thanks for your interest in llmtap.

## Dev setup

```bash
git clone https://github.com/USERNAME/llmtap && cd llmtap
uv venv && uv pip install -e . --group dev
uv run pytest -q
```

Tests run against a local fake OpenAI server, so no API key is needed.

## Adding a probe check

1. Open `llmtap/probe.py`.
2. Add a matcher function. It must be pure and deterministic.
3. Add an entry to `CHECKS` with an English prompt, a weight, and an `expect` string.
4. Keep the sum of all weights at 100.
5. Add the name to the i18n catalog in `llmtap/i18n.py` (English and Chinese).
6. Add a matcher test in `tests/test_smoke.py`.

The check must have exactly one checkable answer. No judge model.

## Adding UI text

All user-visible text goes through `llmtap/i18n.py`. Add the key with an
English and a Chinese string. Never hardcode text in tables or logs.

## Screenshots

Regenerate the README images with:

```bash
python scripts/fake_server.py &
python scripts/make_docs.py
```

## Commits

Imperative subject line. One sentence per body line. Keep it short.

## Reporting a relay/model bug

Include: the `llmtap probe` or `llmtap scan` output, your config with the
API key removed, and the endpoint base URL if it is public.
