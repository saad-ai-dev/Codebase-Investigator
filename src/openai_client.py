from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenAIClientError(RuntimeError):
    pass


@dataclass
class StructuredSchema:
    name: str
    schema: dict[str, Any]


class OpenAIResponsesClient:
    def __init__(
        self, api_key: str | None = None, base_url: str = "https://api.openai.com/v1/responses"
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        if not self.api_key:
            raise OpenAIClientError("OPENAI_API_KEY is required.")

    def create_structured_output(
        self,
        model: str,
        instructions: str,
        user_content: str,
        schema: StructuredSchema,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_content},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema.name,
                    "schema": schema.schema,
                    "strict": True,
                }
            },
        }

        request = Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenAIClientError(f"OpenAI API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise OpenAIClientError(f"OpenAI API request failed: {exc.reason}") from exc

        text = _extract_output_text(body)
        if not text:
            raise OpenAIClientError("OpenAI API returned no text output.")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise OpenAIClientError(f"Structured output was not valid JSON: {text}") from exc


def _extract_output_text(body: dict[str, Any]) -> str:
    output = body.get("output", [])
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                return content.get("text", "")
    return body.get("output_text", "")
