# OctaMind - Source Code Structure

This directory contains the organized source code for the OctaMind project.

## Directory Structure

```
src/
├── __init__.py              # Main package initialization
├── email/                   # Email-related modules
│   ├── __init__.py
│   ├── gmail_service.py    # Gmail API client and functions
│   ├── gmail_auth.py       # OAuth helpers
│   ├── gmail_summarizer.py # Email summarisation
│   └── features/           # Phase 1–4 Gmail automation features
└── agent/                   # AI Agent modules
    ├── __init__.py
    ├── core/               # Agent manager, process manager, automations
    ├── llm/                # LLM client (GitHub Models / local)
    ├── memory/             # Persistent memory system (6 memory files)
    └── ui/                 # Streamlit user interfaces
        ├── agent_dashboard.py      # Thin shim → dashboard/
        ├── email_agent_ui.py       # Thin shim → email_agent/
        ├── generic_agent_ui.py     # Generic chat UI (full)
        ├── assets/                 # Shared assets (octopus.png, etc.)
        ├── dashboard/              # Agent Hub subpackage (7 modules)
        │   ├── app.py              # main() — page config, sidebar, grid
        │   ├── agent_card.py       # show_agent_card()
        │   ├── configure_panel.py  # show_configure_panel()
        │   ├── create_form.py      # show_create_agent_form()
        │   ├── helpers.py          # Logo base64 helpers
        │   └── styles.py           # DARK_THEME_CSS + inject_css()
        └── email_agent/            # Gmail Agent UI subpackage (6 modules)
            ├── app.py              # main() — Streamlit rendering loop
            ├── conversation.py     # handle_conversation()
            ├── formatters.py       # format_email_result() + Gmail cards
            ├── helpers.py          # Logo + browser watchdog thread
            └── orchestrator.py     # execute_with_llm_orchestration()
```

## Email Module (`src/email/`)

The email module provides Gmail integration functionality.

### Components:

- **gmail_service.py**: Core Gmail service with authentication and email operations
  - `send_email()`: Send emails using Gmail API
  - `list_emails()`: List and filter emails
  - `GmailServiceClient`: OOP interface for Gmail operations

- **gmail_examples.py**: Basic usage examples
  - Simple email sending
  - Listing unread messages
  - Email filtering

- **gmail_integration.py**: Advanced integration examples
  - Email assistant workflows
  - Batch email sending
  - Email + AI integration patterns

- **mcp_server.py**: Model Context Protocol server for Gmail
  - MCP tools for email operations
  - Ready for Claude Desktop integration

### Usage Example:

```python
from src.email import send_email, list_emails

# Send an email
result = send_email(
    to="recipient@example.com",
    subject="Hello",
    message="This is a test email"
)

# List unread emails
emails = list_emails(query='is:unread', max_results=10)
```

## Agent Module (`src/agent/`)

The agent module provides AI functionality powered by Gemma models.

### Components:

- **model_downloader.py**: Download Gemma models from Hugging Face
  - `download_gemma()`: Download model snapshots
  - Handles authentication and caching

- **gemma_runner.py**: Run Gemma models for text generation
  - `load_model_and_processor()`: Load and cache models
  - `generate_response()`: Generate AI responses
  - Interactive CLI chat interface

- **gemma_chat_ui.py**: Streamlit web interface
  - Web-based chat UI
  - Conversation history management
  - Real-time response generation

### Usage Example:

```python
from src.agent import download_gemma
from src.agent.gemma_runner import load_model_and_processor, generate_response

# Download model (if needed)
download_gemma(model_id="google/gemma-3-4b-it")

# Load and use model
model, processor, device = load_model_and_processor()
response = generate_response(model, processor, device, "Hello, how are you?")
print(response)
```

## Running the Modules

### Gmail Service Test:
```bash
cd C:\Hrishikesh\OctaMind
python -m src.email.gmail_service
```

### Gemma Interactive Chat:
```bash
python -m src.agent.gemma_runner
```

### Streamlit Chat UI:
```bash
streamlit run src/agent/gemma_chat_ui.py
```

### MCP Server:
```bash
python -m src.email.mcp_server
```

## Configuration

### Gmail Setup:
1. Place `credentials.json` in the project root
2. Run any Gmail example to authenticate
3. Token will be saved automatically

### Gemma Setup:
1. Set `HUGGINGFACE_TOKEN` environment variable (optional)
2. Models are cached in `model_cache/` directory

## Integration Patterns

### Email + AI Integration:
```python
from src.email import list_emails, send_email
from src.agent.gemma_runner import load_model_and_processor, generate_response

# Load AI model
model, processor, device = load_model_and_processor()

# Get unread emails
emails = list_emails(query='is:unread', max_results=5)

# Generate and send AI replies
for email in emails:
    prompt = f"Write a professional reply to: {email['subject']}"
    reply = generate_response(model, processor, device, prompt)
    
    send_email(
        to=email['sender'],
        subject=f"Re: {email['subject']}",
        message=reply
    )
```

## Development

### Adding New Features:

1. **Email features**: Add to `src/email/gmail_service.py`
2. **Agent features**: Add to `src/agent/gemma_runner.py`
3. **Examples**: Create new files in respective directories

### Testing:

Run the test script to verify Gmail setup:
```bash
python test_gmail_setup.py
```

## Dependencies

Install required packages:
```bash
pip install google-auth google-auth-oauthlib google-api-python-client
pip install torch transformers accelerate bitsandbytes
pip install streamlit
pip install huggingface_hub
```

## Notes

- All modules use relative imports within the package
- Credentials and tokens are stored in project root
- Model cache is in project root (`model_cache/`)
- For production use, consider moving sensitive files to secure locations
