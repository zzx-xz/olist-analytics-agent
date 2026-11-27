from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMConfigurationError(RuntimeError):
    """Raised when the model endpoint is not configured."""


def create_chat_completion(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("LLM_MODEL", "deepseek-flash").strip()
    if not api_key or not model:
        raise LLMConfigurationError(
            "Set LLM_API_KEY and LLM_MODEL in the project .env file."
        )

    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.1,
        }
    ).encode("utf-8")
    request = Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError(
                    f"Model API returned HTTP {exc.code}: {detail}"
                ) from exc
        except URLError as exc:
            if attempt == 2:
                raise RuntimeError(
                    f"Could not reach the model API: {exc.reason}"
                ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Model API returned an unreadable response.") from exc
        time.sleep(1.5 * (attempt + 1))

    raise RuntimeError("Model API retries were exhausted.")
