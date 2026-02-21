# Gmail MCP Integration Setup - Learn_Python Project

## 📋 Overview

You now have a complete Gmail integration system that connects your `Learn_Python` project with the `mcp-google-email` MCP server. This allows you to send emails, read emails, and automate email tasks.

---

## 📁 Files Created

| File | Purpose |
|------|---------|
| **gmail_service.py** | Main Gmail integration module - import `send_email()` and `list_emails()` from here |
| **gmail_examples.py** | Simple usage examples |
| **gmail_integration_examples.py** | Advanced workflows and integration patterns |
| **test_gmail_setup.py** | Test script to verify your setup |
| **GMAIL_SETUP.md** | Detailed setup guide with all authentication methods |
| **GMAIL_QUICKSTART.md** | Quick start guide (5-minute setup) |
| **README_GMAIL_INTEGRATION.md** | This file |

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Get Gmail Credentials
1. Go to https://console.cloud.google.com/
2. Create a new project
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop app type)
5. Download and save as **`credentials.json`** in your `Learn_Python` folder

### Step 2: Test Your Setup
```bash
python test_gmail_setup.py
```

This will verify:
- ✓ Dependencies installed
- ✓ Credentials file found
- ✓ Gmail authentication working
- ✓ Email sending functionality

### Step 3: Start Using It!
```python
from gmail_service import send_email

result = send_email(
    to="recipient@example.com",
    subject="Hello from Python!",
    message="This email is from my Learn_Python project"
)

if result['status'] == 'success':
    print("✓ Email sent!")
else:
    print(f"✗ Failed: {result['error']}")
```

---

## 📚 API Reference

### send_email()
Send an email via Gmail

```python
from gmail_service import send_email

result = send_email(
    to="recipient@example.com",
    subject="Email Subject",
    message="Email body text"
)

# Returns: {'status': 'success/error', 'messageId': '...', 'error': '...'}
```

### list_emails()
List emails from your mailbox

```python
from gmail_service import list_emails

# Get unread emails
emails = list_emails(query='is:unread', max_results=10)

# Get emails from specific sender
emails = list_emails(query='from:boss@company.com', max_results=5)

# Get today's emails
emails = list_emails(query='after:2024-01-01', max_results=20)

# Returns: [{'id': '...', 'subject': '...', 'sender': '...', 'date': '...'}, ...]
```

**Common Gmail Search Queries:**
- `'is:unread'` - Unread emails
- `'is:starred'` - Starred emails
- `'from:email@domain.com'` - From specific sender
- `'subject:keyword'` - Subject contains keyword
- `'after:2024-01-01'` - After specific date
- `'before:2024-12-31'` - Before specific date

---

## 💡 Usage Examples

### Example 1: Send Simple Email
```python
from gmail_service import send_email

send_email(
    to="john@example.com",
    subject="Meeting Tomorrow",
    message="Let's meet at 2 PM tomorrow in the conference room."
)
```

### Example 2: Read Unread Emails
```python
from gmail_service import list_emails

emails = list_emails(query='is:unread', max_results=5)

for email in emails:
    print(f"From: {email['sender']}")
    print(f"Subject: {email['subject']}\n")
```

### Example 3: Send Emails in Batch
```python
from gmail_service import send_email

recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]

for recipient in recipients:
    result = send_email(
        to=recipient,
        subject="Important Update",
        message="Please review the attached report."
    )
    
    if result['status'] == 'success':
        print(f"✓ Sent to {recipient}")
    else:
        print(f"✗ Failed: {result['error']}")
```

### Example 4: Integrate with Your Gemma Project
```python
from gmail_service import send_email
from gemma_chat_ui import get_gemma_response  # Your Gemma module

# Get AI response
response = get_gemma_response("What's Python best for?")

# Send as email
send_email(
    to="manager@example.com",
    subject="AI Generated Report",
    message=f"Here's the AI analysis:\n\n{response}"
)
```

---

## ⚙️ Configuration

### Authentication Methods (in priority order)

1. **OAuth 2.0** (Default - Best for personal use)
   - File: `credentials.json` in project directory
   - Browser-based authentication
   - Token saved to `token.json`

2. **Service Account** (Best for automation/server)
   - Environment variable: `GOOGLE_APPLICATION_CREDENTIALS`
   - Points to service account JSON file
   - No browser interaction needed

3. **Service Account Base64** (For CI/CD)
   - Environment variable: `GOOGLE_CREDENTIALS_CONFIG`
   - Base64-encoded credentials
   - Ideal for Docker/cloud deployment

4. **Application Default Credentials (ADC)**
   - Google Cloud default authentication
   - Used in Google Cloud environments

See **GMAIL_SETUP.md** for detailed configuration instructions.

---

