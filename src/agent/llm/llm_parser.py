"""
LLM Integration for OctaMind agents.

Provider is configured via config/providers.json.
Switch models by changing 'active' — no code changes needed.
"""

import logging
from typing import Dict, Any

# Setup logger
logger = logging.getLogger("email_agent.llm_parser")
logger.setLevel(logging.DEBUG)


class GitHubModelsLLM:
    """
    OctaMind LLM client.

    Supports any provider registered in config/providers.json:
      - openai_compatible  (GitHub Models, OpenAI, Ollama, LM Studio, llama.cpp, vLLM, …)
      - anthropic          (Claude 3.5 Sonnet / Haiku)
      - local_hf           (Gemma 3 4B — default; any cached HuggingFace model)

    Switch the active provider by changing ``active`` in config/providers.json
    or calling ``src.agent.llm.provider_registry.set_active_provider(name)``.
    """

    def __init__(self):
        from src.agent.llm.provider_registry import build_client
        self.client, self.model, self.provider_type = build_client()
        logger.info(
            "LLM client initialised — provider_type=%s  model=%s",
            self.provider_type, self.model,
        )

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

6. **Consciousness (Meta Layer)** - High-level strategic understanding
   - User's long-term goals and evolution
   - Core pattern recognition across all interactions

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
✅ Your consciousness layer updates automatically every 2-4 weeks

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
"""

        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history if provided (last 5 exchanges)
        if conversation_history:
            # Last 5 exchanges (10 messages)
            messages.extend(conversation_history[-10:])

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,  # Balanced creativity and consistency
                max_tokens=300,
                timeout=30  # 30 second timeout to prevent hanging
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            # Log error
            logger.error(f"LLM chat error: {str(e)}")
            err_str = str(e)
            if "429" in err_str or "RateLimitReached" in err_str or "rate limit" in err_str.lower():
                import re as _re
                wait_match = _re.search(r"wait (\d+) seconds", err_str)
                wait_msg = f" Please wait {int(wait_match.group(1)) // 60} minutes before retrying." if wait_match and int(wait_match.group(1)) > 60 else " Please try again shortly."
                return f"⏳ **API rate limit reached.**{wait_msg}"
            return f"I'm having trouble processing that right now. As {agent_name}, I'm here to help - could you try rephrasing?"

    def classify_intent(self, user_message: str, agent_context: str = None) -> str:
        """
        Classify whether a user message is a tool command or casual
        conversation.  Deliberately uses a tiny prompt and max_tokens=5 to
        minimise latency and cost.

        Parameters
        ----------
        user_message : str
            The raw user input to classify.
        agent_context : str, optional
            One-sentence description of what counts as a COMMAND for this agent.
            Defaults to an email-agent description when omitted.

        Returns
        -------
        "COMMAND"  — message needs tool execution
        "CHAT"     — message is casual conversation / memory recall / greeting
        """
        if agent_context is None:
            agent_context = (
                "reading, counting, sending, deleting, searching, scheduling, "
                "or otherwise interacting with the user's email inbox, drafts, "
                "contacts, labels, or attachments"
            )
        system_prompt = (
            "You are a router for an AI agent.\n"
            f"Decide if the user message is a COMMAND that requires {agent_context},\n"
            "OR a CASUAL CONVERSATION (greetings, memory questions, general chat,\n"
            "questions about what was discussed before, jokes, etc.).\n"
            "Reply with EXACTLY one word: COMMAND or CHAT.  No punctuation."
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,
                max_tokens=5,
                timeout=10,
            )
            result = response.choices[0].message.content.strip().upper()
            # Guard against unexpected model output
            if "COMMAND" in result:
                return "COMMAND"
            return "CHAT"
        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            # On failure, fall back to treating as COMMAND so nothing is silently dropped
            return "COMMAND"

    def reason_and_act(
        self,
        user_query: str,
        tools_description: str,
        tool_executor,
        memory_context: str = "",
        max_iterations: int = 6,
    ) -> str:
        """
        Thought-Action-Observation loop (ReAct pattern).

        The LLM reasons freely, calls tools, observes results, and repeats
        until it has enough information to write a final answer.  This means
        multi-step tasks ("reply to the most recent email from John") work
        correctly: the LLM lists emails first, gets the ID from the
        observation, then calls reply — all in one coherent reasoning chain.

        Parameters
        ----------
        user_query      : Natural language task from the user.
        tools_description: Full tools list (same string passed to orchestrate_mcp_tool).
        tool_executor   : callable(tool_name: str, params: dict) -> str
                          Runs the actual tool and returns a readable observation.
        memory_context  : Memory context string (optional).
        max_iterations  : Hard cap on reasoning steps to prevent infinite loops.

        Returns
        -------
        str  Final answer string in markdown, ready for display.
        """
        import json as _json

        system_prompt = (
            "You are an intelligent AI agent. You solve tasks step by step by "
            "reasoning and calling tools.\n\n"
            "RESPONSE FORMAT — always respond with a JSON object, never plain text:\n\n"
            "To call a tool:\n"
            '{"thought": "what I\'m reasoning about", '
            '"action": "tool_name", "params": {"key": "value"}}\n\n'
            "When you have enough information to answer the user:\n"
            '{"thought": "I now have everything needed", '
            '"final_answer": "your complete, helpful, markdown-formatted response"}\n\n'
            "RULES:\n"
            "- Use final_answer as soon as you have the information needed — "
            "do not make unnecessary tool calls.\n"
            "- If a tool returns an error, try a different approach or explain "
            "the issue in final_answer.\n"
            "- Never call the same tool twice with identical params.\n"
            "- When listing emails, always include IDs in your final_answer so "
            "the user can reference them.\n"
            "- Write final_answer in friendly markdown — use bold, bullet lists, "
            "and emojis where appropriate.\n\n"
            "Available tools:\n"
            + tools_description
        )

        messages = [{"role": "system", "content": system_prompt}]

        user_content = f"Task: {user_query}"
        if memory_context:
            user_content = f"Memory Context:\n{memory_context}\n\nTask: {user_query}"
        messages.append({"role": "user", "content": user_content})

        for iteration in range(max_iterations):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=3000,
                    timeout=45,
                )
                raw = response.choices[0].message.content.strip()

                # Strip markdown code fences if present
                if raw.startswith("```"):
                    parts = raw.split("```")
                    raw = parts[1] if len(parts) > 1 else raw
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()

                parsed = _json.loads(raw)

            except _json.JSONDecodeError:
                # LLM produced non-JSON — treat the raw text as the final answer
                logger.warning("[ReAct] Non-JSON response, using as final answer")
                return raw
            except Exception as e:
                logger.error(f"[ReAct] LLM call error on iteration {iteration}: {e}")
                err_str = str(e)
                if "429" in err_str or "RateLimitReached" in err_str or "rate limit" in err_str.lower():
                    # Extract wait time if present
                    import re as _re
                    wait_match = _re.search(r"wait (\d+) seconds", err_str)
                    wait_msg = f" Please wait {int(wait_match.group(1)) // 60} minutes before retrying." if wait_match and int(wait_match.group(1)) > 60 else " Please try again shortly."
                    return f"⏳ **API rate limit reached.**{wait_msg}"
                break

            # ── Final answer ─────────────────────────────────────────────────
            if "final_answer" in parsed:
                logger.debug(
                    f"[ReAct] Final answer after {iteration + 1} iteration(s)")
                return parsed["final_answer"]

            # ── Tool call ────────────────────────────────────────────────────
            tool_name = parsed.get("action", "")
            params = parsed.get("params", {})
            thought = parsed.get("thought", "")

            logger.debug(
                f"[ReAct] iter={iteration + 1} | thought={thought[:80]!r} | "
                f"action={tool_name!r} | params={params}"
            )

            if not tool_name:
                logger.warning("[ReAct] No action in response, stopping loop")
                break

            try:
                observation = tool_executor(tool_name, params)
            except Exception as exc:
                observation = f"Tool execution error: {exc}"

            logger.debug(f"[ReAct] Observation: {observation[:300]!r}")

            # Feed the thought+action and observation back into the conversation
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Observation from {tool_name}:\n{observation}",
            })

        # Exhausted iterations or loop broken — ask LLM for a best-effort answer
        try:
            messages.append({
                "role": "user",
                "content": (
                    "You have reached the maximum reasoning steps. "
                    "Provide the best final_answer you can with what you have observed so far. "
                    'Respond with {"thought": "...", "final_answer": "..."}'
                ),
            })
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=3000,
                timeout=30,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1][4:].strip() if len(parts) > 1 else raw
            try:
                parsed = _json.loads(raw)
                return parsed.get("final_answer", raw)
            except _json.JSONDecodeError:
                # LLM returned plain text — use it as-is
                return raw
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RateLimitReached" in err_str or "rate limit" in err_str.lower():
                import re as _re
                wait_match = _re.search(r"wait (\d+) seconds", err_str)
                wait_msg = f" Please wait {int(wait_match.group(1)) // 60} minutes before retrying." if wait_match and int(wait_match.group(1)) > 60 else " Please try again shortly."
                return f"⏳ **API rate limit reached.**{wait_msg}"
            return (
                "I wasn't able to fully complete that task. "
                "Please try rephrasing or break it into smaller steps."
            )

    def orchestrate_mcp_tool(
        self,
        user_query: str,
        memory_context: str = "",
        tools_description: str = None,
    ) -> Dict[str, Any]:
        """
        Orchestrate MCP tool calls based on user's natural language query.
        LLM decides which tool to call and with what parameters.

        Args:
            user_query: Natural language query from user
            memory_context: Agent's memory context for better understanding
            tools_description: Optional custom tool list (overrides the default email tools).
                When provided the system prompt is built from this description instead of
                the hardcoded Gmail tools so the same method can drive any agent type.

        Returns:
            Dictionary with:
                - tool: Name of MCP tool to call
                - params: Dictionary of parameters for the tool
                - reasoning: Why this tool was chosen
        """

        # Guard: every caller must supply their own agent-specific tool list.
        if tools_description is None:
            logger.warning(
                "orchestrate_mcp_tool called without tools_description. "
                "Callers must pass their agent-specific tool list."
            )
            return {"tool": None, "params": {}, "reasoning": "No tools_description provided"}

        system_prompt = (
            "You are an intelligent AI assistant that orchestrates tools via MCP "
            "(Model Context Protocol).\n\n"
            "Available Tools:\n"
            + tools_description
            + "\n\nReturn ONLY a JSON object:\n"
            '{\n  "tool": "tool_name",\n  "params": {"param1": "value1"},\n'
            '  "reasoning": "brief explanation"\n}\n'
            "Do NOT include any other text."
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Memory Context:\n{memory_context}\n\nUser Query: {user_query}"}
                ],
                temperature=0.2,
                max_tokens=300,
                timeout=30,
            )
            import json
            result_text = response.choices[0].message.content.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result_text = result_text.strip()
            return json.loads(result_text)
        except Exception as e:
            logger.error(f"LLM tool orchestration error: {e}")
            return {"tool": None, "params": {}, "reasoning": "Error during tool selection"}


# Singleton instance — reset to None by set_active_provider() when the provider changes
_llm_client = None


def get_llm_client() -> GitHubModelsLLM:
    """
    Return the shared LLM client.

    The client is built once per process and cached.  Calling
    ``provider_registry.set_active_provider(name)`` resets ``_llm_client``
    so the next call here rebuilds with the new provider.
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = GitHubModelsLLM()
    return _llm_client
