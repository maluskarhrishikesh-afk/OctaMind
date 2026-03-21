"""
LLM Integration for Octa Bot agents.

Provider is configured via config/providers.json.
Switch models by changing 'active' — no code changes needed.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

# Setup logger
logger = logging.getLogger("email_agent.llm_parser")
logger.setLevel(logging.DEBUG)

# Module-level singleton — populated lazily by get_llm_client()
_llm_client = None
_provider_clients: dict[str, "GitHubModelsLLM"] = {}

_LOCAL_FALLBACK_TOKEN_CAPS = {
    "routing": 48,
    "intent_classification": 64,
    "agent_planning": 96,
    "dag_planning": 192,
    "skill_dag_planning": 224,
    "nl_workflow_planning": 224,
}

_LOCAL_PROVIDER_NAMES = {
    "ollama",
    "ollama_qwen_fast",
    "ollama_llama3",
    "lmstudio",
    "custom",
    "gemma3_local",
}

_LOCAL_TIMEOUT_BY_PURPOSE = {
    "routing": 240,
    "intent_classification": 240,
    "agent_planning": 300,
    "dag_planning": 420,
    "skill_dag_planning": 420,
    "nl_workflow_planning": 420,
    "general": 180,
}


def _is_retryable_llm_error(exc: Exception) -> bool:
    text = str(exc).lower()
    retryable_markers = (
        "429",
        "rate limit",
        "ratelimitreached",
        "too many requests",
    )
    return any(marker in text for marker in retryable_markers)


def _fallback_reason(exc: Exception) -> str:
    text = str(exc).lower()
    if "429" in text or "rate limit" in text or "ratelimitreached" in text:
        return "rate_limit"
    if "timeout" in text or "timed out" in text or "gateway timeout" in text:
        return "timeout"
    return "transient_error"


def _get_planner_fallback_provider_name() -> str:
    from src.agent.llm.provider_registry import load_provider_config

    config = load_provider_config()
    if config.get("planner_fallback_enabled", True) is False:
        return ""

    provider_name = str(config.get("planner_fallback_model", "ollama") or "").strip()
    providers = config.get("providers", {})
    if provider_name and provider_name in providers:
        return provider_name
    return ""


def _cap_local_fallback_tokens(purpose: str, max_tokens: int) -> int:
    cap = _LOCAL_FALLBACK_TOKEN_CAPS.get(purpose)
    if cap is None:
        return max_tokens
    return min(max_tokens, cap)


def _strip_markdown_code_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _is_local_provider_name(provider_name: str) -> bool:
    return str(provider_name or "").strip().lower() in _LOCAL_PROVIDER_NAMES


def _effective_timeout(provider_name: str, purpose: str, requested_timeout: int) -> int:
    timeout = max(int(requested_timeout or 0), 1)
    if not _is_local_provider_name(provider_name):
        return timeout
    local_timeout = _LOCAL_TIMEOUT_BY_PURPOSE.get(str(purpose or "general").strip().lower())
    if local_timeout is None:
        local_timeout = _LOCAL_TIMEOUT_BY_PURPOSE["general"]
    return max(timeout, int(local_timeout))


class GitHubModelsLLM:
    """
    Octa Bot LLM client.

    Supports any provider registered in config/providers.json:
      - openai_compatible  (GitHub Models, OpenAI, Ollama, LM Studio, llama.cpp, vLLM, …)
      - anthropic          (Claude 3.5 Sonnet / Haiku)
    - local_hf           (locally cached HuggingFace model)

    Switch the active provider by changing ``active`` in config/providers.json
    or calling ``src.agent.llm.provider_registry.set_active_provider(name)``.
    """

    def __init__(self, provider_name: Optional[str] = None):
        from src.agent.llm.provider_registry import build_client, get_active_provider

        self.provider_name = provider_name or get_active_provider()
        self.client, self.model, self.provider_type = build_client(provider_name=provider_name)
        logger.info(
            "LLM client initialised — provider=%s  provider_type=%s  model=%s",
            self.provider_name, self.provider_type, self.model,
        )

    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int = 300,
        timeout: int = 40,
        purpose: str = "general",
        allow_local_fallback: bool = False,
    ) -> Any:
        effective_timeout = _effective_timeout(self.provider_name, purpose, timeout)
        try:
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=effective_timeout,
            )
        except Exception as exc:
            fallback_provider = _get_planner_fallback_provider_name()
            if (
                not allow_local_fallback
                or not _is_retryable_llm_error(exc)
                or not fallback_provider
                or fallback_provider == self.provider_name
            ):
                raise

            fallback_llm = get_llm_client(provider_name=fallback_provider)
            fallback_max_tokens = _cap_local_fallback_tokens(purpose, max_tokens)
            fallback_temperature = 0.0 if temperature <= 0.2 else min(temperature, 0.2)
            fallback_timeout = max(effective_timeout, 300)

            logger.warning(
                "Planner fallback to local model — purpose=%s primary=%s fallback=%s reason=%s max_tokens=%d→%d",
                purpose,
                self.provider_name,
                fallback_provider,
                _fallback_reason(exc),
                max_tokens,
                fallback_max_tokens,
            )
            try:
                from src.agent.telemetry import log_counter

                log_counter(
                    "llm_local_fallback",
                    purpose=purpose,
                    primary_provider=self.provider_name,
                    fallback_provider=fallback_provider,
                    reason=_fallback_reason(exc),
                )
            except Exception:
                pass

            return fallback_llm.client.chat.completions.create(
                model=fallback_llm.model,
                messages=messages,
                temperature=fallback_temperature,
                max_tokens=fallback_max_tokens,
                timeout=fallback_timeout,
            )

    def orchestrate_mcp_tool(
        self,
        user_query: str,
        memory_context: str = "",
        *,
        tools_description: str = "",
    ) -> dict[str, Any]:
        if not str(tools_description or "").strip():
            return {
                "tool": None,
                "params": {},
                "reasoning": "No tools_description provided for MCP orchestration.",
            }

        system_prompt = (
            "You are an MCP tool orchestrator. Choose exactly one tool from the provided tool list "
            "and return only valid JSON with keys tool, params, and reasoning.\n\n"
            "Available tools:\n"
            f"{tools_description.strip()}"
        )
        user_prompt = (
            f"User request: {str(user_query or '').strip()}\n\n"
            "Memory context:\n"
            f"{memory_context.strip() if memory_context else 'No prior memory available.'}"
        )

        try:
            response = self.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=300,
                timeout=40,
            )
            content = response.choices[0].message.content if response and response.choices else ""
            payload = json.loads(_strip_markdown_code_fence(str(content or "")))
        except Exception as exc:
            logger.warning("MCP tool orchestration failed: %s", exc)
            return {
                "tool": None,
                "params": {},
                "reasoning": f"MCP orchestration failed: {exc}",
            }

        if not isinstance(payload, dict):
            return {
                "tool": None,
                "params": {},
                "reasoning": "MCP orchestration returned a non-object payload.",
            }

        tool_name = payload.get("tool")
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        reasoning = str(payload.get("reasoning", "") or "")
        return {
            "tool": tool_name if tool_name else None,
            "params": params,
            "reasoning": reasoning,
        }

    def chat(
        self,
        user_message: str,
        agent_name: str = "AI Assistant",
        agent_type: str = "assistant",
        memory_context: str = "",
        conversation_history: list = None
    ) -> str:
        """
        Generate conversational response using LLM with memory context

        Args:
            user_message: User's message
            agent_name: Name of the agent
            agent_type: Type of agent (email, calendar, etc.)
            memory_context: Memory context from agent_memory
            conversation_history: Previous messages in format [{"role": "user"/"assistant", "content": "..."}]

        Returns:
            LLM-generated response
        """
        # Build system prompt with personality and memory
        system_prompt = f"""You are {agent_name}, an AI {agent_type} agent with a cognitive memory system.

