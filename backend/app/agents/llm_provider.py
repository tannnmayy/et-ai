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

# Circuit breaker: provider_name -> unix timestamp until which we skip it
_CIRCUIT_COOLDOWN_UNTIL: dict[str, float] = {}
_CIRCUIT_COOLDOWN_S = float(os.getenv("AQI_SENTINEL_LLM_CIRCUIT_COOLDOWN", "90"))

# Groq model for native tool calling.
# Many projects block Llama 3.1/3.3 70B; openai/gpt-oss-120b is widely available.
# Override with AQI_SENTINEL_GROQ_MODEL if your project enables other models.
_DEFAULT_GROQ_TOOL_MODEL = os.getenv(
    "AQI_SENTINEL_GROQ_MODEL", "openai/gpt-oss-120b"
)


def _circuit_open(provider: str) -> bool:
    until = _CIRCUIT_COOLDOWN_UNTIL.get(provider, 0.0)
    if until <= 0:
        return False
    if time.time() >= until:
        _CIRCUIT_COOLDOWN_UNTIL.pop(provider, None)
        return False
    return True


def _trip_circuit(provider: str, reason: str = "rate_limit") -> None:
    _CIRCUIT_COOLDOWN_UNTIL[provider] = time.time() + _CIRCUIT_COOLDOWN_S
    logger.warning(
        "Circuit breaker OPEN for %s (%.0fs) — %s",
        provider,
        _CIRCUIT_COOLDOWN_S,
        reason,
    )


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
    "You are AQI Sentinel Copilot — Bengaluru's operational air-quality assistant for "
    "citizens and enforcement officers.\n\n"
    "Grounding rules:\n"
    "• Use ONLY numbers, stations, hexes, and tool fields present in the Data payload.\n"
    "• If knowledge-base / policy passages are present, prefer official CPCB, KSPCB, "
    "Karnataka State Action Plan, NCAP, or WHO wording. Never invent regulation text.\n"
    "• Distinguish clearly: live sensor/model evidence vs policy guidance vs investigation "
    "hypotheses (source attribution is not legal proof of a polluter).\n"
    "• Be concise (2–6 short paragraphs or bullets), actionable, and honest about data gaps.\n"
    "• End enforcement answers with a practical next step for officers when relevant."
)

