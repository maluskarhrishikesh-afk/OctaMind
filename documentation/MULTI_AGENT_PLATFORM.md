# Multi-Agent Platform - Product Overview

## 🎯 Vision

A modular AI platform where users can create and manage multiple specialized agents for different services (Gmail, Google Drive, Slack, Calendar, etc.). Each agent understands natural language and performs automated tasks within its domain.

## 🏗️ Architecture

### Core Components

1. **Agent Hub Dashboard** - `src/agent/ui/dashboard/`
   - Central management interface
   - Create, view, configure, and delete agents
   - Real-time agent statistics
   - Launch agent-specific UIs

2. **Agent Manager** - `src/agent/agent_manager.py`
   - CRUD operations for agents
   - Agent lifecycle management
   - JSON-based storage (`agents.json`)
   - Agent type templates and metadata

3. **Agent Types**:
   - **📧 Gmail Agent**: Email management (send, list, delete, count, search)
   - **📁 Google Drive Agent**: File and folder management
   - **💬 Slack Agent**: Team communication
   - **📅 Calendar Agent**: Event scheduling
   - **🔧 Custom Agent**: User-defined capabilities

4. **LLM Parser** - `src/agent/llm_parser.py`
   - Natural language command understanding
   - GitHub Models API integration (GPT-4o mini)
   - Fallback to rule-based parsing

## 🚀 Getting Started

### Launch the Agent Hub

```bash
# Using launcher script
python run_agent_hub.py

# Or directly
python -m streamlit run src/agent/agent_dashboard.py
```

Open browser to: **http://localhost:8501**

### Create Your First Agent

1. Click the **"➕ Create New Agent"** button
2. Fill in the form:
   - **Name**: What should your agent be called? (e.g., "My Email Assistant")
   - **Type**: Choose from templates (Gmail, Drive, Slack, Calendar) or Custom
   - **Role**: Describe what the agent should do (e.g., "Keep my inbox organized and delete spam")
3. Configure advanced options (optional):
   - Auto-run on startup
   - Max operations per command
4. Click **"✨ Create Agent"**

### Using an Agent

1. From the dashboard, click **"🚀 Open"** on any agent card
2. Agent-specific UI opens (separate window/port)
3. Type natural language commands:
   - "Delete all emails from LinkedIn"
   - "Send email to john@example.com with subject Test"
   - "Show me 10 unread messages"

## 📝 Agent Storage

Agents are stored in `agents.json`:

```json
{
  "agents": [
    {
      "id": "a7f3e2c1",
      "name": "My Email Assistant",
      "type": "gmail",
      "role": "Keep my inbox clean and organized",
      "created_at": "2026-02-18T23:00:00",
      "enabled": true,
      "config": {
        "auto_run": false,
        "max_operations": 100
      },
      "metadata": {
        "name": "Gmail Agent",
        "description": "Manage emails, send messages, and organize inbox",
        "icon": "📧",
        "capabilities": ["send", "list", "delete", "count", "search"]
      }
    }
  ]
}
```

## 🎨 Features

### Dashboard Features
- ✅ Create unlimited agents
- ✅ View all agents in card grid
- ✅ Search and filter agents
- ✅ Real-time statistics (total agents, active agents, by type)
- ✅ Quick actions (create, open, configure, delete)
- ✅ Visual status indicators

### Agent Creation
- ✅ Predefined templates (Gmail, Drive, Slack, Calendar)
- ✅ Custom agent option
- ✅ Name and role customization
- ✅ Advanced configuration options
- ✅ Beautiful form UI with validation

### Agent Management
- ✅ Enable/disable agents
- ✅ Update configuration
- ✅ Delete agents
- ✅ Launch agent-specific UIs

## 🔮 Roadmap

### Phase 1 (Current)
- [x] Agent Hub dashboard
- [x] Agent creation wizard
- [x] Gmail agent integration
- [x] LLM-powered parsing

### Phase 2 (Next)
- [ ] Google Drive agent UI and integration
- [ ] Slack agent UI and integration
- [ ] Calendar agent UI and integration
- [ ] Agent-to-agent communication

### Phase 3 (Future)
- [ ] Custom agent builder (visual workflow editor)
- [ ] Agent marketplace (share/import agents)
- [ ] Team collaboration (shared agents)
- [ ] Agent analytics and insights
- [ ] Voice interface
- [ ] Mobile app

