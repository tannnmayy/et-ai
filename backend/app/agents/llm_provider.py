from __future__ import annotations

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from backend.app.config import get_project_root

logger = logging.getLogger(__name__)


def _has_broken_loopback_proxy() -> bool:
    """Detect the known unusable local proxy without overriding real proxies."""
    proxy_values = (
        os.getenv("HTTPS_PROXY", ""),
        os.getenv("HTTP_PROXY", ""),
        os.getenv("ALL_PROXY", ""),
        os.getenv("https_proxy", ""),
        os.getenv("http_proxy", ""),
        os.getenv("all_proxy", ""),
    )
    return any("127.0.0.1:9" in value or "localhost:9" in value for value in proxy_values)

_SUMMARIZER_SYSTEM_PROMPT = (
    "You are an air quality assistant. "
    "Summarize the provided data accurately. "
    "Do not add information not present in the data."
)

_PLANNING_SYSTEM_PROMPT = (
    "You are a tool-use planner for an air quality system. "
    "Respond only with the exact JSON format requested — no summarization, no prose."
)

_CAUSAL_EXPLANATION_SYSTEM_PROMPT = (
    "You are an air quality science communicator. "
    "Explain the sources of pollution at a specific location in clear, plain language "
    "that a non-expert resident can understand. "
    "Use the source attribution percentages, wind data, and fused PM2.5 estimate provided. "
    "Do not invent data. Do not make causal claims that are not supported by the data. "
    "Respond only with the explanation — no extra commentary, no disclaimers."
)

_ENFORCEMENT_ACTION_SYSTEM_PROMPT = (
    "You are an air quality enforcement advisor generating actionable intervention guidance. "
    "Given the source attribution breakdown, risk scores, and PM2.5 estimate for a specific "
    "Bengaluru hexagon, produce a brief actionable recommendation. "
    "Your response must include:\n"
    "1. The dominant actionable source category (traffic / industrial / construction / burning).\n"
    "2. A concrete recommended enforcement action — specific enough that an inspector "
    "could act on it (e.g. \"inspect active construction sites for dust suppression compliance\", "
    "\"coordinate with traffic police for congestion management during peak hours\", "
    "\"verify industrial emissions compliance at nearby factories\", "
    "\"check for open waste burning in residential zones\").\n"
    "3. Reference to the real data driving the recommendation (the actual exposure weight, "
    "attributable magnitude, and PM2.5 reading — use the numbers provided).\n"
    "Do not invent data. Do not add information not present in the breakdown. "
    "Keep the response to 2-3 sentences. Be direct and actionable."
)