Your personality:
- Professional yet friendly and approachable
- Clear, concise, and helpful in responses
- Proactive in offering assistance
- Remember past interactions and adapt to user preferences

Memory Context:
{memory_context if memory_context else "No prior memory available."}

Memory System Guidelines:
You have access to a multi-layer memory system with the following components:

1. **Working Memory (Short-Term)** - Your current context and recent interactions (last 5-10)
   - Like RAM - limited, frequently updated
   - Use this for immediate context about ongoing tasks

2. **Episodic Memory (Events)** - Important past experiences and conversations
   - Time-stamped events with importance levels (High/Medium/Low)
   - Reference specific past events when relevant

3. **Semantic Memory (Knowledge)** - Distilled knowledge about the user
   - User preferences, interests, technical background
   - Not raw logs - synthesized understanding

4. **Personality** - Your core behavioral traits and communication style
   - Stable identity that guides your responses
   - How you should interact with this specific user

5. **Habits** - Learned patterns from repeated interactions
   - Communication patterns, work routines
   - Only formed after 3+ confirmations of a pattern

6. **Self Reflection (Meta Layer)** - High-level strategic understanding
   - User's long-term goals and evolution
   - Core pattern recognition across all interactions
   - Lessons learned from past strategies (what worked, what didn't)

Memory Usage Principles:
- Draw from ALL relevant memory layers when responding
- Reference specific past interactions when they add value
- Adapt your responses based on learned user preferences
- Connect current conversation to long-term patterns
- Be memory-aware: acknowledge continuity in your relationship with the user

IMPORTANT - Memory Management Rules:
⚠️ You CANNOT and should NOT try to manually update memory files
✅ Memory consolidation happens AUTOMATICALLY in the background
✅ Your interactions are automatically recorded in working memory
✅ Patterns are automatically extracted and stored in semantic memory
✅ Habits are automatically detected after 3+ confirmations
✅ Old memories decay automatically after 90 days based on importance
✅ Your self reflection layer updates automatically every 2-4 weeks

What This Means For You:
- Focus on having natural conversations - memory management is handled for you
- Just BE yourself according to your personality - your habits will be learned
- Reference memory naturally ("I remember when...", "Based on your preference for...")
- DON'T say things like "I'll update my memory" or "I'm storing this information"
- DO acknowledge when you notice patterns ("I've noticed you often ask about...")
- The more consistent your personality, the better your memory will consolidate

Guidelines:
- Use natural, conversational language
- Reference previous interactions when relevant (e.g., "Last time you mentioned...")
- Be helpful but honest about your capabilities
- For action requests, acknowledge and guide the user
- Use appropriate emojis moderately (1-2 per response)
- Keep responses focused and not overly long (2-4 sentences usually)

Follow-up Suggestions:
After EVERY response (including pure conversation), end with a short section:
  "**You could also ask me to:**"
  followed by 2-3 bullet points of actionable follow-up suggestions that are
  contextually relevant to what you just did or discussed.
  Examples of suggestion format:
    - "Find another file on your laptop"
    - "Mail the found file to you"
    - "Schedule a reminder for later"
    - "Check your unread emails"
  Keep each suggestion to one short line. Never suggest something you already just did.
"""

        messages = [{"role": "system", "content": system_prompt}]
        is_local_provider = _is_local_provider_name(self.provider_name)
        history_limit = 4 if is_local_provider else 10

        # Add conversation history if provided (last 5 exchanges)
        # Strip to only role+content — extra fields (file_artifacts, search_paths,
        # ts, elapsed …) can push the request past the token limit.
        if conversation_history:
            for _h in conversation_history[-history_limit:]:
                if isinstance(_h, dict) and "role" in _h and "content" in _h:
                    messages.append({"role": _h["role"], "content": _h["content"]})

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        try:
            response = self.create_chat_completion(
                messages=messages,
                temperature=0.7,  # Balanced creativity and consistency
                max_tokens=160,
                timeout=180 if is_local_provider else 30,
                purpose="general",
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            # Log error
            logger.error("LLM chat error: %s", e)
            err_str = str(e)
            if "429" in err_str or "RateLimitReached" in err_str or "rate limit" in err_str.lower():
                import re as _re
                wait_match = _re.search(r"wait (\d+) seconds", err_str)
                wait_msg = f" Please wait {int(wait_match.group(1)) // 60} minutes before retrying." if wait_match and int(wait_match.group(1)) > 60 else " Please try again shortly."
                return f"⏳ **API rate limit reached.**{wait_msg}"
            return f"I'm having trouble processing that right now. As {agent_name}, I'm here to help - could you try rephrasing?"


def request_completion(
    *,
    llm: Optional[Any] = None,
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: int = 300,
    timeout: int = 40,
    purpose: str = "general",
    allow_local_fallback: bool = False,
) -> Any:
    llm_client = llm or get_llm_client()
    if isinstance(llm_client, GitHubModelsLLM):
        return llm_client.create_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            purpose=purpose,
            allow_local_fallback=allow_local_fallback,
        )
    return llm_client.client.chat.completions.create(
        model=llm_client.model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def get_llm_client(provider_name: Optional[str] = None) -> GitHubModelsLLM:
    """
    Return the shared LLM client.

    The client is built once per process and cached.  Calling
    ``provider_registry.set_active_provider(name)`` resets ``_llm_client``
    so the next call here rebuilds with the new provider.
    """
    global _llm_client

    if provider_name:
        cached = _provider_clients.get(provider_name)
        if cached is None:
            cached = GitHubModelsLLM(provider_name=provider_name)
            _provider_clients[provider_name] = cached
        return cached

    if _llm_client is None:
        _llm_client = GitHubModelsLLM()
    return _llm_client
