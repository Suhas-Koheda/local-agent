import json
import uuid
from typing import Any, Dict, List, Optional

import httpx


class ModelProvider:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434/v1",
        model_name: str = "qwen2.5:3b",
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "options": {"num_ctx": 8192},
        }

        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, json=payload)

            if response.status_code != 200:
                raise RuntimeError(
                    f"Ollama API Error [{response.status_code}]: {response.text}"
                )

            try:
                data = response.json()
            except Exception as e:
                raise RuntimeError(
                    f"Failed to parse JSON from Ollama: {response.text}"
                ) from e

            choices = data.get("choices", [])
            if not choices:
                return {
                    "role": "assistant",
                    "content": "No response returned from model.",
                    "tool_calls": None,
                }

            choice_msg = choices[0].get("message", {})

            raw_tool_calls = choice_msg.get("tool_calls")
            normalized_tool_calls = None
            if raw_tool_calls:
                normalized_tool_calls = []
                for idx, call in enumerate(raw_tool_calls):
                    call_dict = dict(call)
                    if "id" not in call_dict or not call_dict["id"]:
                        call_dict["id"] = f"call_{uuid.uuid4().hex[:8]}"
                    normalized_tool_calls.append(call_dict)

            return {
                "role": "assistant",
                "content": choice_msg.get("content") or "",
                "tool_calls": normalized_tool_calls,
            }
