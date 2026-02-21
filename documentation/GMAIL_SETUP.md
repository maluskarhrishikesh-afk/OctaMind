# Gmail Service Setup Guide

This guide explains how to set up Gmail authentication for sending emails from your OctaMind project using the MCP Gmail service.

## Authentication Methods (in order of priority)

The Gmail service supports 3 authentication methods:

1. **Service Account** - Best for automated scripts and server applications
2. **OAuth 2.0** - Best for personal use and interactive applications
3. **Application Default Credentials (ADC)** - Best for cloud environments

---

## Method 1: OAuth 2.0 Authentication (Recommended for Personal Use)

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable the Gmail API:
   - Visit: https://console.cloud.google.com/apis/library/gmail.googleapis.com
   - Click "Enable"

### Step 2: Create OAuth 2.0 Credentials

1. Go to [Credentials page](https://console.cloud.google.com/apis/credentials)
2. Click "Create Credentials" → "OAuth client ID"
3. Choose "Desktop application"
4. Download the credentials file and name it `credentials.json`
5. Place it in your OctaMind directory (or the directory from which you run the script)

### Step 3: Automatic Authentication

On first run:
- A browser window will open asking for Gmail permission
- Grant the requested permissions
- The credentials will be saved to `token.json` in the same directory
- Subsequent runs will use the saved token automatically

**Files needed:** `credentials.json`

---

## Method 2: Service Account Authentication (Recommended for Production)

### Step 1: Create a Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable Gmail API
4. Navigate to "Credentials"
5. Click "Create Credentials" → "Service Account"
6. Fill in service account details and create
7. Go to the service account and create a JSON key
8. Download the key file

### Step 2: Grant Service Account Access to User Email

In Google Workspace Admin or personal Gmail:
- Use Gmail delegation or share access with the service account email

### Step 3: Configure Environment Variable

Set the environment variable pointing to your service account key:

**Windows (PowerShell):**
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\service-account-key.json"
```

**Windows (Command Prompt):**
```cmd
set GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account-key.json
```

**Linux/macOS:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

**Files needed:** Service account JSON key file path

---

## Method 3: Service Account via Environment Variable (Base64 Encoded)

If you can't use file-based authentication:

1. Convert service account JSON to base64:

```python
import base64
import json

with open('service-account-key.json', 'r') as f:
    credentials = json.load(f)

credentials_str = json.dumps(credentials)
encoded = base64.b64encode(credentials_str.encode()).decode()
print(encoded)
```

2. Set as environment variable:

```powershell
$env:GOOGLE_CREDENTIALS_CONFIG = "your-base64-encoded-credentials"
```

---

## Usage Examples

### Basic Email Sending

```python
from gmail_service import send_email

result = send_email(
    to="recipient@example.com",
    subject="Hello!",
    message="This is a test email"
)

if result['status'] == 'success':
    print(f"Email sent! ID: {result['messageId']}")
else:
    print(f"Error: {result['error']}")
```

### List Unread Emails

```python
from gmail_service import list_emails

# Get unread emails
emails = list_emails(query='is:unread', max_results=10)

for email in emails:
    print(f"Subject: {email['subject']}")
    print(f"From: {email['sender']}")
```

### List Emails from Specific Sender

```python
from gmail_service import list_emails

emails = list_emails(query='from:john@example.com', max_results=5)
```

---

## Google Workspace Users

If using Gmail through Google Workspace:

1. Administrator must enable API access
2. For service accounts: Admin may need to enable domain-wide delegation
3. Follow the OAuth 2.0 method for user impersonation with service accounts

---

## Troubleshooting

### "Invalid credentials" Error
- Check that credentials file path is correct
- Verify API is enabled in Google Cloud Console
- For OAuth: Delete `token.json` and authenticate again

### "Authentication failed" Error
- For service account: Verify `GOOGLE_APPLICATION_CREDENTIALS` environment variable is set
- For OAuth: Ensure `credentials.json` exists in the script directory
- Check that email has been granted access to the application

### "Permission denied" Error
- Verify Gmail API is enabled
- Check OAuth scopes are correct
- Ensure user granted permission to the application

### "Not authenticated" with Service Account
- Service account may need domain-wide delegation configured
- Try using OAuth 2.0 method instead

---

## Testing Your Setup

Use `gmail_examples.py` to test:

1. Open `gmail_examples.py`
2. Uncomment an example function call
3. Run: `python gmail_examples.py`

Example:
```python
# In gmail_examples.py, uncomment:
example_send_email()
```

---

## Security Best Practices

1. **Never commit credentials to version control**
   - Add to `.gitignore`:
     ```
     credentials.json
     token.json
     *.key
     service-account-*.json
     ```

2. **Use service accounts for production**
   - More secure than personal credentials
   - Can be rotated regularly

3. **Limit scopes**
   - Request only needed permissions
   - Current scopes: compose, send, modify, readonly

4. **Rotate tokens regularly**
   - Delete `token.json` periodically to force re-authentication
   - Service account keys should be rotated annually

---

## Quick Setup Checklist

- [ ] Create Google Cloud Project
- [ ] Enable Gmail API
- [ ] Create OAuth 2.0 credentials (download `credentials.json`)
- [ ] Place `credentials.json` in OctaMind directory
- [ ] Run script - browser will open for authentication
- [ ] Grant permissions
- [ ] Test with `gmail_examples.py`

---

For more details, visit:
- [Gmail API Documentation](https://developers.google.com/gmail/api)
- [Google Cloud Console](https://console.cloud.google.com/)
