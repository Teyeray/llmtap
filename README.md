# llmtap

终端大模型 API 测试器。测任何 OpenAI 兼容端点。一条命令得到开发者关心的全部性能数据。

[![python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![license](https://img.shields.io/badge/license-MIT-green)]()

## 功能

- 单请求测试:TTFT、首包延迟、总延迟、ITL(逐 token 间隔)。
- 吞吐统计:解码速度 tok/s、整体速度 tok/s、输入/输出 token 数。
- 压测模式:n 个请求、可设并发。输出 mean/p50/p95/min/max/stdev。
- 费用估算:配置单价表后自动计算单次与总费用。
- 多端点管理:TOML 配置多个 provider 与模型。一个 profile 可挂多个模型。
- TUI:表格展示所有模型的全部配置。可在线发起测试并实时看流式速度。
- 离线演示:内置假 OpenAI 服务器,无 key 也能跑通全部功能。

## 安装

要求 Python 3.10 或更高版本。

```bash
uv tool install llmtap        # 推荐
# 或
pipx install llmtap
pip install llmtap
```

仓库内开发:

```bash
git clone <this repo> && cd llmtap
uv venv && uv pip install -e .
uv run llmtap --help
```

## 快速开始:不写配置,直接测一个端点

```bash
# 测本地 Ollama
llmtap test --base-url http://127.0.0.1:11434/v1 --model qwen2.5:7b

# 测任意 OpenAI 兼容端点,key 放在环境变量里
export MY_KEY=sk-xxx
llmtap test --base-url https://api.deepseek.com/v1 --model deepseek-chat --api-key-env MY_KEY
```

## 配置文件

查找顺序:`--config` 参数、`$LLMTAP_CONFIG`、`./llmtap.toml`、`~/.config/llmtap/config.toml`。

完整示例见 [examples/config.toml](examples/config.toml)。核心结构:

```toml
[defaults]
prompt = "Count from 1 to 20 slowly."
max_tokens = 512
temperature = 0.7

[profiles.deepseek]                  # 一个端点
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"     # key 从这个环境变量读取
model = "deepseek-chat"              # 单模型

[profiles.kimi]                      # 一个端点挂多个模型
base_url = "https://api.moonshot.cn/v1"
api_key_env = "MOONSHOT_API_KEY"
models = ["kimi-k2-0905-preview", "moonshot-v1-8k"]

[pricing."deepseek-chat"]            # 可选:USD / 1M tokens
input = 0.27
output = 1.10
```

配置后,profile 名为 `deepseek` 和 `kimi/kimi-k2-0905-preview`、`kimi/moonshot-v1-8k`。

命令里可用前缀匹配唯一名,如 `llmtap test kimi/k2`。

## 命令

| 命令 | 作用 |
|---|---|
| `llmtap list` | 表格显示所有模型的所有配置 |
| `llmtap show <profile>` | 一个 profile 的完整配置 |
| `llmtap models <profile>` | 调 GET /models,列出端点上的模型 |
| `llmtap test <profile>` | 单请求。输出全部指标 + 响应预览 |
| `llmtap bench <profile> --n 10 -c 2` | 压测。输出 mean/p50/p95/min/max/stdev |
| `llmtap bench --all` | 压测全部 profile,输出对比表 |
| `llmtap tui` | 打开交互界面 |

常用选项:`-p` 换 prompt。`--max-tokens`、`--temperature` 覆盖配置。`--no-stream` 测非流式。`--full` 打印完整响应。

## 指标说明

| 指标 | 含义 |
|---|---|
| time to headers | 请求发出到收到响应头的耗时 |
| time to first chunk | 第一个 SSE 数据块的到达时间 |
| TTFT | 首个 token(含思考 token)到达时间。用户感知的等待 |
| ITL | 相邻两个 token 的间隔。p95 大说明输出卡顿 |
| decode speed | 首 token 之后的解码速度,tok/s |
| overall speed | 全程折算速度,tok/s |
| tokens in/out | 输入/输出 token 数。无 usage 时按块数估算,标注 estimated |
| cost | 按 pricing 配置估算的美元费用 |

## TUI

```bash
llmtap tui
```

上方表格列出所有模型的全部配置。选中一行后:

| 按键 | 作用 |
|---|---|
| `r` | 单请求测试,右侧实时显示 tok/s |
| `b` | 连续 5 次请求,右侧显示统计表 |
| `Enter` | 弹窗查看该模型完整配置 |
| `m` | 调 GET /models 列出端点模型 |
| `l` | 重新加载配置文件 |
| `q` | 退出 |

## 离线演示

不需要任何真实 key:

```bash
python scripts/fake_server.py &        # 起假端点,端口 8765
export LLMTAP_CONFIG=tests/local.toml
llmtap list
llmtap test local7b
llmtap bench local7b --n 5 -c 2
llmtap bench --all
llmtap tui
```

可用环境变量调延迟:`FAKE_TTFT_MS=200 FAKE_ITL_MS=30 python scripts/fake_server.py`。

## 运行测试

```bash
uv pip install -e . --group dev
pytest
```

## 与现有工具的差别

- token-speed-tester(npm):测速统计强。无 TUI,无多端点配置管理。
- llm-relay-tester:中转站可用性探测。无 TUI,无逐 token ITL。
- llmtap:CLI 统计 + TUI 全配置总览 + 多 provider 配置,三合一。

## License

MIT
