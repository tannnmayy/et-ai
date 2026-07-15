from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from backend.app.config import get_project_root

logger = logging.getLogger(__name__)

# Response cache: hash(system+prompt+data) -> (timestamp, text)
_RESPONSE_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL_SECONDS = int(os.getenv("AQI_SENTINEL_LLM_CACHE_TTL", str(8 * 60)))  # ~8 min default
_MAX_RETRIES = max(1, int(os.getenv("AQI_SENTINEL_LLM_MAX_RETRIES", "3")))
_BACKOFF_BASE = float(os.getenv("AQI_SENTINEL_LLM_BACKOFF_BASE", "0.8"))  # seconds


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
    "You are AQI Sentinel Copilot, an air quality assistant for Bengaluru. "
    "Summarize the provided tool data accurately. "
    "Do not invent stations, readings, or regulations not present in the data. "
    "If knowledge-base context is provided, prefer official CPCB / KSPCB / WHO wording. "
    "Be concise and actionable."
)

_PLANNING_SYSTEM_PROMPT = (
    "You are the planning brain of AQI Sentinel Copilot for Bengaluru air quality.\n"
    "You decide which tools to call to answer the user, then produce a grounded final answer.\n\n"
    "Rules:\n"
    "1. Respond with STRICT JSON only — no markdown fences, no prose outside JSON.\n"
    "2. Prefer real tools over guessing. Call enforcement, attribution, forecast, "
    "and policy-search tools when the question needs live or official data.\n"
    "3. For construction dust, vehicle emissions, CPCB/KSPCB rules, or inspection "
    "procedures always call tool_search_policy_guidance.\n"
    "4. For 'where is polluted' / 'what to inspect' call tool_get_enforcement_priority "
    "and/or tool_get_city_extremes.\n"
    "5. For station-specific air quality use station ids like cpcb_peenya, cpcb_bapujinagar.\n"
    "6. Never invent numbers. If a tool fails, say so and use remaining evidence.\n"
    "7. When enough evidence exists, return final_answer with a clear 2–5 sentence reply "
    "plus concrete next steps for citizens or enforcement officers.\n"
    "8. Do not call the same tool with identical arguments twice."
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


def _cache_key(system_prompt: str, prompt: str, structured_data: dict[str, Any]) -> str:
    blob = json.dumps(
        {"s": system_prompt, "p": prompt, "d": structured_data},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> str | None:
    hit = _RESPONSE_CACHE.get(key)
    if not hit:
        return None
    ts, text = hit
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _RESPONSE_CACHE.pop(key, None)
        return None
    return text


def _cache_set(key: str, text: str) -> None:
    _RESPONSE_CACHE[key] = (time.time(), text)
    # Soft bound cache size
    if len(_RESPONSE_CACHE) > 256:
        oldest = sorted(_RESPONSE_CACHE.items(), key=lambda kv: kv[1][0])[:64]
        for k, _ in oldest:
            _RESPONSE_CACHE.pop(k, None)


class LLMProvider:
    def __init__(self) -> None:
        load_dotenv(get_project_root() / ".env")
        self.provider = os.getenv("AQI_SENTINEL_LLM_PROVIDER", "gemini").strip().lower()
        self.model: str = os.getenv("AQI_SENTINEL_LLM_MODEL", "")
        self.gemini_model = os.getenv("AQI_SENTINEL_GEMINI_MODEL") or (
            self.model if self.provider == "gemini" and self.model.startswith("gemini-") else "gemini-2.5-flash"
        )
        self.openrouter_model = os.getenv("AQI_SENTINEL_OPENROUTER_MODEL") or (
            self.model if self.provider == "openrouter" else "openrouter/free"
        )

        # Multi-key Gemini pool (1 → 2 → 3) for rate-limit resilience
        self._gemini_keys: list[str] = []
        for env_name in (
            "AQI_SENTINEL_GEMINI_API_KEY",
            "AQI_SENTINEL_GEMINI_API_KEY_2",
            "AQI_SENTINEL_GEMINI_API_KEY_3",
            "GOOGLE_API_KEY",  # optional alias
        ):
            val = (os.getenv(env_name) or "").strip()
            if val and val not in self._gemini_keys:
                self._gemini_keys.append(val)

        self._keys = {
            "gemini": self._gemini_keys[0] if self._gemini_keys else None,
            "openrouter": os.getenv("AQI_SENTINEL_OPENROUTER_API_KEY"),
            "groq": os.getenv("AQI_SENTINEL_LLM_API_KEY"),
        }
        self._providers = self._configured_providers()
        self.api_key: str | None = self._keys.get(self.provider)
        self.last_provider: str | None = None
        self.last_gemini_key_index: int | None = None
        self.last_fallback_note: str | None = None
        self._available = bool(self._providers) or bool(self._gemini_keys)

    def _configured_providers(self) -> list[str]:
        """Prefer Gemini multi-key, then other configured services."""
        configured: list[str] = []
        order = (self.provider, "gemini", "openrouter", "groq")
        for provider in order:
            if provider == "gemini" and self._gemini_keys and "gemini" not in configured:
                configured.append("gemini")
            elif provider in self._keys and self._keys[provider] and provider not in configured:
                if provider != "gemini" or self._gemini_keys:
                    configured.append(provider)
        # Ensure gemini is tried first when keys exist
        if "gemini" in configured and configured[0] != "gemini":
            configured = ["gemini"] + [p for p in configured if p != "gemini"]
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
        knowledge_context: str = "",
    ) -> dict[str, Any] | None:
        if not self._available:
            return None

        tools_section = "\n".join(
            f"  - {name}: {schema['description']}\n    Parameters: {json.dumps(schema['parameters'], indent=6)}"
            for name, schema in tool_schemas.items()
        )

        results_section = json.dumps(tool_results_so_far, indent=2, default=str) if tool_results_so_far else "No tools called yet."
        kb_section = knowledge_context.strip() or "(none retrieved)"

        prompt = (
            f"You are planning tool use for AQI Sentinel (Bengaluru).\n\n"
            f"## User Query\n{query}\n\n"
            f"## Knowledge-base context\n{kb_section}\n\n"
            f"## Available Tools\n{tools_section}\n\n"
            f"## Results So Far (step {step_number} of {max_steps})\n{results_section}\n\n"
            f"## Instructions\n"
            f"Respond with STRICT JSON ONLY. No prose, no markdown fences.\n"
            f"Choose exactly one format:\n"
            f'  {{"action": "call_tool", "tool": "<tool_name>", "arguments": {{...}}}}\n'
            f'  {{"action": "final_answer", "text": "<natural language answer>"}}\n\n'
            f"If the query mentions construction dust, CPCB, KSPCB, enforcement rules, or vehicle norms, "
            f"call tool_search_policy_guidance early if not already called.\n"
            f"If you already have enough information, use final_answer.\n"
            f"If the step budget is nearly exhausted, use final_answer with what you have."
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
            # Tolerate leading junk before first {
            if "{" in cleaned and not cleaned.startswith("{"):
                cleaned = cleaned[cleaned.index("{") :]
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict) or "action" not in parsed:
                logger.warning("plan_next_step: parsed JSON missing 'action' key: %s", parsed)
                return None
            if parsed["action"] == "call_tool":
                if "tool" not in parsed or "arguments" not in parsed:
                    logger.warning("plan_next_step: call_tool missing fields: %s", parsed)
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
            logger.warning("plan_next_step: JSON parse error: %s — raw: %s", e, raw[:300] if raw else None)
            return None
        except Exception as exc:
            logger.warning("plan_next_step: unexpected error: %s", exc)
            return None

    def _call_llm(self, prompt: str, structured_data: dict[str, Any], system_prompt: str | None = None) -> str | None:
        system_msg = system_prompt or _SUMMARIZER_SYSTEM_PROMPT
        key = _cache_key(system_msg, prompt, structured_data)
        cached = _cache_get(key)
        if cached:
            logger.info("LLM cache hit")
            self.last_provider = "cache"
            return cached

        self.last_fallback_note = None
        for provider in self._providers:
            if provider == "gemini":
                response = self._call_gemini_with_key_fallback(prompt, structured_data, system_prompt=system_msg)
            elif provider == "openrouter":
                response = self._call_openai_compatible(
                    provider="openrouter",
                    base_url="https://openrouter.ai/api/v1",
                    model=self.openrouter_model,
                    prompt=prompt,
                    structured_data=structured_data,
                    system_prompt=system_msg,
                )
            else:
                response = self._call_groq(prompt, structured_data, system_prompt=system_msg)
            if response:
                self.last_provider = provider
                _cache_set(key, response)
                return response
            self.last_fallback_note = f"{provider} unavailable; trying next provider"
        return None

    def _call_gemini_with_key_fallback(
        self,
        prompt: str,
        structured_data: dict[str, Any],
        system_prompt: str | None = None,
    ) -> str | None:
        """Try each Gemini API key with exponential backoff on rate limits."""
        if not self._gemini_keys:
            return None

        for key_index, api_key in enumerate(self._gemini_keys, start=1):
            for attempt in range(1, _MAX_RETRIES + 1):
                result, rate_limited = self._call_gemini_once(
                    api_key=api_key,
                    prompt=prompt,
                    structured_data=structured_data,
                    system_prompt=system_prompt,
                )
                if result:
                    self.last_gemini_key_index = key_index
                    logger.info("Gemini success with key #%d (attempt %d)", key_index, attempt)
                    return result
                if rate_limited and attempt < _MAX_RETRIES:
                    delay = _BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini key #%d rate-limited (attempt %d/%d); backoff %.1fs",
                        key_index, attempt, _MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                if rate_limited:
                    logger.warning("Gemini key #%d exhausted after %d attempts; trying next key", key_index, _MAX_RETRIES)
                    break
                # Non-rate-limit failure — try next key sooner
                logger.warning("Gemini key #%d failed (non-rate-limit); trying next key", key_index)
                break
        return None

    def _call_gemini_once(
        self,
        *,
        api_key: str,
        prompt: str,
        structured_data: dict[str, Any],
        system_prompt: str | None = None,
    ) -> tuple[str | None, bool]:
        """Returns (text_or_None, was_rate_limited)."""
        try:
            import requests

            model = self.gemini_model
            system_msg = system_prompt or _SUMMARIZER_SYSTEM_PROMPT
            session = requests.Session()
            if _has_broken_loopback_proxy():
                session.trust_env = False
            data_blob = json.dumps(structured_data, indent=2, default=str) if structured_data else "{}"
            response = session.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                json={
                    "system_instruction": {"parts": [{"text": system_msg}]},
                    "contents": [{
                        "role": "user",
                        "parts": [{"text": f"{prompt}\n\nData:\n{data_blob}"}],
                    }],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1200},
                },
                timeout=25,
            )
            if response.status_code in (429, 503):
                return None, True
            if response.status_code == 400 and "API key" in response.text:
                logger.warning("Gemini rejected API key")
                return None, False
            response.raise_for_status()
            payload = response.json()
            # Blocked / safety
            if not payload.get("candidates"):
                logger.warning("Gemini returned no candidates: %s", str(payload)[:200])
                return None, False
            parts = payload["candidates"][0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts).strip()
            return (text or None), False
        except Exception as exc:
            msg = str(exc).lower()
            rate_limited = "429" in msg or "rate" in msg or "quota" in msg or "resource exhausted" in msg
            logger.warning("Gemini call failed: %s", exc)
            return None, rate_limited

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
                        {"role": "user", "content": f"{prompt}\n\nData:\n{json.dumps(structured_data, indent=2, default=str)}"},
                    ],
                    temperature=0.3,
                    max_tokens=800,
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
                    {"role": "user", "content": f"{prompt}\n\nData:\n{json.dumps(structured_data, indent=2, default=str)}"},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            return resp.choices[0].message.content
        except ImportError:
            logger.warning("openai package not installed")
            return None
        except APITimeoutError:
            logger.warning("Groq API call timed out — falling back")
            return None
        except Exception as exc:
            logger.warning("Groq call failed: %s", exc)
            return None


def get_llm_provider() -> LLMProvider:
    return LLMProvider()
