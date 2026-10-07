"""Config file loading and model target expansion.

A config file (TOML) holds defaults, profiles and pricing.
One profile can hold one model ("model") or many models ("models").
Each model expands into one ModelTarget. All commands use ModelTarget.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

DEFAULT_PROMPT = (
    "Count from 1 to 20, one number per line. "
    "Then write one short sentence about the sea."
)


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
            raise ConfigError(f"config file not found: {p}")
        return p
    env = os.environ.get("LLMTAP_CONFIG")
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            raise ConfigError(f"LLMTAP_CONFIG points to a missing file: {p}")
        return p
    for cand in (Path("llmtap.toml"),
                 Path.home() / ".config" / "llmtap" / "config.toml"):
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
        raise ConfigError(
            "no config file found. Create llmtap.toml in the current "
            "directory, or ~/.config/llmtap/config.toml, or pass --config."
        )
    data = tomllib.loads(path.read_text("utf-8"))
    defaults: dict = data.get("defaults") or {}
    pricing: dict = data.get("pricing") or {}
    profiles: dict = data.get("profiles") or {}
    if not profiles:
        raise ConfigError(f"no [profiles.*] tables in {path}")

    targets: list[ModelTarget] = []
    for key, prof in profiles.items():
        if not isinstance(prof, dict):
            raise ConfigError(f"profile '{key}' must be a table")
        base_url = prof.get("base_url")
        if not base_url:
            raise ConfigError(f"profile '{key}': base_url is required")
        if "models" in prof:
            models = prof["models"]
            if not isinstance(models, list) or not models:
                raise ConfigError(f"profile '{key}': 'models' must be a list")
        elif "model" in prof:
            models = [prof["model"]]
        else:
            raise ConfigError(f"profile '{key}': set 'model' or 'models'")

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
            ))
    return targets


def adhoc_target(base_url: str, model: str, api_key_env: str = "",
                 prompt: str | None = None) -> ModelTarget:
    """Build a target from CLI flags, without a config file."""
    api_key = os.environ.get(api_key_env, "") if api_key_env else ""
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
    for t in targets:
        if t.profile == name:
            return t
    prefix_hits = [t for t in targets if t.profile.startswith(name)]
    if len(prefix_hits) == 1:
        return prefix_hits[0]
    if len(prefix_hits) > 1:
        names = ", ".join(t.profile for t in prefix_hits)
        raise ConfigError(f"'{name}' matches several profiles: {names}")
    available = ", ".join(t.profile for t in targets)
    raise ConfigError(f"profile '{name}' not found. Available: {available}")
