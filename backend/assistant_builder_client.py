from __future__ import annotations

import os
from typing import Dict, List, Optional

import httpx


class AssistantBuilderClient:
    """OVMS-backed chat client using the OpenAI-compatible REST API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout_seconds: float = 120.0, max_tokens: int = 256) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self._client = httpx.AsyncClient(timeout=self.timeout_seconds)

    async def chat(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        session_key: Optional[str] = None,  # unused for OVMS; kept for interface compatibility
        name: str = "Debate Arena",
    ) -> str:
        payload = {
            "model": model_id,
            "messages": messages,
            "stream": False,
            "temperature": 0.7,
            "max_tokens": self.max_tokens,
        }

        url = f"{self.base_url}/v3/chat/completions"
        resp = await self._client.post(url, json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_detail = ""
            try:
                error_detail = f" - {resp.text}"
            except:
                pass
            raise RuntimeError(f"OVMS request failed: {exc.response.status_code}{error_detail}") from exc
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Unexpected OVMS response: {data}") from exc

    async def warmup(self) -> None:
        # Optional: hit config to ensure server is reachable.
        try:
            await self._client.get(f"{self.base_url}/v1/config")
        except Exception:
            return

    async def aclose(self) -> None:
        await self._client.aclose()
