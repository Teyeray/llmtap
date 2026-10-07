"""Config file loading and model target expansion.

A config file (TOML) holds defaults, profiles and pricing.
One profile can hold one model ("model") or many models ("models").
Each model expands into one ModelTarget. All commands use ModelTarget.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

from .i18n import t

DEFAULT_PROMPT = (
    "Count from 1 to 20, one number per line. "
    "Then write one short sentence about the sea."
)

USER_CONFIG_PATH = Path.home() / ".config" / "llmtap" / "config.toml"

CONFIG_TEMPLATE = '''# llmtap config. Docs: https://github.com/Teyeray/llmtap
# Add a profile without editing this file:
#   llmtap add myrelay -u https://host/v1 -k sk-xxx

[defaults]
prompt = "Count from 1 to 20, one number per line. Then write one short sentence about the sea."
max_tokens = 512
temperature = 0.7
timeout = 120
# profile = "ollama"        # used when you omit PROFILE on the command line

[profiles.ollama]
base_url = "http://127.0.0.1:11434/v1"
model = "qwen2.5:7b"
max_tokens = 256

# [profiles.deepseek]
# base_url = "https://api.deepseek.com/v1"
# api_key_env = "DEEPSEEK_API_KEY"   # key read from this env var
# model = "deepseek-chat"

# [profiles.kimi]                    # one endpoint, several models
# base_url = "https://api.moonshot.cn/v1"
# api_key_env = "MOONSHOT_API_KEY"
# models = ["kimi-k2-0905-preview", "moonshot-v1-8k"]

# [pricing."deepseek-chat"]          # optional, USD per 1M tokens
# input = 0.27
# output = 1.10
'''


class ConfigError(Exception):
    """Raised when the config file is missing or invalid."""


@dataclass
class ModelTarget:
    """One testable endpoint plus one model, with all settings."""

    profile: str
    model: str
    base_url: str
    api_key: str = ""
    api_key_env: str = ""
    headers: dict = field(default_factory=dict)
    temperature: float | None = None
    max_tokens: int | None = None
    prompt: str = DEFAULT_PROMPT
    timeout_s: float = 120.0
    price_in: float | None = None   # USD per 1M input tokens
    price_out: float | None = None  # USD per 1M output tokens
    source: str = ""                # config path or "adhoc"
    default: bool = False           # [defaults].profile points here

    @property
    def key_display(self) -> str:
        if self.api_key_env:
            state = "set" if os.environ.get(self.api_key_env) else "unset"
            return f"env:{self.api_key_env}({state})"
        if self.api_key:
            return "inline"
        return "none"

    @property
    def host(self) -> str:
        s = self.base_url.split("://", 1)[-1]
        return s.split("/", 1)[0]

    def safe_dict(self) -> dict:
        """Config as a dict, with the API key value removed."""
        d = asdict(self)
        d.pop("api_key", None)
        d["api_key"] = self.key_display
        return d


def find_config(explicit: str | None = None) -> Path | None:
    """Find the config file. Explicit path wins, then env var, then defaults."""
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise ConfigError(t("err.config_path_missing", path=p))
        return p
    env = os.environ.get("LLMTAP_CONFIG")
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            raise ConfigError(t("err.env_config_missing", path=p))
        return p
    for cand in (Path("llmtap.toml"), USER_CONFIG_PATH):
        if cand.is_file():
            return cand
    return None


def _match_price(model: str, pricing: dict) -> tuple[float | None, float | None]:
    """Return (input, output) price. Exact match first, then longest substring."""
    if not pricing:
        return None, None
    entry = pricing.get(model)
    if entry is None:
        best = None
        for key in pricing:
            if key in model and (best is None or len(key) > len(best)):
                best = key
        entry = pricing.get(best) if best else None
    if not entry:
        return None, None
    pin = entry.get("input")
    pout = entry.get("output")
    return (
        float(pin) if pin is not None else None,
        float(pout) if pout is not None else None,
    )


def load_targets(explicit: str | None = None) -> list[ModelTarget]:
    """Load the config file and expand profiles into ModelTarget objects."""
    path = find_config(explicit)
    if path is None:
        raise ConfigError(t("err.config_not_found"))
    data = tomllib.loads(path.read_text("utf-8"))
    defaults: dict = data.get("defaults") or {}
    pricing: dict = data.get("pricing") or {}
    profiles: dict = data.get("profiles") or {}
    if not profiles:
        raise ConfigError(t("err.no_profiles", path=path))
    default_name = str(defaults.get("profile") or "")

    targets: list[ModelTarget] = []
    for key, prof in profiles.items():
        if not isinstance(prof, dict):
            raise ConfigError(t("err.profile_table", key=key))
        base_url = prof.get("base_url")
        if not base_url:
            raise ConfigError(t("err.profile_base_url", key=key))
        if "models" in prof:
            models = prof["models"]
            if not isinstance(models, list) or not models:
                raise ConfigError(t("err.profile_models_list", key=key))
        elif "model" in prof:
            models = [prof["model"]]
        else:
            raise ConfigError(t("err.profile_model_missing", key=key))

        env_name = prof.get("api_key_env") or defaults.get("api_key_env") or ""
        api_key = os.environ.get(env_name, "") if env_name else ""
        if not api_key:
            api_key = prof.get("api_key") or defaults.get("api_key") or ""

        for m in models:
            name = f"{key}/{m}" if "models" in prof else key
            pin, pout = _match_price(m, pricing)
            targets.append(ModelTarget(
                profile=name,
                model=m,
                base_url=str(base_url),
                api_key=api_key,
                api_key_env=str(env_name),
                headers=dict(prof.get("headers") or {}),
                temperature=prof.get("temperature", defaults.get("temperature")),
                max_tokens=prof.get("max_tokens", defaults.get("max_tokens")),
                prompt=prof.get("prompt", defaults.get("prompt", DEFAULT_PROMPT)),
                timeout_s=float(prof.get("timeout", defaults.get("timeout", 120.0))),
                price_in=pin,
                price_out=pout,
                source=str(path),
                default=bool(default_name) and default_name in (key, name),
            ))
    return targets


def adhoc_target(base_url: str, model: str, api_key_env: str = "",
                 prompt: str | None = None, api_key: str = "") -> ModelTarget:
    """Build a target from CLI flags, without a config file."""
    if not api_key and api_key_env:
        api_key = os.environ.get(api_key_env, "")
    return ModelTarget(
        profile="adhoc",
        model=model,
        base_url=base_url,
        api_key=api_key,
        api_key_env=api_key_env,
        prompt=prompt or DEFAULT_PROMPT,
        source="adhoc",
    )


def pick_target(targets: list[ModelTarget], name: str) -> ModelTarget:
    """Find a target by exact profile name, or by a unique name prefix."""
    for target in targets:
        if target.profile == name:
            return target
    prefix_hits = [x for x in targets if x.profile.startswith(name)]
    if len(prefix_hits) == 1:
        return prefix_hits[0]
    if len(prefix_hits) > 1:
        names = ", ".join(x.profile for x in prefix_hits)
        raise ConfigError(t("err.profile_ambiguous", name=name, names=names))
    available = ", ".join(x.profile for x in targets)
    raise ConfigError(t("err.profile_not_found", name=name,
                        names=available))


# ---- writing config -------------------------------------------------------

def write_template(path: Path, force: bool = False) -> bool:
    """Create a starter config. Return False when the file already exists."""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    return True


def _toml_key(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else f'"{name}"'


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def append_profile(path: Path, name: str, base_url: str, models: list[str],
                   api_key_env: str = "", api_key: str = "") -> None:
    """Append one [profiles.name] table. Create the file when missing."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[defaults]\nmax_tokens = 512\ntimeout = 120\n",
                        encoding="utf-8")
    data = tomllib.loads(path.read_text("utf-8"))
    if name in (data.get("profiles") or {}):
        raise ConfigError(t("err.profile_exists", name=name, path=path))
    lines = [f"\n[profiles.{_toml_key(name)}]",
             f"base_url = {_toml_str(base_url)}"]
    if api_key_env:
        lines.append(f"api_key_env = {_toml_str(api_key_env)}")
    elif api_key:
        lines.append(f"api_key = {_toml_str(api_key)}")
    if len(models) == 1:
        lines.append(f"model = {_toml_str(models[0])}")
    else:
        lines.append("models = [" + ", ".join(_toml_str(m) for m in models)
                     + "]")
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
