"""
LLM Integration for Octa Bot agents.

Provider is configured via config/providers.json.
Switch models by changing 'active' — no code changes needed.
"""

import logging

# Setup logger
logger = logging.getLogger("email_agent.llm_parser")
logger.setLevel(logging.DEBUG)

# Module-level singleton — populated lazily by get_llm_client()
_llm_client = None


class GitHubModelsLLM:
    """
    Octa Bot LLM client.

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

        # Add conversation history if provided (last 5 exchanges)
        # Strip to only role+content — extra fields (file_artifacts, search_paths,
        # ts, elapsed …) can push the request past the token limit.
        if conversation_history:
            for _h in conversation_history[-10:]:
                if isinstance(_h, dict) and "role" in _h and "content" in _h:
                    messages.append({"role": _h["role"], "content": _h["content"]})

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