_PLANNING_SYSTEM_PROMPT = (
    "You are the planning brain of AQI Sentinel Copilot for Bengaluru air quality.\n"
    "You choose tools, gather evidence, then produce a grounded final answer.\n\n"
    "OUTPUT FORMAT (mandatory):\n"
    "• Respond with STRICT JSON only — no markdown fences, no prose outside JSON.\n"
    "• Exactly one of:\n"
    '    {"action":"call_tool","tool":"<name>","arguments":{...}}\n'
    '    {"action":"final_answer","text":"<natural language answer>"}\n\n'
    "TOOL SELECTION PRIORITY:\n"
    "1. POLICY / REGULATIONS — If the user mentions CPCB, KSPCB, NCAP, WHO, guidelines, "
    "emission norms, construction dust rules, legal requirements, or 'what does the "
    "policy say', you MUST call tool_search_policy_guidance early (unless its results "
    "are already in Results So Far). Prefer knowledge-base evidence over free-form recall.\n"
    "2. ENFORCEMENT / DISPATCH — For 'what to inspect', 'hotspots', 'priorities', "
    "'construction sites', or officer routing → tool_get_enforcement_priority "
    "(prefer over tool_get_inspection_priorities). Optionally add tool_get_city_extremes.\n"
    "3. WHY POLLUTED / SOURCES — For source mix, traffic vs industrial vs construction → "
    "tool_get_attribution and/or tool_get_causal_explanation (need lat/lon or h3 when possible).\n"
    "4. STATION FORECAST — Known station ids (cpcb_peenya, cpcb_bapujinagar, cpcb_hebbal, …) "
    "→ tool_get_forecast_evidence; trust questions → tool_get_forecast_confidence.\n"
    "5. CITY OVERVIEW — briefing / situation report → tool_get_city_briefing.\n"
    "6. WEATHER / TRAVEL — outdoor safety, commute, rain → weather + travel readiness tools.\n\n"
    "QUALITY RULES:\n"
    "• Never invent PM2.5 values, rankings, or regulation quotes. If a tool fails, say so.\n"
    "• Do not call the same tool with identical arguments twice.\n"
    "• When evidence is sufficient, emit final_answer: 2–5 clear sentences + concrete next steps.\n"
    "• If the step budget is nearly exhausted, finalize with what you have rather than looping."
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

        # Multi-key Groq pool (dedicated Copilot keys first)
        self._groq_keys: list[str] = []
        for env_name in (
            "AQI_SENTINEL_GROQ_API_KEY",
            "AQI_SENTINEL_GROQ_API_KEY_2",
            "AQI_SENTINEL_LLM_API_KEY",  # legacy single Groq key
            "GROQ_API_KEY",
        ):
            val = (os.getenv(env_name) or "").strip()
            if val and val not in self._groq_keys:
                self._groq_keys.append(val)

        self.groq_model = (
            os.getenv("AQI_SENTINEL_GROQ_MODEL")
            or (self.model if self.provider == "groq" and self.model else None)
            or _DEFAULT_GROQ_TOOL_MODEL
        )

        self._keys = {
            "gemini": self._gemini_keys[0] if self._gemini_keys else None,
            "openrouter": os.getenv("AQI_SENTINEL_OPENROUTER_API_KEY"),
            "groq": self._groq_keys[0] if self._groq_keys else None,
        }
        self._providers = self._configured_providers()
        self.api_key: str | None = self._keys.get(self.provider)
        self.last_provider: str | None = None
        self.last_gemini_key_index: int | None = None
        self.last_groq_key_index: int | None = None
        self.last_fallback_note: str | None = None
        self._available = bool(self._providers) or bool(self._gemini_keys) or bool(self._groq_keys)

    def _configured_providers(self) -> list[str]:
        """Copilot Phase 1: Groq first (tool-calling), then Gemini, then OpenRouter."""
        configured: list[str] = []
        # Explicit preferred order for the new architecture
        prefer = os.getenv("AQI_SENTINEL_LLM_PROVIDER", "groq").strip().lower()
        if prefer == "gemini":
            order = ("gemini", "groq", "openrouter")
        else:
            order = ("groq", "gemini", "openrouter")
        for provider in order:
            if provider == "gemini" and self._gemini_keys and "gemini" not in configured:
                configured.append("gemini")
            elif provider == "groq" and self._groq_keys and "groq" not in configured:
                configured.append("groq")
            elif (
                provider == "openrouter"
                and self._keys.get("openrouter")
                and "openrouter" not in configured
            ):
                configured.append("openrouter")
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
            f"## Knowledge-base context (dense RAG — prefer for CPCB/KSPCB/NCAP/WHO questions)\n"
            f"{kb_section}\n\n"
            f"## Available Tools\n{tools_section}\n\n"
            f"## Results So Far (step {step_number} of {max_steps})\n{results_section}\n\n"
            f"## Instructions\n"
            f"Respond with STRICT JSON ONLY. No prose, no markdown fences.\n"
            f"Choose exactly one format:\n"
            f'  {{"action": "call_tool", "tool": "<tool_name>", "arguments": {{...}}}}\n'
            f'  {{"action": "final_answer", "text": "<natural language answer>"}}\n\n'
            f"If the query involves regulations, guidelines, CPCB, KSPCB, NCAP, dust control, "
            f"or emission norms: use the knowledge-base context above AND call "
            f"tool_search_policy_guidance if not already present in Results So Far.\n"
            f"For enforcement priorities prefer tool_get_enforcement_priority.\n"
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
            if _circuit_open(provider):
                logger.info("Skipping %s (circuit open)", provider)
                continue
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

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> dict[str, Any] | None:
        """Native function-calling turn (OpenAI-compatible API).

        Returns:
          {
            "content": str | None,
            "tool_calls": [{"id", "name", "arguments": dict}, ...],
            "provider": str,
            "finish_reason": str | None,
          }
        or None if all providers fail.
        """
        if not self._available:
            return None

        # Prefer Groq for tool calling, then OpenRouter; Gemini text path is weaker here
        order: list[str] = []
        for p in ("groq", "openrouter", "gemini"):
            if p in self._providers and p not in order:
                order.append(p)
        for p in self._providers:
            if p not in order:
                order.append(p)

        for provider in order:
            if _circuit_open(provider):
                continue
            if provider == "groq" and self._groq_keys:
                result = self._chat_tools_groq(messages, tools, temperature, max_tokens)
                if result:
                    self.last_provider = "groq"
                    return result
            elif provider == "openrouter" and self._keys.get("openrouter"):
                result = self._chat_tools_openai_compatible(
                    api_key=self._keys["openrouter"],
                    base_url="https://openrouter.ai/api/v1",
                    model=self.openrouter_model or "openrouter/free",
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    provider_label="openrouter",
                )
                if result:
                    self.last_provider = "openrouter"
                    return result
            elif provider == "gemini" and self._gemini_keys:
                # Gemini: use OpenAI-compatible endpoint when available, else skip tools
                # Fall through to text-only is handled by agent fallback
                continue
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
        if not self._groq_keys:
            return None
        system_msg = system_prompt or _SUMMARIZER_SYSTEM_PROMPT
        user_content = f"{prompt}\n\nData:\n{json.dumps(structured_data, indent=2, default=str)}"
        for key_index, api_key in enumerate(self._groq_keys, start=1):
            if _circuit_open(f"groq:{key_index}"):
                continue
            try:
                import openai
                from openai import APITimeoutError

                client = openai.OpenAI(
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=20.0,
                )
                resp = client.chat.completions.create(
                    model=self.groq_model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.3,
                    max_tokens=800,
                )
                self.last_groq_key_index = key_index
                return resp.choices[0].message.content
            except ImportError:
                logger.warning("openai package not installed")
                return None
            except Exception as exc:
                msg = str(exc).lower()
                if "429" in msg or "rate" in msg or "quota" in msg:
                    _trip_circuit(f"groq:{key_index}", "rate_limit")
                    logger.warning("Groq key #%d rate-limited; trying next", key_index)
                    continue
                logger.warning("Groq key #%d call failed: %s", key_index, exc)
                continue
        _trip_circuit("groq", "all_keys_failed")
        return None

    def _chat_tools_groq(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any] | None:
        for key_index, api_key in enumerate(self._groq_keys, start=1):
            if _circuit_open(f"groq:{key_index}"):
                continue
            try:
                import openai

                client = openai.OpenAI(
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=35.0,
                )
                resp = client.chat.completions.create(
                    model=self.groq_model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                choice = resp.choices[0]
                msg = choice.message
                tool_calls: list[dict[str, Any]] = []
                if getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        args_raw = tc.function.arguments or "{}"
                        try:
                            args = json.loads(args_raw)
                        except json.JSONDecodeError:
                            args = {"_raw": args_raw}
                        tool_calls.append(
                            {
                                "id": tc.id,
                                "name": tc.function.name,
                                "arguments": args if isinstance(args, dict) else {"value": args},
                            }
                        )
                self.last_groq_key_index = key_index
                self.last_provider = "groq"
                return {
                    "content": msg.content,
                    "tool_calls": tool_calls,
                    "provider": "groq",
                    "finish_reason": choice.finish_reason,
                    "key_index": key_index,
                }
            except Exception as exc:
                msg = str(exc).lower()
                if "429" in msg or "rate" in msg or "quota" in msg:
                    _trip_circuit(f"groq:{key_index}", "rate_limit")
                    continue
                # Project-level model blocks — try lighter fallback model once
                if "blocked" in msg or "permission" in msg or "403" in msg:
                    for fallback_model in (
                        "openai/gpt-oss-120b",
                        "llama-3.1-8b-instant",
                        "llama-3.3-70b-versatile",
                    ):
                        if fallback_model == self.groq_model:
                            continue
                        try:
                            import openai as _oai

                            client2 = _oai.OpenAI(
                                api_key=api_key,
                                base_url="https://api.groq.com/openai/v1",
                                timeout=35.0,
                            )
                            resp2 = client2.chat.completions.create(
                                model=fallback_model,
                                messages=messages,
                                tools=tools,
                                tool_choice="auto",
                                temperature=temperature,
                                max_tokens=max_tokens,
                            )
                            choice = resp2.choices[0]
                            msg2 = choice.message
                            tool_calls = []
                            if getattr(msg2, "tool_calls", None):
                                for tc in msg2.tool_calls:
                                    args_raw = tc.function.arguments or "{}"
                                    try:
                                        args = json.loads(args_raw)
                                    except json.JSONDecodeError:
                                        args = {"_raw": args_raw}
                                    tool_calls.append(
                                        {
                                            "id": tc.id,
                                            "name": tc.function.name,
                                            "arguments": args
                                            if isinstance(args, dict)
                                            else {"value": args},
                                        }
                                    )
                            self.last_groq_key_index = key_index
                            self.last_provider = "groq"
                            self.groq_model = fallback_model
                            logger.info("Groq fallback model OK: %s", fallback_model)
                            return {
                                "content": msg2.content,
                                "tool_calls": tool_calls,
                                "provider": "groq",
                                "finish_reason": choice.finish_reason,
                                "key_index": key_index,
                                "model": fallback_model,
                            }
                        except Exception as exc2:
                            logger.warning(
                                "Groq fallback model %s failed: %s", fallback_model, exc2
                            )
                            continue
                logger.warning("Groq tools key #%d failed: %s", key_index, exc)
                continue
        return None

    def _chat_tools_openai_compatible(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        provider_label: str,
    ) -> dict[str, Any] | None:
        try:
            import openai
            import httpx

            http_client = httpx.Client(
                timeout=35.0, trust_env=not _has_broken_loopback_proxy()
            )
            try:
                client = openai.OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=35.0,
                    http_client=http_client,
                )
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                choice = resp.choices[0]
                msg = choice.message
                tool_calls: list[dict[str, Any]] = []
                if getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        args_raw = tc.function.arguments or "{}"
                        try:
                            args = json.loads(args_raw)
                        except json.JSONDecodeError:
                            args = {"_raw": args_raw}
                        tool_calls.append(
                            {
                                "id": tc.id,
                                "name": tc.function.name,
                                "arguments": args if isinstance(args, dict) else {"value": args},
                            }
                        )
                return {
                    "content": msg.content,
                    "tool_calls": tool_calls,
                    "provider": provider_label,
                    "finish_reason": choice.finish_reason,
                }
            finally:
                http_client.close()
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "rate" in msg:
                _trip_circuit(provider_label, "rate_limit")
            logger.warning("%s tools call failed: %s", provider_label, exc)
            return None


def get_llm_provider() -> LLMProvider:
    return LLMProvider()