## 🛠️ Technical Stack

- **UI Framework**: Streamlit
- **LLM**: GitHub Models API (GPT-4o mini)
- **Storage**: JSON file-based
- **APIs**: Gmail API, Google Drive API (planned), Slack API (planned)
- **Language**: Python 3.13

## 📂 Project Structure

```
OctaMind/
├── src/
│   ├── agent/
│   │   ├── core/                       # Agent manager, process manager
│   │   ├── llm/                        # LLM client (GitHub Models / local)
│   │   ├── memory/                     # Persistent memory system
│   │   └── ui/
│   │       ├── agent_dashboard.py      # Thin shim → dashboard/
│   │       ├── email_agent_ui.py       # Thin shim → email_agent/
│   │       ├── generic_agent_ui.py     # Generic chat UI (full)
│   │       ├── dashboard/              # Agent Hub subpackage
│   │       │   ├── app.py              # main() entry point
│   │       │   ├── agent_card.py       # show_agent_card()
│   │       │   ├── configure_panel.py  # show_configure_panel()
│   │       │   ├── create_form.py      # show_create_agent_form()
│   │       │   ├── helpers.py          # Logo helpers
│   │       │   └── styles.py           # DARK_THEME_CSS
│   │       └── email_agent/            # Gmail Agent UI subpackage
│   │           ├── app.py              # main() entry point
│   │           ├── conversation.py     # handle_conversation()
│   │           ├── formatters.py       # format_email_result()
│   │           ├── helpers.py          # Logo + watchdog
│   │           └── orchestrator.py     # execute_with_llm_orchestration()
│   └── email/
│       ├── gmail_service.py            # Gmail API client
│       └── ...
├── tests/
│   ├── agent/
│   └── integration/
├── run_agent_hub.py                    # Dashboard launcher
├── agents.json                         # Agent storage
├── credentials.json                    # Gmail OAuth
├── token.json                          # Gmail OAuth token
└── .env                                # GitHub token
```

## 🔐 Security

- `.env` file stores GitHub API token
- `credentials.json` and `token.json` for Gmail OAuth
- All sensitive files protected by `.gitignore`
- Agents run in isolated contexts

## 📖 Usage Examples

### Managing Multiple Agents

```python
from src.agent.agent_manager import get_agent_manager

# Get manager
manager = get_agent_manager()

# Create agents
email_agent = manager.create_agent(
    name="Email Butler",
    agent_type="gmail",
    role="Manage my inbox and filter spam"
)

drive_agent = manager.create_agent(
    name="File Organizer",
    agent_type="google_drive",
    role="Keep my Drive organized and shared"
)

# List all agents
agents = manager.list_agents()
print(f"Total agents: {len(agents)}")

# Update agent
manager.update_agent(
    agent_id=email_agent['id'],
    updates={'role': 'Advanced email management with priority sorting'}
)

# Delete agent
manager.delete_agent(drive_agent['id'])
```

## 🎯 Product Differentiation

**vs Traditional Email Clients:**
- Natural language interface (not just buttons)
- Multi-service integration in one platform
- AI-powered understanding of user intent

**vs Zapier/IFTTT:**
- More intelligent (LLM-powered, not just triggers)
- Conversational interface (not workflow builders)
- Specialized agents (not generic automation)

**vs AI Assistants (ChatGPT, Claude):**
- Specialized per service (deep integrations)
- Persistent agents (not one-off conversations)
- Action-oriented (executes tasks, not just answers)

## 💡 Future Product Ideas

1. **Agent Marketplace**: Users share and download agents
2. **Multi-Agent Workflows**: Agents collaborate on complex tasks
3. **Smart Suggestions**: Agents proactively suggest actions
4. **Team Spaces**: Shared agent workspace for organizations
5. **Voice Control**: "Hey agent, delete my spam emails"
6. **Scheduled Actions**: Agents run tasks on schedule
7. **Analytics Dashboard**: Track agent performance and usage

## 🤝 Contributing

To add a new agent type:

1. Add template to `AgentManager.AGENT_TYPES` in `agent_manager.py`
2. Create agent-specific UI (e.g., `drive_agent_ui.py`)
3. Update dashboard routing in `src/agent/ui/dashboard/app.py`
4. Document capabilities in this file

---

**Built with ❤️ for the multi-agent future**
