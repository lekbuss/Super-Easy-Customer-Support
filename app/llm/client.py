import asyncio
import json
import logging
import time

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    pass


class AnthropicClient:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model
        self._max_tokens = settings.llm_max_tokens
        self._temperature = settings.llm_temperature

    async def chat(self, system_prompt: str, user_message: str) -> str:
        max_attempts = 3
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            try:
                response = await asyncio.to_thread(
                    self._client.messages.create,
                    model=self._model,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    timeout=30.0,
                )
                logger.info(
                    "LLM usage: input_tokens=%d output_tokens=%d",
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                return response.content[0].text
            except anthropic.APIStatusError as exc:
                last_error = exc
                if exc.status_code in (429, 500, 502, 503, 529):
                    wait = 2**attempt
                    logger.warning(
                        "Anthropic API error %s on attempt %d/%d, retrying in %ds",
                        exc.status_code,
                        attempt + 1,
                        max_attempts,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise LLMServiceError(str(exc)) from exc
            except anthropic.APIConnectionError as exc:
                last_error = exc
                wait = 2**attempt
                logger.warning(
                    "Anthropic connection error on attempt %d/%d, retrying in %ds",
                    attempt + 1,
                    max_attempts,
                    wait,
                )
                await asyncio.sleep(wait)

        raise LLMServiceError(
            f"Anthropic API failed after {max_attempts} attempts"
        ) from last_error

    def chat_sync(self, system_prompt: str, user_message: str) -> str:
        """Synchronous variant of chat() for use in non-async call paths."""
        max_attempts = 3
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    timeout=30.0,
                )
                logger.info(
                    "LLM usage (sync): input_tokens=%d output_tokens=%d",
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                return response.content[0].text
            except anthropic.APIStatusError as exc:
                last_error = exc
                if exc.status_code in (429, 500, 502, 503, 529):
                    wait = 2**attempt
                    logger.warning(
                        "Anthropic API error %s on attempt %d/%d, retrying in %ds",
                        exc.status_code,
                        attempt + 1,
                        max_attempts,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    raise LLMServiceError(str(exc)) from exc
            except anthropic.APIConnectionError as exc:
                last_error = exc
                wait = 2**attempt
                logger.warning(
                    "Anthropic connection error on attempt %d/%d, retrying in %ds",
                    attempt + 1,
                    max_attempts,
                    wait,
                )
                time.sleep(wait)

        raise LLMServiceError(
            f"Anthropic API failed after {max_attempts} attempts"
        ) from last_error

    def chat_with_search_sync(
        self, system_prompt: str, user_message: str, max_uses: int = 3
    ) -> tuple[str, list[str]]:
        """Call Claude with Anthropic's built-in web search tool enabled.

        Returns (response_text, source_urls).
        Falls back gracefully if the model does not support web search.
        """
        max_attempts = 3
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    tools=[
                        {
                            "type": "web_search_20250305",
                            "name": "web_search",
                            "max_uses": max_uses,
                        }
                    ],
                    timeout=30.0,
                )
                logger.info(
                    "LLM usage (web_search): input_tokens=%d output_tokens=%d",
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )

                text_parts: list[str] = []
                sources: list[str] = []

                for block in response.content:
                    block_type = getattr(block, "type", None)
                    if block_type == "text":
                        text_parts.append(getattr(block, "text", ""))
                    elif block_type == "tool_result":
                        # Extract URLs from web search tool results
                        content = getattr(block, "content", [])
                        if isinstance(content, list):
                            for item in content:
                                url = getattr(item, "url", None)
                                if url:
                                    sources.append(url)
                    elif block_type == "web_search_tool_result":
                        content = getattr(block, "content", [])
                        if isinstance(content, list):
                            for item in content:
                                url = getattr(item, "url", None)
                                if url:
                                    sources.append(url)

                text = "\n".join(text_parts).strip()
                return text, sources

            except anthropic.APIStatusError as exc:
                last_error = exc
                if exc.status_code in (429, 500, 502, 503, 529):
                    wait = 2**attempt
                    logger.warning(
                        "Anthropic API error %s on attempt %d/%d (chat_with_search), retrying in %ds",
                        exc.status_code,
                        attempt + 1,
                        max_attempts,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    raise LLMServiceError(str(exc)) from exc
            except anthropic.APIConnectionError as exc:
                last_error = exc
                wait = 2**attempt
                logger.warning(
                    "Anthropic connection error on attempt %d/%d (chat_with_search), retrying in %ds",
                    attempt + 1,
                    max_attempts,
                    wait,
                )
                time.sleep(wait)

        raise LLMServiceError(
            f"chat_with_search failed after {max_attempts} attempts"
        ) from last_error

    async def chat_json(self, system_prompt: str, user_message: str) -> dict:
        for attempt in range(2):
            raw = await self.chat(system_prompt, user_message)
            try:
                text = raw.strip()
                # Strip markdown code fences if present
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1]
                    text = text.rsplit("```", 1)[0]
                return json.loads(text)
            except json.JSONDecodeError as exc:
                if attempt == 0:
                    logger.warning(
                        "JSON parse failed on first attempt, retrying. Raw: %.200s",
                        raw,
                    )
                    continue
                raise LLMServiceError(
                    f"LLM did not return valid JSON after 2 attempts: {exc}"
                ) from exc

        # Unreachable, but satisfies type checkers
        raise LLMServiceError("chat_json: unexpected exit")
