"""Model B client — LLM-backed PLF editor/query.

Provider-aware since 2026-10-20 (PLAN.md Fase V1). The default provider is
groq with GROQ_API_KEY, so the pre-provider call signature keeps working:

    create_client()                      # groq, key from env/.env
    create_client(api_key="...", model="...")

New call shape:

    create_client(provider="openai", model="gpt-4o-mini")
    create_client(provider="anthropic")
    create_client(provider="ollama")     # local, no key needed

See plf/model_b/providers.py for the registry and key resolution order.
"""

from __future__ import annotations

from .providers import (
    DEFAULT_PROVIDER,
    ProviderSpec,
    chat as _provider_chat,
    ensure_env_loaded,
    get_provider,
    resolve_api_key,
)
from .system_prompt import get_system_prompt


class ModelBClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        base_url: str | None = None,
    ):
        ensure_env_loaded()
        self.spec: ProviderSpec = get_provider(provider)
        self.api_key = resolve_api_key(self.spec, api_key)
        self.model = model or self.spec.default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.system_prompt = get_system_prompt()

    def chat(self, user_message: str, plf_context: str = "") -> str:
        if self.spec.requires_key and not self.api_key:
            raise ValueError(
                f"No API key for provider '{self.spec.name}'. "
                f"Set the {self.spec.env_key} environment variable, "
                f"pass api_key= to create_client(), or add it to a .env file."
            )

        full_message = user_message
        if plf_context:
            full_message = (
                f"=== PLF FILE ===\n{plf_context}\n\n=== USER QUERY ===\n{user_message}"
            )

        return _provider_chat(
            self.spec,
            api_key=self.api_key,
            model=self.model,
            system=self.system_prompt,
            user=full_message,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            base_url=self.base_url,
        )

    def query(self, question: str, plf_context: str = "") -> "QueryResult":
        from .modes import parse_query

        output = self.chat(question, plf_context)
        return parse_query(output)

    def propose(self, prompt: str, plf_context: str = "") -> "ProposalResult":
        from .modes import parse_proposal

        output = self.chat(prompt, plf_context)
        return parse_proposal(output)

    def instruct(self, instruction: str, plf_context: str = "") -> "InstructionResult":
        from .modes import parse_instruction

        output = self.chat(instruction, plf_context)
        return parse_instruction(output)


def create_client(
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
) -> ModelBClient:
    return ModelBClient(api_key=api_key, model=model, provider=provider, base_url=base_url)
