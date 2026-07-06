from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class LLMProvider:
    def __init__(self) -> None:
        self.api_key: str | None = os.getenv("AQI_SENTINEL_LLM_API_KEY")
        self.provider: str = os.getenv("AQI_SENTINEL_LLM_PROVIDER", "")
        self.model: str = os.getenv("AQI_SENTINEL_LLM_MODEL", "")
        self._available = bool(self.api_key and self.provider and self.model)

    @property
    def is_available(self) -> bool:
        return self._available

    def summarize(self, prompt: str, structured_data: dict[str, Any]) -> str | None:
        if not self._available:
            return None
        try:
            return self._call_llm(prompt, structured_data)
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return None

    def _call_llm(self, prompt: str, structured_data: dict[str, Any]) -> str | None:
        provider = self.provider.lower().strip()

        if provider == "openai":
            return self._call_openai(prompt, structured_data)
        elif provider == "anthropic":
            return self._call_anthropic(prompt, structured_data)
        elif provider == "google":
            return self._call_google(prompt, structured_data)

        logger.warning("Unsupported LLM provider: %s", self.provider)
        return None

    def _call_openai(self, prompt: str, structured_data: dict[str, Any]) -> str | None:
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            model = self.model or "gpt-4o-mini"
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an air quality assistant. Summarize the provided data accurately. Do not add information not present in the data."},
                    {"role": "user", "content": f"{prompt}\n\nData:\n{json.dumps(structured_data, indent=2)}"},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            return resp.choices[0].message.content
        except ImportError:
            logger.warning("openai package not installed")
            return None
        except Exception as exc:
            logger.warning("OpenAI call failed: %s", exc)
            return None

    def _call_anthropic(self, prompt: str, structured_data: dict[str, Any]) -> str | None:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            model = self.model or "claude-3-haiku-20240307"
            resp = client.messages.create(
                model=model,
                max_tokens=500,
                system="You are an air quality assistant. Summarize the provided data accurately. Do not add information not present in the data.",
                messages=[
                    {"role": "user", "content": f"{prompt}\n\nData:\n{json.dumps(structured_data, indent=2)}"},
                ],
            )
            return resp.content[0].text if resp.content else None
        except ImportError:
            logger.warning("anthropic package not installed")
            return None
        except Exception as exc:
            logger.warning("Anthropic call failed: %s", exc)
            return None

    def _call_google(self, prompt: str, structured_data: dict[str, Any]) -> str | None:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model or "gemini-2.0-flash-lite")
            resp = model.generate_content(
                f"You are an air quality assistant. Summarize the provided data accurately. Do not add information not present in the data.\n\n{prompt}\n\nData:\n{json.dumps(structured_data, indent=2)}",
                generation_config={"temperature": 0.3, "max_output_tokens": 500},
            )
            return resp.text
        except ImportError:
            logger.warning("google-generativeai package not installed")
            return None
        except Exception as exc:
            logger.warning("Google call failed: %s", exc)
            return None


def get_llm_provider() -> LLMProvider:
    return LLMProvider()
