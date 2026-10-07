"""Lightweight i18n for llmtap. English and Chinese.

Language resolution order:
1. LLMTAP_LANG env var (en or zh)
2. system locale (zh* -> zh, else en)

Probe prompts stay English on purpose: they are test data, not UI text.
"""

from __future__ import annotations

import os

_LANG = "en"


def detect_lang() -> str:
    env = (os.environ.get("LLMTAP_LANG") or "").strip().lower()
    if env.startswith("zh"):
        return "zh"
    if env.startswith("en"):
        return "en"
    for probe in (os.environ.get("LC_ALL"), os.environ.get("LANG")):
        if probe and "zh" in probe.lower():
            return "zh"
    return "en"


def set_lang(lang: str) -> None:
    global _LANG
    _LANG = "zh" if lang.strip().lower().startswith("zh") else "en"


def get_lang() -> str:
    return _LANG


def toggle_lang() -> str:
    set_lang("en" if _LANG == "zh" else "zh")
    return _LANG


# key: (english, chinese)
CATALOG: dict[str, tuple[str, str]] = {
    # ---- config errors ----
    "err.config_not_found": (
        "no config file found. Create llmtap.toml here, or "
        "~/.config/llmtap/config.toml, or pass --config.",
        "未找到配置文件。请在当前目录创建 llmtap.toml,或 "
        "~/.config/llmtap/config.toml,或传入 --config。"),
    "err.config_path_missing": ("config file not found: {path}",
                                "配置文件不存在:{path}"),
    "err.env_config_missing": (
        "LLMTAP_CONFIG points to a missing file: {path}",
        "LLMTAP_CONFIG 指向的文件不存在:{path}"),
    "err.no_profiles": ("no [profiles.*] tables in {path}",
                        "{path} 中没有 [profiles.*] 表"),
    "err.profile_table": ("profile '{key}' must be a table",
                          "profile '{key}' 必须是表"),
    "err.profile_base_url": ("profile '{key}': base_url is required",
                             "profile '{key}':必须设置 base_url"),
    "err.profile_models_list": ("profile '{key}': 'models' must be a list",
                                "profile '{key}':'models' 必须是列表"),
    "err.profile_model_missing": ("profile '{key}': set 'model' or 'models'",
                                  "profile '{key}':需设置 model 或 models"),
    "err.profile_not_found": (
        "profile '{name}' not found. Available: {names}",
        "未找到 profile '{name}'。可用:{names}"),
    "err.profile_ambiguous": (
        "'{name}' matches several profiles: {names}",
        "'{name}' 匹配多个 profile:{names}"),
    # ---- cli ----
    "cli.config_error": ("config error: {msg}", "配置错误:{msg}"),
    "cli.need_profile": ("give PROFILE, or pass --base-url and --model",
                         "请给出 PROFILE,或同时传入 --base-url 和 --model"),
    "cli.flags_together": ("--base-url and --model must be used together",
                           "--base-url 和 --model 必须同时使用"),
    "cli.n_targets": ("{n} targets from {src}", "来自 {src} 的 {n} 个目标"),
    "cli.n_models": ("{n} models on {url} (HTTP {status})",
                     "{url} 上有 {n} 个模型(HTTP {status})"),
    "cli.probing": ("probing {name}", "正在检测 {name}"),
    "cli.scanning": ("scanning {host}", "正在扫描 {host}"),
    # ---- report: config table ----
    "report.configured_models": ("Configured models", "已配置的模型"),
    "col.profile": ("profile", "名称"),
    "col.model": ("model", "模型"),
    "col.base_url": ("base URL", "地址"),
    "col.api_key": ("API key", "密钥"),
    "col.temp": ("temp", "温度"),
    "col.max_tok": ("max tok", "最大 token"),
    "col.timeout": ("timeout (s)", "超时 (s)"),
    "col.price_in": ("$in/1M", "$入/1M"),
    "col.price_out": ("$out/1M", "$出/1M"),
    # ---- report: single request ----
    "report.single_title": ("{profile} — single request", "{profile} — 单请求"),
    "m.status": ("status", "状态"),
    "m.model_reported": ("model (reported)", "模型(服务端)"),
    "m.headers": ("time to headers", "响应头耗时"),
    "m.first_chunk": ("time to first chunk", "首块耗时"),
    "m.ttft": ("TTFT (first token)", "TTFT(首 token)"),
    "m.total": ("total time", "总耗时"),
    "m.itl_avg": ("ITL avg", "ITL 均值"),
    "m.input_tokens": ("input tokens", "输入 token"),
    "m.output_tokens": ("output tokens", "输出 token"),
    "m.decode": ("decode speed", "解码速度"),
    "m.overall": ("overall speed", "整体速度"),
    "m.finish": ("finish reason", "结束原因"),
    "m.reasoning": ("reasoning chars", "思考字数"),
    "m.cost": ("cost", "费用"),
    "n.first_token_ms": ("first token, ms", "首 token,毫秒"),
    "n.nonstream_na": ("non-stream: n/a", "非流式:不适用"),
    "n.decode": ("tok/s after first token", "首 token 后 tok/s"),
    "n.overall": ("tok/s over full request", "全程折算 tok/s"),
    "n.estimated": ("estimated", "估算值"),
    "n.from_usage": ("from usage", "来自 usage"),
    "n.ok": ("ok", "成功"),
    "n.failed": ("failed", "失败"),
    "report.response": ("response", "响应"),
    "report.error": ("error", "错误"),
    # ---- report: bench ----
    "report.bench_title": (
        "{profile} — {n} requests (concurrency {c}, {mode})",
        "{profile} — {n} 次请求(并发 {c},{mode})"),
    "report.mode_stream": ("stream", "流式"),
    "report.mode_nonstream": ("non-stream", "非流式"),
    "report.metric": ("metric", "指标"),
    "col.value": ("value", "值"),
    "col.note": ("note", "说明"),
    "b.ttft": ("TTFT (ms)", "TTFT (ms)"),
    "b.total": ("total (ms)", "总耗时 (ms)"),
    "b.itl": ("ITL (ms)", "ITL (ms)"),
    "b.decode": ("decode speed (tok/s)", "解码速度 (tok/s)"),
    "b.out_tokens": ("output tokens", "输出 token 数"),
    "b.ok_total": ("ok / total", "成功 / 总数"),
    "b.error_rate": ("error rate", "错误率"),
    "b.wall": ("wall time", "总耗时"),
    "b.throughput": ("throughput", "吞吐"),
    "b.tokens": ("tokens in/out", "输入/输出 token"),
    "b.cost": ("total cost", "总费用"),
    "report.errors": ("errors", "错误"),
    "report.comparison": ("Comparison", "对比"),
    "col.ok": ("ok", "成功"),
    "col.err_pct": ("err%", "错误%"),
    "col.ttft_p50": ("TTFT p50", "TTFT p50"),
    "col.total_p50": ("total p50", "总耗时 p50"),
    "col.tps_p50": ("tok/s p50", "tok/s p50"),
    "col.cost": ("cost", "费用"),
    "report.get_models": ("GET /models", "GET /models"),
    "col.model_id": ("model id", "模型 id"),
    "report.config_of": ("Config: {profile}", "配置:{profile}"),
    "report.source": ("source: {src}", "来源:{src}"),
    # ---- probe ----
    "probe.instruction": ("Instruction following", "指令遵循"),
    "probe.base64": ("Base64 decode", "Base64 解码"),
    "probe.needle": ("Needle in haystack", "长文本找验证码"),
    "probe.batball": ("Bat and ball", "球棒与球"),
    "probe.math": ("Multiplication 17x24", "乘法 17x24"),
    "probe.setlen": ("Set dedup", "集合去重"),
    "probe.title": ("{profile} — downgrade probe ({n} checks)",
                    "{profile} — 降智检测({n} 题)"),
    "col.check": ("check", "题目"),
    "col.weight": ("weight", "权重"),
    "col.result": ("result", "结果"),
    "col.latency": ("latency", "耗时"),
    "col.expected": ("expected", "期望"),
    "col.got": ("got (first 80 chars)", "回答(前 80 字符)"),
    "probe.pass": ("pass", "通过"),
    "probe.fail": ("fail", "未通过"),
    "probe.err": ("ERR", "错误"),
    "probe.score": ("score:  {score} / {total}", "得分:{score} / {total}"),
    "probe.verdict": ("verdict:  {verdict}", "结论:{verdict}"),
    "probe.model_reported": ("model reported by server:  {model}",
                             "服务端报告的模型:{model}"),
    "probe.errors": ("errors:  {errors}", "错误:{errors}"),
    "probe.v.ok": ("pass: no obvious downgrade", "通过:无明显降智"),
    "probe.v.partial": ("suspect: some checks failed", "可疑:部分题目未通过"),
    "probe.v.fail": ("fail: strong signs of downgrade", "失败:明显降智迹象"),
    "probe.v.inconclusive": ("inconclusive: requests failed",
                             "无法判定:存在请求失败"),
    # ---- scan ----
    "scan.title": ("scan {host} — {n} of {m} listed models",
                   "扫描 {host} — 共 {m} 个模型,测试 {n} 个"),
    "scan.fetch_failed": ("GET /models failed [{status}]: {error}",
                          "GET /models 失败 [{status}]:{error}"),
    "col.status": ("status", "状态"),
    "col.ttft": ("TTFT", "TTFT"),
    "col.error": ("error", "错误"),
    "col.tps": ("tok/s", "tok/s"),
    "col.out_tok": ("out tok", "输出 token"),
    "scan.ok": ("ok", "存活"),
    "scan.fail": ("fail", "失败"),
    "scan.alive": ("alive: {ok}/{n}", "存活:{ok}/{n}"),
    "scan.ttft_summary": ("TTFT p50/p95:  {p50} / {p95} ms",
                          "TTFT p50/p95:{p50} / {p95} ms"),
    "scan.dead": ("dead:  {models}", "失败:{models}"),
    # ---- tui ----
    "tui.subtitle": ("r test · b bench · p probe · s scan · enter details "
                     "· m models · l reload · t lang",
                     "r 测试 · b 压测 · p 降智 · s 扫描 · enter 详情 "
                     "· m 模型 · l 重载 · t 语言"),
    "tui.loaded": ("loaded {n} targets from {src}",
                   "已从 {src} 加载 {n} 个目标"),
    "tui.config_error": ("config error: {msg}", "配置错误:{msg}"),
    "tui.testing": ("testing {name}", "正在测试 {name}"),
    "tui.waiting": ("waiting for tokens", "等待 token 输出"),
    "tui.benching": ("bench {name} x{n}", "压测 {name} x{n}"),
    "tui.bench_done": ("{name} bench done: {ok}/{n} ok",
                       "{name} 压测完成:{ok}/{n} 成功"),
    "tui.probing": ("probing {name}", "正在降智检测 {name}"),
    "tui.probe_running": ("running 6 checks", "正在执行 6 道题目"),
    "tui.probe_done": ("{name} probe: score {score}/100, {verdict}",
                       "{name} 降智检测:得分 {score}/100,{verdict}"),
    "tui.scanning": ("scanning {host}", "正在扫描 {host}"),
    "tui.listing": ("listing models", "正在获取模型列表"),
    "tui.scan_done": ("{host} scan: {ok}/{n} alive",
                      "{host} 扫描:{ok}/{n} 存活"),
    "tui.getting_models": ("GET /models on {host}",
                           "正在请求 {host} 的 /models"),
    "tui.models_done": ("{host}: {n} models", "{host}:共 {n} 个模型"),
    "tui.lang_switched": ("language: {lang}", "语言已切换:{lang}"),
    "lang.en": ("English", "英文"),
    "lang.zh": ("Chinese", "中文"),
}


def t(key: str, **kw) -> str:
    """Translate a key with the current language."""
    entry = CATALOG.get(key)
    s = (entry[1] if _LANG == "zh" else entry[0]) if entry else key
    return s.format(**kw) if kw else s


set_lang(detect_lang())
