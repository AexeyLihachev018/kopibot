from openai import AsyncOpenAI
from config import OPENROUTER_API_KEY, MODELS


class BaseAgent:
    def __init__(self, model_key: str = "sonnet"):
        self.model_key = model_key
        self.client = AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )

    async def call_llm(self, messages: list[dict], model_key: str = None) -> str:
        model = MODELS[model_key or self.model_key]
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
