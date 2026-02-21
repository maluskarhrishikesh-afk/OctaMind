"""
LLM Integration for Email Agent using GitHub Models

This module provides LLM-orchestrated tool calling for intelligent email operations.
"""

import os
import logging
from typing import Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Setup logger
logger = logging.getLogger("email_agent.llm_parser")
logger.setLevel(logging.DEBUG)


class GitHubModelsLLM:
    """LLM client using GitHub Models API"""

    def __init__(self):
        """Initialize GitHub Models client"""
        self.token = os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN not found in environment variables")

        self.client = OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=self.token
        )

        # Use GPT-4o mini - fast and intelligent
        self.model = "gpt-4o-mini"

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
            # Fallback response
            return f"I'm having trouble processing that right now. As {agent_name}, I'm here to help - could you try rephrasing?"

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


# Singleton instance
_llm_client = None


def get_llm_client() -> GitHubModelsLLM:
    """Get or create LLM client singleton"""
    global _llm_client
    if _llm_client is None:
        _llm_client = GitHubModelsLLM()
    return _llm_client
