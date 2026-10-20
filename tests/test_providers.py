"""Tests for plf.model_b.providers — registry, key resolution, transports.

No network: providers._post is replaced with a recorder, and the native groq
SDK path is stubbed. Key resolution is exercised against env vars and a temp
PLF_ENV_FILE so the developer's real .env never influences the results.
"""

import pytest

from plf.model_b import providers
from plf.model_b.client import ModelBClient, create_client
from plf.model_b.modes import QueryResult


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


@pytest.fixture
def no_dotenv(monkeypatch):
    """Neutralize .env discovery and any real keys for the test."""
    monkeypatch.setenv("PLF_ENV_FILE", "/nonexistent/.env")
    for spec in providers.PROVIDERS.values():
        if spec.env_key:
            monkeypatch.delenv(spec.env_key, raising=False)


@pytest.fixture
def recorder(monkeypatch):
    """Capture the outgoing request; return canned completions."""
    calls = []

    def fake_post(url, *, json, headers, timeout=120.0):
        calls.append({"url": url, "json": json, "headers": headers})
        if "anthropic" in url:
            return FakeResponse({"content": [{"type": "text", "text": "hola desde claude"}]})
        return FakeResponse({"choices": [{"message": {"content": "hola desde el modelo"}}]})

    monkeypatch.setattr(providers, "_post", fake_post)
    return calls


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

def test_registry_has_expected_providers():
    assert set(providers.PROVIDERS) == {
        "groq", "openai", "together", "openrouter",
        "deepseek", "xai", "mistral", "anthropic", "ollama",
    }


def test_ollama_requires_no_key():
    spec = providers.get_provider("ollama")
    assert spec.requires_key is False


def test_get_provider_default_is_groq():
    assert providers.get_provider(None).name == "groq"
    assert providers.get_provider("GROQ").name == "groq"  # case-insensitive


def test_get_provider_unknown_lists_known():
    with pytest.raises(ValueError, match="deepseek"):
        providers.get_provider("costela")


def test_list_providers_never_exposes_keys(no_dotenv, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-secret")
    listing = providers.list_providers()
    names = [p["name"] for p in listing]
    assert "groq" in names and "ollama" in names
    for p in listing:
        assert set(p) == {
            "name", "label", "env_key", "default_model", "requires_key", "has_key",
        }
    groq = next(p for p in listing if p["name"] == "groq")
    assert groq["has_key"] is True


# --------------------------------------------------------------------------
# Key resolution
# --------------------------------------------------------------------------

def test_key_resolution_order(no_dotenv, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_PROV_KEY=from-dotenv\n")

    spec = providers.ProviderSpec(
        name="testprov", label="Test", env_key="TEST_PROV_KEY", default_model="m"
    )

    # 3. .env file
    monkeypatch.setenv("PLF_ENV_FILE", str(env_file))
    assert providers.resolve_api_key(spec) == "from-dotenv"

    # 2. environment variable beats .env
    monkeypatch.setenv("TEST_PROV_KEY", "from-env")
    assert providers.resolve_api_key(spec) == "from-env"

    # 1. explicit argument beats everything
    assert providers.resolve_api_key(spec, "explicit") == "explicit"


def test_client_picks_up_dotenv(no_dotenv, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-dotenv-test\n")
    monkeypatch.setenv("PLF_ENV_FILE", str(env_file))

    client = create_client(provider="deepseek")
    assert client.api_key == "sk-dotenv-test"
    assert client.model == "deepseek-chat"


# --------------------------------------------------------------------------
# Transports
# --------------------------------------------------------------------------

def test_openai_compat_transport(recorder, no_dotenv):
    spec = providers.get_provider("openai")
    out = providers.chat(
        spec, api_key="sk-test", model="gpt-4o-mini",
        system="SISTEMA", user="USUARIO", temperature=0.1, max_tokens=100,
    )
    assert out == "hola desde el modelo"

    call = recorder[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    assert call["json"]["messages"][0] == {"role": "system", "content": "SISTEMA"}
    assert call["json"]["messages"][1] == {"role": "user", "content": "USUARIO"}
    assert call["json"]["temperature"] == 0.1
    assert call["json"]["max_tokens"] == 100


def test_anthropic_transport(recorder, no_dotenv):
    spec = providers.get_provider("anthropic")
    out = providers.chat(
        spec, api_key="sk-ant", model="claude-sonnet-4-5",
        system="SISTEMA", user="USUARIO",
    )
    assert out == "hola desde claude"

    call = recorder[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"]["x-api-key"] == "sk-ant"
    assert call["headers"]["anthropic-version"] == "2023-06-01"
    # Anthropic takes system as a top-level field, not a message
    assert call["json"]["system"] == "SISTEMA"
    assert call["json"]["messages"] == [{"role": "user", "content": "USUARIO"}]


def test_groq_prefers_native_sdk(monkeypatch, no_dotenv):
    seen = {}

    def fake_native(spec, api_key, model, system, user, temperature, max_tokens):
        seen["called"] = True
        return "respuesta nativa"

    monkeypatch.setattr(providers, "_groq_native", fake_native)
    out = providers.chat(
        providers.get_provider("groq"), api_key="g", model="m", system="s", user="u"
    )
    assert out == "respuesta nativa"
    assert seen.get("called")


def test_groq_falls_back_to_compat(recorder, monkeypatch, no_dotenv):
    monkeypatch.setattr(providers, "_groq_native", lambda *a, **k: None)
    out = providers.chat(
        providers.get_provider("groq"), api_key="g", model="m", system="s", user="u"
    )
    assert out == "hola desde el modelo"
    assert recorder[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"


def test_ollama_local_without_key(recorder, no_dotenv):
    providers.chat(
        providers.get_provider("ollama"), api_key="", model="qwen2.5:3b",
        system="s", user="u",
    )
    call = recorder[0]
    assert call["url"] == "http://localhost:11434/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer not-needed"


def test_base_url_override(recorder, no_dotenv):
    providers.chat(
        providers.get_provider("openai"), api_key="k", model="m",
        system="s", user="u", base_url="http://127.0.0.1:11434/v1",
    )
    assert recorder[0]["url"] == "http://127.0.0.1:11434/v1/chat/completions"


# --------------------------------------------------------------------------
# Client integration + backward compatibility
# --------------------------------------------------------------------------

def test_client_end_to_end_query(recorder, no_dotenv):
    client = create_client(provider="openai", api_key="sk-test")
    result = client.query("¿dónde está Laura?", plf_context="PLF1.0 ...")
    assert isinstance(result, QueryResult)
    # the PLF context is wrapped and sent as the user message
    sent = recorder[0]["json"]["messages"][1]["content"]
    assert sent.startswith("=== PLF FILE ===")
    assert "=== USER QUERY ===" in sent


def test_backward_compat_default_provider(no_dotenv, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g-key")
    client = create_client()
    assert client.spec.name == "groq"
    assert client.model == "llama-3.3-70b-versatile"
    assert client.api_key == "g-key"


def test_missing_key_error_names_env_var(no_dotenv):
    client = ModelBClient(provider="anthropic", api_key="")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        client.chat("hola")
