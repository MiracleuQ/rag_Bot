import logging
import time
from typing import List, Mapping, Optional

from openai import OpenAI, APIStatusError, RateLimitError, APITimeoutError, APIConnectionError

from app.config import Settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY_SEC = 1.0


class LLMClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = OpenAI(
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

        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.chat.completions.create(
                    model=model or self._settings.llm_model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                )
                return (resp.choices[0].message.content or "").strip()
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    delay = _BASE_DELAY_SEC * (2 ** attempt)
                    logger.warning(
                        "LLM call failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1, _MAX_RETRIES, exc, delay,
                    )
                    time.sleep(delay)
            except APIStatusError as exc:
                if exc.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                    last_exc = exc
                    delay = _BASE_DELAY_SEC * (2 ** attempt)
                    logger.warning(
                        "LLM server error %d (attempt %d/%d). Retrying in %.1fs...",
                        exc.status_code, attempt + 1, _MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                raise

        raise last_exc  # type: ignore[misc]
