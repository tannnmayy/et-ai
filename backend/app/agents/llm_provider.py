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
            raw = self._call_llm(prompt, {})
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
