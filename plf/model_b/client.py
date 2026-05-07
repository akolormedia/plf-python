import os
from .system_prompt import get_system_prompt

_DEFAULT_MODEL = "llama-3.3-70b-versatile"


class ModelBClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model or _DEFAULT_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = get_system_prompt()

    def chat(self, user_message: str, plf_context: str = "") -> str:
        from groq import Groq

        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Set the environment variable "
                "or pass api_key to ModelBClient()."
            )

        client = Groq(api_key=self.api_key)

        full_message = user_message
        if plf_context:
            full_message = f"=== PLF FILE ===\n{plf_context}\n\n=== USER QUERY ===\n{user_message}"

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": full_message},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        return response.choices[0].message.content

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
) -> ModelBClient:
    return ModelBClient(api_key=api_key, model=model)
