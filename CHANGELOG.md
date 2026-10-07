# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - 2026-10-07

### Added
- Language switching: English and Chinese UI, `LLMTAP_LANG` env var,
  `t` key in the TUI. Auto-detect from the system locale.
- CI workflow (Linux, macOS, Windows; Python 3.10-3.14).
- README in English and Chinese, with generated SVG screenshots.
- CONTRIBUTING and CHANGELOG.

### Changed
- Probe questions are now all English, so results are comparable
  across models and regions.

## [0.2.0] - 2026-10-07

### Added
- `llmtap probe`: downgrade detection with 6 fixed checks,
  regex-scored, no judge model, `--strict` for CI.
- `llmtap scan`: relay scan, discovers all models via `GET /models`
  and tests each for status, TTFT and tok/s.
- Parameter fallback for endpoints that reject `temperature` or
  `max_tokens` (o-series style models).
- Loopback endpoints bypass the system proxy automatically.

## [0.1.0] - 2026-10-07

### Added
- Core: OpenAI-compatible client with SSE timing, TTFT, ITL,
  decode speed, usage tokens.
- CLI: `list`, `show`, `models`, `test`, `bench`, `tui`.
- Textual TUI with full config table and live stats.
- TOML config with multi-provider profiles and optional pricing.
- Fake OpenAI server and offline smoke tests.
