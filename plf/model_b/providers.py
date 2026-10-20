"""Provider registry for Model B.

Every provider speaks one of three wire protocols:

- ``openai``    — OpenAI-compatible ``POST {base_url}/chat/completions`` with a
                  Bearer key. Covers openai, together, openrouter, deepseek,
                  xai, mistral, ollama (local, no key) and groq as a fallback.
- ``groq``      — native ``groq`` SDK when installed; silently falls back to
                  the OpenAI-compatible endpoint otherwise.
- ``anthropic`` — Messages API (``POST {base_url}/messages`` with ``x-api-key``).

API key resolution order (first hit wins):

1. explicit ``api_key=`` argument
2. the provider's environment variable (e.g. ``GROQ_API_KEY``)
3. the same variable loaded from the nearest ``.env`` file (walked upward from
   the current working directory; ``PLF_ENV_FILE`` forces a specific file)

Nothing here imports a network library at module level — httpx and the groq SDK
are imported lazily inside the call, so the parser package keeps its zero
dependency footprint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    base_url: str = ""
    env_key: str = ""
    default_model: str = ""
    api: str = "openai"  # "openai" | "groq" | "anthropic"
    requires_key: bool = True


PROVIDERS: dict[str, ProviderSpec] = {
    s.name: s
    for s in (
        ProviderSpec(
            name="groq",
            label="Groq",
            base_url="https://api.groq.com/openai/v1",
            env_key="GROQ_API_KEY",
            default_model="llama-3.3-70b-versatile",
            api="groq",
        ),
        ProviderSpec(
            name="openai",
            label="OpenAI",
            base_url="https://api.openai.com/v1",
            env_key="OPENAI_API_KEY",
            default_model="gpt-4o-mini",
        ),
        ProviderSpec(
            name="together",
            label="Together.ai",
            base_url="https://api.together.xyz/v1",
            env_key="TOGETHER_API_KEY",
            default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        ),
        ProviderSpec(
            name="openrouter",
            label="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            env_key="OPENROUTER_API_KEY",
            default_model="meta-llama/llama-3.3-70b-instruct",
        ),
        ProviderSpec(
            name="deepseek",
            label="DeepSeek",
            base_url="https://api.deepseek.com/v1",
            env_key="DEEPSEEK_API_KEY",
            default_model="deepseek-chat",
        ),
        ProviderSpec(
            name="xai",
            label="xAI (Grok)",
            base_url="https://api.x.ai/v1",
            env_key="XAI_API_KEY",
            default_model="grok-3",
        ),
        ProviderSpec(
            name="mistral",
            label="Mistral",
            base_url="https://api.mistral.ai/v1",
            env_key="MISTRAL_API_KEY",
            default_model="mistral-large-latest",
        ),
        ProviderSpec(
            name="anthropic",
            label="Anthropic (Claude)",
            base_url="https://api.anthropic.com/v1",
            env_key="ANTHROPIC_API_KEY",
            default_model="claude-sonnet-4-5",
            api="anthropic",
        ),
        ProviderSpec(
            name="ollama",
            label="Ollama (local)",
            base_url="http://localhost:11434/v1",
            env_key="OLLAMA_HOST",  # base URL override, not a secret
            default_model="qwen2.5:3b",
            requires_key=False,
        ),
    )
}

DEFAULT_PROVIDER = "groq"


def get_provider(name: str | None) -> ProviderSpec:
    """Look up a provider by name; None means the default (groq)."""
    key = (name or DEFAULT_PROVIDER).strip().lower()
    if key not in PROVIDERS:
        known = ", ".join(PROVIDERS)
        raise ValueError(f"Unknown provider '{name}'. Known providers: {known}")
    return PROVIDERS[key]


def list_providers() -> list[dict]:
    """Metadata for UIs — never includes key material, only key *presence*."""
    ensure_env_loaded()
    out = []
    for spec in PROVIDERS.values():
        out.append(
            {
                "name": spec.name,
                "label": spec.label,
                "env_key": spec.env_key,
                "default_model": spec.default_model,
                "requires_key": spec.requires_key,
                "has_key": bool(resolve_api_key(spec)),
            }
        )
    return out


# --------------------------------------------------------------------------
# .env loading (zero-dependency parser)
# --------------------------------------------------------------------------

_env_loaded = False
_env_cache: dict[Path, dict[str, str]] = {}


def _parse_env_file(path: Path) -> dict[str, str]:
    if path in _env_cache:
        return _env_cache[path]
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            values[k.strip()] = v
    except OSError:
        pass
    _env_cache[path] = values
    return values


def _candidate_env_files(start: Path | None = None) -> list[Path]:
    forced = os.environ.get("PLF_ENV_FILE")
    if forced:
        return [Path(forced).expanduser()]
    start = (start or Path.cwd()).resolve()
    found = []
    for directory in [start, *start.parents]:
        env = directory / ".env"
        if env.is_file():
            found.append(env)
    return found


def ensure_env_loaded(start: Path | None = None) -> None:
    """Load the nearest .env into os.environ (never overriding real env vars).

    Idempotent; call again with a different cwd only matters for tests.
    """
    global _env_loaded
    for env_file in _candidate_env_files(start):
        for k, v in _parse_env_file(env_file).items():
            if k not in os.environ or not os.environ[k]:
                os.environ[k] = v
    _env_loaded = True


def resolve_api_key(spec: ProviderSpec, explicit: str | None = None) -> str:
    """explicit arg > environment variable > nearest .env file."""
    if explicit:
        return explicit
    if spec.env_key:
        value = os.environ.get(spec.env_key, "")
        if value:
            return value
        for env_file in _candidate_env_files():
            value = _parse_env_file(env_file).get(spec.env_key, "")
            if value:
                return value
    return ""


# --------------------------------------------------------------------------
# Transports
# --------------------------------------------------------------------------


def _post(url: str, *, json: dict, headers: dict, timeout: float = 120.0):
    """Single HTTP entry point (patched in tests)."""
    import httpx

    return httpx.post(url, json=json, headers=headers, timeout=timeout)


def _groq_native(spec, api_key, model, system, user, temperature, max_tokens):
    """Native groq SDK path; returns None if the SDK is unavailable."""
    try:
        from groq import Groq
    except ImportError:
        return None
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def chat(
    spec: ProviderSpec,
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    base_url: str | None = None,
) -> str:
    """Dispatch one chat turn to the provider; returns the assistant text."""
    if spec.api == "groq":
        native = _groq_native(spec, api_key, model, system, user, temperature, max_tokens)
        if native is not None:
            return native
        # fall through to the OpenAI-compatible endpoint

    if spec.api == "anthropic":
        return _chat_anthropic(spec, api_key, model, system, user, temperature, max_tokens, base_url)
    return _chat_openai_compat(spec, api_key, model, system, user, temperature, max_tokens, base_url)


def _chat_openai_compat(spec, api_key, model, system, user, temperature, max_tokens, base_url) -> str:
    url = (base_url or spec.base_url).rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key or 'not-needed'}"}
    if spec.name == "openrouter":
        headers["X-Title"] = "PLF"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    response = _post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _chat_anthropic(spec, api_key, model, system, user, temperature, max_tokens, base_url) -> str:
    url = (base_url or spec.base_url).rstrip("/") + "/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "temperature": temperature,
    }
    response = _post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data["content"][0]["text"]
