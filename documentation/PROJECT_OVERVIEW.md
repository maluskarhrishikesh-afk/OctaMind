# Learn Python - Project Overview

A comprehensive project integrating Gmail API and Gemma AI for intelligent email automation.

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install google-auth google-auth-oauthlib google-api-python-client
pip install torch transformers accelerate bitsandbytes streamlit huggingface_hub
```

### 2. Setup Gmail Authentication
1. Place your `credentials.json` file in the project root
2. Run any Gmail example to authenticate
3. Follow the browser authentication flow

### 3. Run Examples

**Send an email:**
```bash
python run_gmail_examples.py
```

**Chat with Gemma AI:**
```bash
python run_gemma_chat.py
```

**Launch Streamlit UI:**
```bash
streamlit run src/agent/gemma_chat_ui.py
```

## 📁 Project Structure

```
Learn_Python/
├── src/                         # Main source code (NEW!)
│   ├── email/                   # Gmail integration modules
│   │   ├── gmail_service.py    # Core Gmail service
│   │   ├── gmail_examples.py   # Basic examples
│   │   ├── gmail_integration.py # Advanced integration
│   │   └── mcp_server.py       # MCP server
│   └── agent/                   # AI agent modules
│       ├── model_downloader.py  # Model download utilities
│       ├── gemma_runner.py      # Gemma runner (CLI)
│       └── gemma_chat_ui.py     # Streamlit UI
│
├── Convenience Scripts (use new src structure):
│   ├── run_gmail_examples.py    # Run Gmail examples
│   ├── run_gmail_integration.py # Run integration examples
│   ├── run_gemma_chat.py        # Run Gemma CLI chat
│   └── download_model.py        # Download Gemma model
│
├── Legacy Files (for reference):
│   ├── gmail_service.py         # Old version
│   ├── app.py                   # Old version
│   └── ... (other old files)
│
├── Configuration & Data:
│   ├── credentials.json         # Gmail OAuth credentials
│   ├── token.json              # Gmail auth token (auto-generated)
│   └── model_cache/            # Cached Gemma models
│
└── Documentation:
    ├── README.md               # This file
    ├── GMAIL_SETUP.md          # Gmail setup guide
    └── src/README.md           # Source code documentation
```

## 🔧 Module Usage

### Email Module

**Import and use:**
```python
from src.email import send_email, list_emails

# Send email
result = send_email(
    to="recipient@example.com",
    subject="Hello",
    message="Test email"
)

# List unread emails
emails = list_emails(query='is:unread', max_results=10)
for email in emails:
    print(f"{email['subject']} from {email['sender']}")
```

**CLI usage:**
```bash
# Run basic examples
python run_gmail_examples.py

# Run integration examples
python run_gmail_integration.py

# Run MCP server
python -m src.email.mcp_server
```

### Agent Module

**Import and use:**
```python
from src.agent.gemma_runner import load_model_and_processor, generate_response

# Load model
model, processor, device = load_model_and_processor()

# Generate response
response = generate_response(model, processor, device, "Hello!")
print(response)
```

**CLI usage:**
```bash
# Interactive chat
python run_gemma_chat.py

# Download model
python download_model.py --model-id google/gemma-3-4b-it

# Streamlit UI
streamlit run src/agent/gemma_chat_ui.py
```

## 🤖 Integration: Email + AI

Combine Gmail with Gemma AI for intelligent email automation:

```python
from src.email import list_emails, send_email
from src.agent.gemma_runner import load_model_and_processor, generate_response

# Load AI model
model, processor, device = load_model_and_processor()

# Get unread emails
emails = list_emails(query='is:unread', max_results=5)

# Generate and send AI-powered replies
for email in emails:
    # Create prompt for AI
    prompt = f"""Generate a professional email reply to:
    Subject: {email['subject']}
    From: {email['sender']}
    Keep it concise and helpful."""
    
    # Get AI response
    reply = generate_response(model, processor, device, prompt)
    
    # Send reply
    send_email(
        to=email['sender'],
        subject=f"Re: {email['subject']}",
        message=reply
    )
    print(f"✓ Replied to {email['sender']}")
```

## 📚 Available Examples

### Gmail Examples
1. **Basic Email Sending** - `run_gmail_examples.py`
   - Send simple emails
   - List unread messages
   - Filter emails by sender

2. **Advanced Integration** - `run_gmail_integration.py`
   - Email assistant workflows
   - Batch email sending
   - Email filtering and processing
   - AI integration patterns

### Gemma Examples
1. **CLI Chat** - `run_gemma_chat.py`
   - Interactive terminal chat
   - Conversation with Gemma AI

2. **Streamlit UI** - `src/agent/gemma_chat_ui.py`
   - Web-based chat interface
   - Conversation history
   - Visual  feedback

## 🔐 Configuration

### Gmail Configuration
- **credentials.json**: OAuth 2.0 credentials from Google Cloud Console
- **token.json**: Auto-generated after first authentication
- Supports multiple auth methods (OAuth, Service Account, ADC)

### Gemma Configuration
- **HUGGINGFACE_TOKEN**: (Optional) Set environment variable
- **model_cache/**: Models cached locally after first download
- Default model: `google/gemma-3-4b-it`

## 🧪 Testing

Test Gmail setup:
```bash
python test_gmail_setup.py
```

Check errors:
```python
from src.email import send_email

result = send_email(
    to="test@example.com",
    subject="Test",
    message="Testing"
)

if result['status'] == 'success':
    print("✓ Email sent!")
else:
    print(f"✗ Error: {result.get('error')}")
```

## 📖 Documentation

- **[src/README.md](src/README.md)** - Detailed source code documentation
- **[GMAIL_SETUP.md](GMAIL_SETUP.md)** - Gmail setup instructions
- **[FILE_STRUCTURE.md](FILE_STRUCTURE.md)** - Original structure reference

## 🆕 What's New

### Code Organization
- ✅ All code organized in `src/` directory
- ✅ Separate `email/` and `agent/` modules
- ✅ Clean imports and proper package structure
- ✅ Convenience wrapper scripts for easy access

### Benefits
- 🎯 Clear separation of concerns
- 📦 Proper Python package structure
- 🔄 Easy to import and reuse
- 🛠️ Better maintainability
- 📚 Comprehensive documentation

## 🤝 Contributing

When adding new features:
1. Email features → `src/email/`
2. AI features → `src/agent/`
3. Create wrapper scripts in root for convenience
4. Update documentation

## 📝 Notes

- Old files kept for backward compatibility
- New code should use `src/` imports
- All examples updated to use new structure
- Test your Gmail setup before running examples

## 🆘 Troubleshooting

**Import errors:**
```bash
# Make sure you're in the project root
cd C:\Hrishikesh\Learn_Python

# Run with python module syntax
python -m src.email.gmail_service
```

**Gmail auth issues:**
```bash
# Delete old token and re-authenticate
del token.json
python run_gmail_examples.py
```

**Gemma model issues:**
```bash
# Set Hugging Face token
set HUGGINGFACE_TOKEN=your_token_here

# Download model manually
python download_model.py
```

## 📧 Support

For issues:
1. Check the documentation in `src/README.md`
2. Review examples in `run_*.py` files
3. Check `GMAIL_SETUP.md` for Gmail configuration

---

**Happy Coding! 🎉**