class LLMProvider:
    def __init__(self) -> None:
        # Provider workers can be imported before FastAPI starts. Loading the
        # workspace environment here prevents import order from disabling Deep
        # Reasoning even when credentials are configured.
        load_dotenv(get_project_root() / ".env")
        self.provider = os.getenv("AQI_SENTINEL_LLM_PROVIDER", "groq").strip().lower()
        self.model: str = os.getenv("AQI_SENTINEL_LLM_MODEL", "")
        self.gemini_model = os.getenv("AQI_SENTINEL_GEMINI_MODEL") or (
            self.model if self.provider == "gemini" and self.model.startswith("gemini-") else "gemini-2.5-flash"
        )
        self.openrouter_model = os.getenv("AQI_SENTINEL_OPENROUTER_MODEL") or (
            self.model if self.provider == "openrouter" else "openrouter/free"
        )
        self._keys = {
            "gemini": os.getenv("AQI_SENTINEL_GEMINI_API_KEY"),
            "openrouter": os.getenv("AQI_SENTINEL_OPENROUTER_API_KEY"),
            "groq": os.getenv("AQI_SENTINEL_LLM_API_KEY"),
        }
        self._providers = self._configured_providers()
        self.api_key: str | None = self._keys.get(self.provider)
        self.last_provider: str | None = None
        self._available = bool(self._providers)

    def _configured_providers(self) -> list[str]:
        """Prefer the selected service and use other configured services as fallbacks."""
        configured: list[str] = []
        for provider in (self.provider, "gemini", "openrouter", "groq"):
            if provider in self._keys and self._keys[provider] and provider not in configured:
                configured.append(provider)
        return configured

    @property
    def is_available(self) -> bool:
        return self._available

    def summarize(self, prompt: str, structured_data: dict[str, Any], system_prompt: str | None = None) -> str | None:
        if not self._available:
            return None
        try:
            return self._call_llm(prompt, structured_data, system_prompt=system_prompt)
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return None

    def plan_next_step(
        self,
        query: str,
        tool_schemas: dict[str, dict],
        tool_results_so_far: dict[str, Any],
        step_number: int,
        max_steps: int,
    ) -> dict[str, Any] | None:
        if not self._available:
            return None

        tools_section = "\n".join(
            f"  - {name}: {schema['description']}\n    Parameters: {json.dumps(schema['parameters'], indent=6)}"
            for name, schema in tool_schemas.items()
        )

        results_section = json.dumps(tool_results_so_far, indent=2) if tool_results_so_far else "No tools called yet."

        prompt = (
            f"You are an air quality research planner. You have access to a set of tools to answer the user's query.\n\n"
            f"## User Query\n{query}\n\n"
            f"## Available Tools\n{tools_section}\n\n"
            f"## Results So Far (step {step_number} of {max_steps})\n{results_section}\n\n"
            f"## Instructions\n"
            f"Respond with STRICT JSON ONLY. No prose, no markdown fences, no explanation.\n"
            f"Choose exactly one of these two response formats:\n"
            f'  {{"action": "call_tool", "tool": "<tool_name>", "arguments": {{...}}}}\n'
            f'  {{"action": "final_answer", "text": "<natural language answer>"}}\n\n'
            f"If you already have enough information to answer the query, use final_answer.\n"
            f"If you cannot make progress or the step budget is nearly exhausted, use final_answer with whatever you have gathered.\n"
            f"Do not call the same tool with identical arguments twice."
        )

        try:
            raw = self._call_llm(prompt, {}, system_prompt=_PLANNING_SYSTEM_PROMPT)
            if raw is None:
                return None
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict) or "action" not in parsed:
                logger.warning("plan_next_step: parsed JSON missing 'action' key: %s", parsed)
                return None
            if parsed["action"] == "call_tool":
                if "tool" not in parsed or "arguments" not in parsed:
                    logger.warning("plan_next_step: call_tool missing 'tool' or 'arguments': %s", parsed)
                    return None
            elif parsed["action"] == "final_answer":
                if "text" not in parsed:
                    logger.warning("plan_next_step: final_answer missing 'text': %s", parsed)
                    return None
            else:
                logger.warning("plan_next_step: unknown action '%s'", parsed.get("action"))
                return None
            return parsed
        except json.JSONDecodeError as e:
            logger.warning("plan_next_step: JSON parse error: %s — raw: %s", e, raw)
            return None
        except Exception as exc:
            logger.warning("plan_next_step: unexpected error: %s", exc)
            return None

    def _call_llm(self, prompt: str, structured_data: dict[str, Any], system_prompt: str | None = None) -> str | None:
        for provider in self._providers:
            if provider == "gemini":
                response = self._call_gemini(prompt, structured_data, system_prompt=system_prompt)
            elif provider == "openrouter":
                response = self._call_openai_compatible(
                    provider="openrouter",
                    base_url="https://openrouter.ai/api/v1",
                    model=self.openrouter_model,
                    prompt=prompt,
                    structured_data=structured_data,
                    system_prompt=system_prompt,
                )
            else:
                response = self._call_groq(prompt, structured_data, system_prompt=system_prompt)
            if response:
                self.last_provider = provider
                return response
        return None

    def _call_gemini(self, prompt: str, structured_data: dict[str, Any], system_prompt: str | None = None) -> str | None:
        """Use Gemini's native REST API; no extra SDK is required."""
        try:
            import requests

            model = self.gemini_model
            system_msg = system_prompt or _SUMMARIZER_SYSTEM_PROMPT
            session = requests.Session()
            if _has_broken_loopback_proxy():
                logger.info("Ignoring unavailable loopback proxy for Gemini")
                session.trust_env = False
            response = session.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": self._keys["gemini"]},
                json={
                    "system_instruction": {"parts": [{"text": system_msg}]},
                    "contents": [{"role": "user", "parts": [{"text": f"{prompt}\n\nData:\n{json.dumps(structured_data, indent=2)}"}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500},
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts).strip()
            if not text:
                logger.warning("Gemini returned no text content")
            return text or None
        except Exception as exc:
            logger.warning("Gemini call failed: %s", exc)
            return None

    def _call_openai_compatible(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        prompt: str,
        structured_data: dict[str, Any],
        system_prompt: str | None = None,
    ) -> str | None:
        try:
            import openai
            import httpx

            http_client = httpx.Client(timeout=20.0, trust_env=not _has_broken_loopback_proxy())
            client = openai.OpenAI(api_key=self._keys[provider], base_url=base_url, timeout=20.0, http_client=http_client)
            system_msg = system_prompt or _SUMMARIZER_SYSTEM_PROMPT
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": f"{prompt}\n\nData:\n{json.dumps(structured_data, indent=2)}"},
                    ],
                    temperature=0.3,
                    max_tokens=500,
                )
                return resp.choices[0].message.content
            finally:
                http_client.close()
        except Exception as exc:
            logger.warning("%s call failed: %s", provider.title(), exc)
            return None

    def _call_groq(self, prompt: str, structured_data: dict[str, Any], system_prompt: str | None = None) -> str | None:
        try:
            import openai
            from openai import APITimeoutError
            client = openai.OpenAI(
                api_key=self._keys["groq"],
                base_url="https://api.groq.com/openai/v1",
                timeout=15.0,
            )
            model = self.model if self.provider == "groq" and self.model else "openai/gpt-oss-120b"
            system_msg = system_prompt or _SUMMARIZER_SYSTEM_PROMPT
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": f"{prompt}\n\nData:\n{json.dumps(structured_data, indent=2)}"},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            return resp.choices[0].message.content
        except ImportError:
            logger.warning("openai package not installed")
            return None
        except APITimeoutError:
            logger.warning("Groq API call timed out after 15s — falling back to deterministic mode")
            return None
        except Exception as exc:
            logger.warning("Groq call failed: %s", exc)
            return None


def get_llm_provider() -> LLMProvider:
    return LLMProvider()
