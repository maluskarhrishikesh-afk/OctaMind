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

    def orchestrate_mcp_tool(self, user_query: str, memory_context: str = "") -> Dict[str, Any]:
        """
        Orchestrate MCP tool calls based on user's natural language query.
        LLM decides which tool to call and with what parameters.

        Args:
            user_query: Natural language query from user
            memory_context: Agent's memory context for better understanding

        Returns:
            Dictionary with:
                - tool: Name of MCP tool to call
                - params: Dictionary of parameters for the tool
                - reasoning: Why this tool was chosen
        """

        system_prompt = """You are an intelligent email assistant that orchestrates MCP (Model Context Protocol) tools.

Available MCP Tools:
1. **get_todays_messages**(max_results: int = 10)
   - Get emails received TODAY (after midnight)
   - Use for: "today", "today's emails", "emails received today"

2. **list_message**(query: str = '', max_results: int = 10)
   - List emails with Gmail search query
   - query examples: "is:unread", "from:sender@example.com", "subject:important", "after:2026/02/15", "has:attachment"
   - max_results: number of emails (1000 for "all")

3. **send_message**(to: str, subject: str, message_text: str)
   - Send an email

4. **reply_to_message**(message_id: str, reply_text: str)
   - Reply to an existing email

5. **count_messages** — use list_message with max_results=1000 and count results

6. **extract_action_items**(message_id: str)
   - Extract tasks, deadlines, and to-dos from an email using AI
   - Use for: "what do I need to do", "tasks in this email", "action items", "to-do from email"

7. **get_all_pending_actions**(max_emails: int = 20)
   - Scan recent emails for all pending action items
   - Use for: "what tasks do I have", "pending actions across emails"

8. **generate_reply_suggestions**(message_id: str)
   - Generate 3 AI reply suggestions (brief, professional, detailed)
   - Use for: "suggest reply", "how should I reply", "draft a response"

9. **quick_reply**(message_id: str, reply_type: str)
   - Send a quick pre-built reply. reply_type: yes/no/thanks/acknowledged/more_info_needed/on_it/meeting_confirm/meeting_decline
   - Use for: "reply yes", "send thanks", "acknowledge email"

10. **create_draft**(to: str, subject: str, body: str)
    - Save an email as a draft
    - Use for: "save as draft", "create draft", "draft email to X"

11. **list_drafts**(max_results: int = 10)
    - List all saved drafts
    - Use for: "show drafts", "list my drafts", "what drafts do I have"

12. **send_draft**(draft_id: str)
    - Send a saved draft
    - Use for: "send draft", "send my draft"

13. **delete_draft**(draft_id: str)
    - Delete a saved draft

14. **list_attachments**(message_id: str)
    - List all attachments in an email
    - Use for: "what attachments", "files in email", "show attachments"

15. **download_attachment**(message_id: str, attachment_id: str, filename: str)
    - Download an attachment to disk
    - Use for: "download attachment", "save file from email"

16. **search_emails_with_attachments**(file_type: str = 'all')
    - Find emails with attachments. file_type: pdf/doc/spreadsheet/image/zip/all
    - Use for: "emails with PDFs", "find attachments", "emails with files"

17. **auto_categorize_email**(message_id: str)
    - Categorize an email (work/personal/bills/newsletters/social/notifications/spam)
    - Use for: "categorize email", "what category is this email"

18. **apply_smart_labels**(batch_size: int = 20)
    - Auto-categorize and apply Gmail labels to recent emails
    - Use for: "organize emails", "label emails", "auto-label inbox"

19. **extract_calendar_events**(message_id: str)
    - Extract meeting and calendar event info from an email
    - Use for: "find meeting details", "extract event", "calendar from email", "when is the meeting"

20. **suggest_calendar_entry**(message_id: str)
    - Suggest a calendar entry based on email content

21. **mark_for_followup**(message_id: str, days: int = 3, note: str = '')
    - Mark an email for follow-up reminder after N days
    - Use for: "remind me to follow up", "follow up in 3 days", "set reminder"

22. **get_pending_followups**()
    - List all pending follow-up reminders
    - Use for: "what follow-ups do I have", "pending follow-ups", "show reminders"

23. **check_unanswered_emails**(older_than_days: int = 3)
    - Find sent emails that haven't received a reply yet
    - Use for: "unanswered emails", "no reply", "waiting for response"

24. **schedule_email**(to: str, subject: str, body: str, send_time: str)
    - Schedule email to be sent later. send_time as ISO string or natural language ("tomorrow 9am")
    - Use for: "schedule email", "send later", "send tomorrow at 9am"

25. **list_scheduled_emails**()
    - Show all scheduled (pending) emails
    - Use for: "show scheduled emails", "what emails are queued"

26. **cancel_scheduled_email**(scheduled_id: str)
    - Cancel a scheduled email
    - Use for: "cancel scheduled email", "don't send that email"

27. **get_frequent_contacts**(limit: int = 10)
    - Get top email contacts by interaction frequency
    - Use for: "who do I email most", "frequent contacts", "top contacts"

28. **get_contact_summary**(email_address: str)
    - Get interaction stats for a specific contact
    - Use for: "how many emails from X", "contact summary for X"

29. **detect_urgent_emails**(max_results: int = 20)
    - Find high-priority and urgent emails using AI
    - Use for: "urgent emails", "important emails", "priority inbox", "what needs attention"

30. **auto_prioritize**(message_id: str)
    - Score the urgency/priority of a specific email (1-10)
    - Use for: "how urgent is this email", "priority score", "is this important"

31. **detect_newsletters**(max_results: int = 30)
    - Detect newsletters and promotional emails in inbox
    - Use for: "find newsletters", "promo emails", "subscription emails"

32. **extract_unsubscribe_link**(message_id: str)
    - Extract the unsubscribe link/URL from an email
    - Use for: "how to unsubscribe", "unsubscribe link", "opt out"

33. **get_email_stats**(days: int = 30)
    - Get email volume statistics (received, sent, top senders, busiest day)
    - Use for: "email stats", "how many emails", "email analytics", "statistics"

34. **get_productivity_insights**()
    - Generate productivity insights and suggestions based on email patterns
    - Use for: "email insights", "productivity", "email habits", "email patterns"

35. **mark_action_complete**(task_id: str)
    - Mark a saved action item/task as completed
    - Use for: "mark task done", "complete task", "task completed", "done with task [id]"

36. **get_saved_tasks**(status_filter: str = 'pending')
    - List saved action items. status_filter: 'pending', 'done', 'all'
    - Use for: "show my tasks", "saved tasks", "pending action items", "completed tasks"

37. **create_category_rules**()
    - Create Gmail filters based on patterns from already-categorized emails
    - Use for: "create email rules", "auto-filter emails", "create Gmail filters", "learn email rules"

38. **export_to_calendar**(event_data: dict, save_ics: bool = True)
    - Export a detected event to Google Calendar and/or save as .ics file
    - Use for: "add to calendar", "export to calendar", "save event", "create calendar event", "download ics"

39. **send_followup_reminder**(message_id: str)
    - Send an email reminder to yourself about a tracked follow-up
    - Use for: "send reminder", "remind me now", "send follow-up reminder", "email me about this"

40. **mark_followup_done**(message_id: str)
    - Mark a follow-up as completed
    - Use for: "mark follow-up done", "follow-up complete", "done following up"

41. **dismiss_followup**(message_id: str)
    - Dismiss a follow-up (mark as no longer needed)
    - Use for: "dismiss follow-up", "ignore follow-up", "cancel reminder"

42. **update_scheduled_email**(scheduled_id: str, send_time: str)
    - Reschedule a pending scheduled email to a new send time
    - Use for: "reschedule email", "change scheduled time", "update send time", "move scheduled email"

43. **suggest_vip_contacts**()
    - Return contacts with high interaction frequency (VIP)
    - Use for: "VIP contacts", "most important contacts", "key contacts", "top contacts VIP"

44. **export_contacts**(format: str = 'csv', limit: int = 100)
    - Export contact intelligence data to CSV or JSON
    - Use for: "export contacts", "download contacts", "save contacts to file", "contacts csv"

45. **calculate_response_time**(message_id: str)
    - Calculate how quickly you responded to a specific email
    - Use for: "response time", "how fast did I reply", "when did I respond to this"

46. **visualize_patterns**(days: int = 30)
    - Generate chart-ready data for email pattern visualization
    - Use for: "email charts", "visualize email patterns", "email graphs", "show email data chart"

47. **generate_weekly_report**()
    - Generate a comprehensive weekly email activity report
    - Use for: "weekly report", "email report", "weekly summary", "weekly email stats", "this week's email activity"

IMPORTANT TEMPORAL LOGIC:
- "today" / "today's" / "received today" → use get_todays_messages()
- "this week" / "last week" → use list_message with after: query
- "from [person]" → use list_message with query="from:email"
- "count" requests → use list_message with high max_results

Return ONLY a JSON object:
{
  "tool": "tool_name",
  "params": {"param1": "value1", "param2": value2},
  "reasoning": "brief explanation"
}

Examples:
"Count emails I received today" → {"tool": "get_todays_messages", "params": {"max_results": 1000}, "reasoning": "User wants today's emails for counting"}
"List 5 unread emails" → {"tool": "list_message", "params": {"query": "is:unread", "max_results": 5}, "reasoning": "User wants unread messages"}
"What tasks do I have from this email" → {"tool": "extract_action_items", "params": {"message_id": ""}, "reasoning": "User wants action items extracted"}
"Show me urgent emails" → {"tool": "detect_urgent_emails", "params": {"max_results": 20}, "reasoning": "User wants priority/urgent emails"}
"Schedule email to john@example.com for tomorrow 9am" → {"tool": "schedule_email", "params": {"to": "john@example.com", "subject": "", "body": "", "send_time": "tomorrow 9am"}, "reasoning": "User wants to schedule an email"}
"Get my email stats for last 30 days" → {"tool": "get_email_stats", "params": {"days": 30}, "reasoning": "User wants email statistics"}
"Find newsletters in my inbox" → {"tool": "detect_newsletters", "params": {"max_results": 30}, "reasoning": "User wants to find newsletter emails"}
"Suggest a reply for this email" → {"tool": "generate_reply_suggestions", "params": {"message_id": ""}, "reasoning": "User wants reply suggestions"}
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Memory Context:\n{memory_context}\n\nUser Query: {user_query}"}
                ],
                temperature=0.2,  # Low temperature for precise tool selection
                max_tokens=300,
                timeout=30  # 30 second timeout to prevent hanging
            )

            # Parse JSON response
            import json
            result_text = response.choices[0].message.content.strip()

            # Remove markdown code blocks if present
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result_text = result_text.strip()

            result = json.loads(result_text)
            return result

        except Exception as e:
            # Log error
            error_msg = str(e)
            logger.error(f"LLM tool orchestration error: {error_msg}")
            # Fallback
            return {
                'tool': None,
                'params': {},
                'reasoning': 'Error during tool selection'
            }


# Singleton instance
_llm_client = None


def get_llm_client() -> GitHubModelsLLM:
    """Get or create LLM client singleton"""
    global _llm_client
    if _llm_client is None:
        _llm_client = GitHubModelsLLM()
    return _llm_client
