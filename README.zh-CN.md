# llmtap

**终端大模型 API 测试器。** 测 TTFT、吞吐、token 统计。检测模型降智。扫描中转站。一个工具,测任何 OpenAI 兼容端点。

[![CI](https://github.com/USERNAME/llmtap/actions/workflows/ci.yml/badge.svg)](https://github.com/USERNAME/llmtap/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/llmtap)](https://pypi.org/project/llmtap/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green)]()
[![English](https://img.shields.io/badge/README-English-blue)](README.md)

![TUI](docs/img/tui.svg)

## 为什么做这个

你在中转站付费使用旗舰模型。中转站真的在跑这个模型吗?速度如何?手里五个 key 哪个 TTFT 最好?`llmtap` 在终端里回答这些问题。不需要控制台,不需要注册,数据不出本机。

## 功能

- **延迟测试**:TTFT、首包延迟、总耗时、逐 token 间隔 ITL(p50/p95)。
- **吞吐统计**:解码速度 tok/s、整体速度、输入/输出 token,优先取 usage。
- **压测**:N 个请求,可设并发。输出 mean/p50/p95/min/max/stdev。
- **降智检测**:6 道固定英文题,规则判分,不用裁判模型。总分 0-100。
- **中转站扫描**:GET /models 发现全部模型,逐个测状态与 TTFT。
- **费用估算**:配置单价表后,自动算单次与总费用。
- **TUI**:一张表看所有模型全部配置,流式时实时 tok/s,统计面板。
- **中英双语**:TUI 按 `t` 切换,CLI 用 `LLMTAP_LANG`。
- **广泛兼容**:OpenAI、DeepSeek、Moonshot、Qwen、OpenRouter、Ollama、LM Studio、vLLM、任意中转。

## 安装

要求 Python 3.10 或更高。

```bash
uv tool install llmtap   # 推荐
# 或
pipx install llmtap
pip install llmtap
```

源码安装:

```bash
git clone https://github.com/USERNAME/llmtap && cd llmtap
uv venv && uv pip install -e .
uv run llmtap --help
```

## 快速开始:不写配置

```bash
# 本地 Ollama
llmtap test --base-url http://127.0.0.1:11434/v1 --model qwen2.5:7b

# 任意 OpenAI 兼容端点,key 放环境变量
export MY_KEY=sk-xxx
llmtap test --base-url https://api.deepseek.com/v1 --model deepseek-chat \
    --api-key-env MY_KEY
```

![llmtap test](docs/img/test.svg)

## 配置文件

查找顺序:`--config`、`$LLMTAP_CONFIG`、`./llmtap.toml`、`~/.config/llmtap/config.toml`。完整示例:[examples/config.toml](examples/config.toml)。

```toml
[defaults]
prompt = "Count from 1 to 20 slowly."
max_tokens = 512
temperature = 0.7

[profiles.deepseek]                # 一个端点,一个模型
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"
model = "deepseek-chat"

[profiles.kimi]                    # 一个端点,多个模型
base_url = "https://api.moonshot.cn/v1"
api_key_env = "MOONSHOT_API_KEY"
models = ["kimi-k2-0905-preview", "moonshot-v1-8k"]

[pricing."deepseek-chat"]          # 可选:USD / 1M tokens
input = 0.27
output = 1.10
```

配置 `models` 后,profile 展开为 `kimi/kimi-k2-0905-preview` 等。命令行支持唯一前缀:`llmtap test kimi/k2`。

![llmtap list](docs/img/list.svg)

## 命令

| 命令 | 作用 |
|---|---|
| `llmtap list` | 表格显示所有模型的全部配置 |
| `llmtap show PROFILE` | 一个 profile 的完整配置 |
| `llmtap models PROFILE` | 调 GET /models,列出端点模型 |
| `llmtap test PROFILE` | 单请求,全部指标,响应预览 |
| `llmtap bench PROFILE --n 10 -c 2` | 压测,完整统计 |
| `llmtap bench --all` | 压测全部 profile,输出对比表 |
| `llmtap probe PROFILE` | 降智检测,6 题,总分 0-100 |
| `llmtap scan PROFILE` | 扫描端点上全部模型 |
| `llmtap tui` | 交互界面 |

常用选项:`-p` 换 prompt,`--max-tokens`,`--temperature`,`--no-stream`,`--full`。

![llmtap bench](docs/img/bench.svg)

## 指标说明

| 指标 | 含义 |
|---|---|
| time to headers | 请求发出到收到响应头 |
| time to first chunk | 第一个 SSE 数据块 |
| TTFT | 首 token 到达(含思考)。用户等待的时间 |
| ITL | 相邻 token 间隔。p95 大说明输出卡顿 |
| decode speed | 首 token 后的解码速度 tok/s |
| overall speed | 全程折算 tok/s |
| tokens in/out | 有 usage 用 usage,否则按块数估算并标注 |
| cost | 按可选单价表估算 |

## 降智检测原理

6 道固定英文题,每题有唯一可验证答案。不用裁判模型,答案用字符串与正则规则判分。temperature=0,非流式,max_tokens 固定,保证可复现。

| 题目 | 权重 | 通过规则 |
|---|---|---|
| 指令遵循(只回 APPLE) | 10 | 清理后等于 APPLE |
| Base64 解码 | 15 | 包含解码结果 |
| 长文本找四位验证码 | 20 | 包含验证码 |
| 球棒与球(1.10 美元陷阱) | 15 | 0.05 或 5 cents |
| 乘法 17×24 | 20 | 精确等于 408 |
| 集合去重 [1,1,2,3,3,3] | 20 | 精确等于 3 |

总分 85 以上判通过,60-84 判可疑,60 以下判明显降智。任何请求失败(401/429/5xx/超时)判"无法判定",不给分。`--strict` 低于 85 时退出码为 1,可接入 CI。

诚实说明:题目不难,便宜小模型也可能全对。通过只说明"无明显降智",不证明就是旗舰模型。

![llmtap probe](docs/img/probe.svg)

## 中转站扫描原理

GET /models 拿到端点全部模型 id。每个模型发一条最小流式请求(固定 prompt,max_tokens=16)。记录状态、TTFT、总耗时、tok/s、错误。汇总输出:存活数、TTFT p50/p95、死亡模型清单。`--only` 按子串过滤,`--limit` 限制数量,`-c` 控制并发。端点拒绝 temperature 或 max_tokens 时(o 系列)自动用默认参数重试。

![llmtap scan](docs/img/scan.svg)

## TUI

```bash
llmtap tui
```

| 按键 | 作用 |
|---|---|
| `r` | 单请求测试,右侧实时 tok/s |
| `b` | 连测 5 次,统计表 |
| `p` | 降智检测 |
| `s` | 扫描端点全部模型 |
| `Enter` | 完整配置弹窗 |
| `m` | 列出端点模型 |
| `l` | 重载配置 |
| `t` | 切换语言(中/英) |
| `q` | 退出 |

## 语言

默认英文。系统语言为中文时自动切换中文。

```bash
export LLMTAP_LANG=zh   # 或 en
```

CLI 的 `--help` 保持英文。全部表格、结论、TUI 文案随语言切换。

## 离线演示

不需要任何 key:

```bash
python scripts/fake_server.py &
export LLMTAP_CONFIG=tests/local.toml
llmtap list
llmtap test local7b
llmtap bench local7b --n 5 -c 2
llmtap probe local7b
llmtap scan local7b
llmtap tui
```

用 `FAKE_TTFT_MS=200 FAKE_ITL_MS=30 python scripts/fake_server.py` 调整模拟延迟。

## 与现有工具对比

| 工具 | 性能统计 | 降智检测 | 中转扫描 | TUI | 多端点配置 |
|---|---|---|---|---|---|
| llmtap | 有 | 有 | 有 | 有 | 有 |
| token-speed-tester | 有 | 无 | 无 | 无 | 无 |
| llm-relay-tester | 部分 | 无 | 有 | 无 | 部分 |
| llmprobe | 无 | 有 | 无 | 无 | 无 |

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。欢迎提 bug 和新题目。

## License

MIT