## 🔒 Security

### ⚠️ Important: Don't Commit Credentials!

Add to your `.gitignore`:
```
credentials.json
token.json
*.key
service-account-*.json
```

### Best Practices

1. Never share `credentials.json` files
2. Use service accounts for production, OAuth for development
3. Rotate credentials regularly
4. Use environment variables for sensitive data
5. Review Gmail app permissions periodically

---

## 🧪 Testing

### Run the Test Suite
```bash
python test_gmail_setup.py
```

This tests:
- Dependencies installation
- Credentials availability
- Gmail connectivity
- Email sending capability
- Email listing capability

### Manual Testing

Edit `gmail_examples.py` and uncomment examples:
```python
# Uncomment example functions
example_send_email()  # Send test email
example_list_unread_emails()  # List unread
```

Then run:
```bash
python gmail_examples.py
```

---

## 🐛 Troubleshooting

### "credentials.json not found"
```
Solution: Download OAuth 2.0 credentials from Google Cloud Console
and save as 'credentials.json' in Learn_Python folder
```

### "ModuleNotFoundError: google"
```
Solution: Install dependencies:
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### "Authentication failed"
```
Solution: Delete token.json and run again - browser will appear for re-auth
rm token.json
python test_gmail_setup.py
```

### "Permission denied" Error
```
Solution: 
1. Ensure Gmail API is enabled in Google Cloud Console
2. Delete token.json and re-authenticate
3. Grant all requested permissions in browser popup
```

### Still having issues?
See **GMAIL_SETUP.md** for detailed troubleshooting

---

## 📦 Dependencies

Automatically installed when you use `gmail_service.py`:
```
google-api-python-client>=2.0.0
google-auth-httplib2>=0.1.0
google-auth-oauthlib>=0.4.6
python-dotenv>=0.19.0
```

Or install manually:
```bash
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 python-dotenv
```

---

## 🔗 Integration with mcp-google-email

The `gmail_service.py` module wraps the MCP server functionality, providing a simple Python interface.

**MCP Server Location:**
```
c:\Hrishikesh\Agentic AI\mcp-google-email\
```

**The module handles:**
- ✓ Authentication (multiple methods)
- ✓ Connection management
- ✓ Error handling
- ✓ Gmail API calls

You don't need to interact with the MCP server directly - just use `gmail_service.py`!

---

## 📖 Documentation Files

- **GMAIL_QUICKSTART.md** - 5-minute setup
- **GMAIL_SETUP.md** - Complete setup guide
- **gmail_examples.py** - Code examples
- **gmail_integration_examples.py** - Advanced workflows
- **README_GMAIL_INTEGRATION.md** - This file

---

## ✅ Verification Checklist

- [ ] OAuth credentials downloaded from Google Cloud
- [ ] `credentials.json` saved in Learn_Python folder
- [ ] `test_gmail_setup.py` runs successfully
- [ ] Can send test email with `send_email()`
- [ ] Can list emails with `list_emails()`
- [ ] Ready to integrate with main project

---

## 🎯 Next Steps

1. **Complete Setup** - Follow GMAIL_QUICKSTART.md (5 minutes)
2. **Test Connection** - Run `python test_gmail_setup.py`
3. **Try Examples** - Run `gmail_examples.py` or `gmail_integration_examples.py`
4. **Integrate** - Add email functionality to your app.py or other modules
5. **Automate** - Build workflows with `gmail_integration_examples.py` as reference

---

## 📝 Example: Adding Email to Your Main Script

In your `app.py`:
```python
from gmail_service import send_email

def main():
    # Your existing code...
    
    # Send notification email
    download_gemma(model_id="mosaicml/gemma-3-4b")
    
    send_email(
        to="you@example.com",
        subject="Model Downloaded Successfully",
        message="The Gemma-3-4b model has been downloaded successfully."
    )

if __name__ == "__main__":
    main()
```

---

## 🆘 Need Help?

1. **Quick Setup Issues** → See GMAIL_QUICKSTART.md
2. **Configuration Problems** → See GMAIL_SETUP.md  
3. **Code Examples** → See gmail_examples.py or gmail_integration_examples.py
4. **Testing/Debugging** → Run test_gmail_setup.py
5. **Advanced Topics** → Check MCP server docs at mcp-google-email/

---

## 📞 Support Resources

- [Gmail API Documentation](https://developers.google.com/gmail/api)
- [Google Cloud Console](https://console.cloud.google.com/)
- [OAuth 2.0 Guide](https://developers.google.com/identity/protocols/oauth2)
- [MCP Protocol](https://modelcontextprotocol.io/)

---

**Happy Emailing! 📧**

You now have a powerful email integration tool ready to use. Start with the quick start guide and build amazing automations!
