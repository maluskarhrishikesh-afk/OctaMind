# Learn Python - Documentation

This folder contains all the project documentation.

## 📖 Documentation Index

### Getting Started

- **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** - Complete project overview and quick start guide
  - Project structure
  - Installation instructions
  - Usage examples
  - Integration patterns

- **[GMAIL_SETUP.md](GMAIL_SETUP.md)** - Gmail API setup instructions
  - Google Cloud Console setup
  - OAuth 2.0 configuration
  - Authentication flow
  - Troubleshooting

- **[GMAIL_QUICKSTART.md](GMAIL_QUICKSTART.md)** - Quick start guide for Gmail integration

### Integration Guides

- **[README_GMAIL_INTEGRATION.md](README_GMAIL_INTEGRATION.md)** - Gmail integration examples
  - Basic email operations
  - Advanced patterns
  - Error handling

- **[REORGANIZATION_SUMMARY.md](REORGANIZATION_SUMMARY.md)** - Code reorganization details
  - New structure explanation
  - Migration guide
  - Benefits of new organization

### UI & Platform

- **[UI_REFERENCE.md](UI_REFERENCE.md)** - Complete UI reference ⬅️ **new**
  - All three Streamlit apps (Hub, Gmail, Generic)
  - Every page layout, sidebar, and panel documented
  - Design system (colours, typography, glassmorphism patterns)
  - Session state keys and source file index

- **[MULTI_AGENT_PLATFORM.md](MULTI_AGENT_PLATFORM.md)** - Multi-agent platform architecture

### Reference

- **[FILE_STRUCTURE.md](FILE_STRUCTURE.md)** - Original project structure reference

- **[setup-gmail-readme.md](setup-gmail-readme.md)** - Additional Gmail setup notes

- **[../src/README.md](../src/README.md)** - Source code documentation
  - Module documentation
  - API reference
  - Development guide

## 🚀 Quick Links

### Common Tasks

**Setup Gmail:**
1. Read [GMAIL_SETUP.md](GMAIL_SETUP.md)
2. Download credentials from Google Cloud Console
3. Run `python test_gmail_setup.py`

**Send Email:**
```python
from src.email import send_email
send_email("recipient@example.com", "Hello", "Test message")
```

**Use Gemma AI:**
```python
from src.agent.gemma_runner import load_model_and_processor, generate_response
model, processor, device = load_model_and_processor()
response = generate_response(model, processor, device, "Hello!")
```

**Integrate Email + AI:**
See examples in [README_GMAIL_INTEGRATION.md](README_GMAIL_INTEGRATION.md)

## 📁 Project Structure

```
Learn_Python/
├── documentation/          # This folder
│   ├── README.md          # This file
│   ├── UI_REFERENCE.md    # ← UI pages, layouts, design system
│   ├── PROJECT_OVERVIEW.md
│   ├── REORGANIZATION_SUMMARY.md
│   ├── GMAIL_SETUP.md
│   ├── README_GMAIL_INTEGRATION.md
│   ├── FILE_STRUCTURE.md
│   ├── GMAIL_QUICKSTART.md
│   └── setup-gmail-readme.md
│
├── src/                   # Source code
│   ├── README.md         # Source documentation
│   ├── email/            # Gmail integration
│   └── agent/            # AI agents
│
├── README.md             # Main project readme
├── credentials.json      # Gmail credentials
└── run_*.py             # Convenience scripts
```

## 🆘 Troubleshooting

**Can't authenticate Gmail?**
→ See [GMAIL_SETUP.md](GMAIL_SETUP.md)

**Import errors?**
→ See [REORGANIZATION_SUMMARY.md](REORGANIZATION_SUMMARY.md)

**Need examples?**
→ See [README_GMAIL_INTEGRATION.md](README_GMAIL_INTEGRATION.md)

## 📝 Notes

- All main documentation is in this folder
- Source code documentation is in `src/README.md`
- Keep credentials and tokens secure
- Test setup with `test_gmail_setup.py`

---

For the latest information, refer to [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
