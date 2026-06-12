from typing import List, Mapping, Optional

from openai import OpenAI

from app.config import Settings


class LLMClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = OpenAI(
            # OpenAI SDK 要求 api_key 非空，但允许 base_url 指向无需鉴权的代理。
            # 传 "EMPTY_KEY" 绕过客户端侧校验，实际调用时通过 chat() 的 guard 拦截。
            api_key=settings.llm_api_key or "EMPTY_KEY",
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_sec,
        )

    def chat(
        self,
        messages: List[Mapping[str, str]],
        temperature: float = 0.2,
        model: Optional[str] = None,
    ) -> str:
        if not self._settings.llm_api_key:
            raise ValueError("LLM_API_KEY is empty. Please configure it in .env.")

        resp = self._client.chat.completions.create(
            model=model or self._settings.llm_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()
