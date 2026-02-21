# Gmail Integration - Quick Start

## 5-Minute Setup

### Step 1: Get Credentials
1. Go to: https://console.cloud.google.com/
2. Create a new project
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download and save as `credentials.json` in this folder

### Step 2: First Run
```python
from gmail_service import send_email

result = send_email(
    to="your-email@gmail.com",
    subject="Test",
    message="Hello!"
)
print(result)
```

A browser window will open - grant permissions. Done!

### Step 3: Use It Anywhere in Your Project
```python
from gmail_service import send_email

# Send email
result = send_email(to="recipient@example.com", subject="Hi", message="Hello")
print(result)

# List emails
from gmail_service import list_emails
emails = list_emails(query='is:unread', max_results=5)
for email in emails:
    print(email['subject'])
```

---

## API Reference

### send_email(to, subject, message)
Send an email

**Parameters:**
- `to` (str): Recipient email address
- `subject` (str): Email subject
- `message` (str): Email body text

**Returns:** Dictionary with keys:
- `status`: 'success' or 'error'
- `messageId`: ID of sent message (if success)
- `threadId`: Thread ID (if success)
- `error`: Error message (if failed)

**Example:**
```python
result = send_email(
    to="john@example.com",
    subject="Meeting Tomorrow",
    message="Let's meet at 2 PM tomorrow."
)
if result['status'] == 'success':
    print("Sent!")
```

---

### list_emails(query='', max_results=10)
List emails from mailbox

**Parameters:**
- `query` (str): Gmail search query (default: all emails)
- `max_results` (int): Max emails to return (default: 10)

**Returns:** List of email dictionaries with:
- `id`: Email ID
- `subject`: Email subject
- `sender`: Sender's email address

**Common Queries:**
- `'is:unread'` - Unread emails
- `'is:starred'` - Starred emails
- `'from:john@example.com'` - From specific sender
- `'subject:project'` - Emails with "project" in subject
- `'after:2024-01-01'` - Emails after date

**Example:**
```python
# Get 5 unread emails
emails = list_emails(query='is:unread', max_results=5)

# Get emails from someone
emails = list_emails(query='from:boss@company.com', max_results=10)

# Print subjects
for email in emails:
    print(f"From: {email['sender']}")
    print(f"Subject: {email['subject']}\n")
```

---

## Files Created

1. **gmail_service.py** - Main Gmail integration module
2. **gmail_examples.py** - Usage examples
3. **GMAIL_SETUP.md** - Detailed setup guide
4. **GMAIL_QUICKSTART.md** - This file

---

## Troubleshooting

**"credentials.json not found"**
- Download OAuth 2.0 credentials from Google Cloud Console
- Save as `credentials.json` in this OctaMind directory

**"ModuleNotFoundError: No module named 'google'"**
- Install: `pip install google-api-python-client google-auth-oauthlib google-auth-httplib2`

**"Authentication failed"**
- Delete `token.json` file
- Run your script again - browser will open for re-authentication

---

## Next Steps

1. ✅ Set up credentials (see GMAIL_SETUP.md for details)
2. ✅ Import `send_email` or `list_emails` from `gmail_service`
3. ✅ Use in your project!

---

## Real-World Examples

### Send Email with Gemma Chat Result
```python
from gmail_service import send_email
from gemma_chat_ui import get_response

# Get AI response
response = get_response("What's the weather?")

# Send as email
send_email(
    to="user@example.com",
    subject="AI Response",
    message=f"Query Response:\n\n{response}"
)
```

### Track Unread Emails
```python
from gmail_service import list_emails

unread = list_emails(query='is:unread', max_results=100)
print(f"You have {len(unread)} unread emails")

# Group by sender
from collections import defaultdict
senders = defaultdict(list)
for email in unread:
    senders[email['sender']].append(email['subject'])

for sender, subjects in senders.items():
    print(f"\n{sender} ({len(subjects)} emails)")
    for subject in subjects[:3]:
        print(f"  - {subject}")
```

---

Need help? See GMAIL_SETUP.md for detailed configuration instructions.
