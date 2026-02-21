# OctaMind

A comprehensive project integrating Gmail API and Gemma AI for intelligent email automation.

## 🚀 Quick Start

```bash
# Install dependencies
pip install google-auth google-auth-oauthlib google-api-python-client
pip install torch transformers accelerate bitsandbytes streamlit huggingface_hub

# Send an email
python run_gmail_examples.py

# Chat with Gemma AI
python run_gemma_chat.py

# Launch Streamlit UI
streamlit run src/agent/gemma_chat_ui.py
```

## 📁 Project Structure

```
OctaMind/
├── src/                    # Source code
│   ├── email/             # Gmail integration
│   └── agent/             # AI agents
├── tests/                 # All test files
│   ├── email/             # Email operation tests
│   ├── agent/             # Agent functionality tests
│   └── integration/       # Integration tests
├── documentation/         # All documentation files
├── credentials.json       # Gmail OAuth credentials
└── run_*.py              # Convenience scripts
```

## 📚 Documentation

All documentation is in the [`documentation/`](documentation/) folder:

- **[PROJECT_OVERVIEW.md](documentation/PROJECT_OVERVIEW.md)** - Complete project guide
- **[REORGANIZATION_SUMMARY.md](documentation/REORGANIZATION_SUMMARY.md)** - Code organization details
- **[GMAIL_SETUP.md](documentation/GMAIL_SETUP.md)** - Gmail authentication setup
- **[README_GMAIL_INTEGRATION.md](documentation/README_GMAIL_INTEGRATION.md)** - Gmail integration guide
- **[FILE_STRUCTURE.md](documentation/FILE_STRUCTURE.md)** - Original structure reference
- **[GMAIL_QUICKSTART.md](documentation/GMAIL_QUICKSTART.md)** - Quick start guide
- **[src/README.md](src/README.md)** - Source code documentation

## 🔧 Usage

### Email Module
```python
from src.email import send_email, list_emails

# Send email
send_email("recipient@example.com", "Hello", "Test message")

# List emails
emails = list_emails(query='is:unread', max_results=10)
```

### Agent Module
```python
from src.agent.gemma_runner import load_model_and_processor, generate_response

# Load model
model, processor, device = load_model_and_processor()

# Generate response
response = generate_response(model, processor, device, "Hello!")
```

## 🤖 Integration Example

```python
from src.email import list_emails, send_email
from src.agent.gemma_runner import load_model_and_processor, generate_response

# Load AI model
model, processor, device = load_model_and_processor()

# Get unread emails and reply with AI
emails = list_emails(query='is:unread', max_results=5)
for email in emails:
    prompt = f"Reply professionally to: {email['subject']}"
    reply = generate_response(model, processor, device, prompt)
    send_email(email['sender'], f"Re: {email['subject']}", reply)
```

## 🧪 Testing

```bash
# Test Gmail setup
python test_gmail_setup.py

# Test new structure
python test_new_structure.py
```

## 📖 Learn More

Visit the [`documentation/`](documentation/) folder for comprehensive guides and examples.

## ✅ Features

- ✅ Gmail API integration with OAuth 2.0
- ✅ AI-powered email responses using Gemma
- ✅ Streamlit web interface
- ✅ Modular, maintainable code structure
- ✅ Comprehensive documentation

---

**Happy Coding! 🎉**
