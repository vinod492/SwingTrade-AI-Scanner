"""OpenAI-backed trade analysis (chat completions via httpx, JSON response)."""
from __future__ import annotations

import json
import logging

import httpx

from app.config import get_settings
from app.providers.base import AIProvider
from app.providers.sample_ai import SampleAIProvider

log = logging.getLogger(__name__)

_SYSTEM = """You are a senior swing-trading analyst. Given a stock's technical
context, produce a concise, concrete analysis. Respond with a JSON object with
exactly these string keys: why_moving, bull_case, bear_case, technical,
trade_plan, risk_factors. 2-4 sentences per section. Reference the actual
numbers provided. Always close risk_factors by noting this is research, not
financial advice."""


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self._model = settings.openai_model
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key or settings.openai_api_key}"},
            timeout=60,
        )

    async def analyze(self, ctx: dict) -> dict:
        try:
            resp = await self._client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": json.dumps(ctx, default=str)},
                    ],
                    "temperature": 0.4,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            required = {"why_moving", "bull_case", "bear_case", "technical",
                        "trade_plan", "risk_factors"}
            if required <= set(data):
                return {k: str(data[k]) for k in required}
            raise ValueError(f"missing keys: {required - set(data)}")
        except Exception as exc:  # fall back rather than fail the request
            log.warning("openai analysis failed (%s); using sample analysis", exc)
            return await SampleAIProvider().analyze(ctx)
