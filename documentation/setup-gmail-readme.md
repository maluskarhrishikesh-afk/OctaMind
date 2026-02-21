📖 How to Enable Gmail API - Detailed Guide
Step 1: Go to Google Cloud Console
Open your browser and go to: https://console.cloud.google.com/
Sign in with your Google account (use your personal Gmail account)
Step 2: Create a New Project
Look at the top of the page - you'll see a dropdown that says "Select a Project" or shows a project name
Click on it
Click the "NEW PROJECT" button (blue button on the right)
In the popup:
Project name: Type anything, e.g., Learn-Python-Gmail
Leave other fields as-is
Click "CREATE"
Wait a moment while it creates (usually 30 seconds - 1 minute)
The project will auto-select when ready
Step 3: Enable Gmail API
Now you need to find and turn ON the Gmail API:

Method A: Using Search (Easiest)

At the top of the page, find the search bar (says "Search products and resources")
Type: Gmail API
Press Enter
Click on "Gmail API" from the results
Click the blue "ENABLE" button
Method B: Using Navigation Menu

Click the hamburger menu (≡) in the top-left corner
Click "APIs & Services"
Click "Library"
Search for "Gmail API"
Click on it
Click the blue "ENABLE" button
Step 4: Create OAuth 2.0 Credentials
After enabling Gmail API:

You'll see a notification saying "To use this API, you may need credentials"
Click "CREATE CREDENTIALS" button (blue button)
OR if you don't see it:

Click the hamburger menu (≡) again
Click "APIs & Services"
Click "Credentials" (left sidebar)
Click the "+ CREATE CREDENTIALS" button (blue button)
Choose "OAuth client ID" from the dropdown
Step 5: Configure OAuth Consent Screen
If this is your first time, you'll see: "OAuth consent screen"

Choose "External" (only option for personal use)
Click "CREATE"
Fill in the form:
App name: Learn-Python-Gmail (any name)
User support email: Your email address
Developer contact: Your email address
Click "SAVE AND CONTINUE"
Skip the next sections (Scopes, Optional info)
Click "SAVE AND CONTINUE" each time
Click "BACK TO DASHBOARD"
Step 6: Create OAuth 2.0 Credentials (Continued)
Now create the actual credentials:

Click "+ CREATE CREDENTIALS" again
Choose "OAuth client ID"
For Application type: Select "Desktop application"
Click "CREATE"
You'll see a popup with your credentials - click "DOWNLOAD" (or the download icon)
Step 7: Save the Downloaded File
The file downloads as client_secret_*.json or similar
Rename it to: credentials.json
Move it to: Your OctaMind folder
Path: OctaMind