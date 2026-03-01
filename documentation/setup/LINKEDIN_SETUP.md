# LinkedIn Agent Setup Guide

This guide walks you through configuring the LinkedIn Agent so that Octa can publish posts, images, videos, and articles to your personal profile or LinkedIn Company Page.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Create a LinkedIn Developer App](#create-a-linkedin-developer-app)
3. [Request the Required Scopes](#request-the-required-scopes)
4. [Run the OAuth2 Flow](#run-the-oauth2-flow)
5. [Find Your Organisation URN](#find-your-organisation-urn)
6. [Configure `settings.json`](#configure-settingsjson)
7. [Enable the LinkedIn Agent](#enable-the-linkedin-agent)
8. [Verify the Connection](#verify-the-connection)
9. [AI Image Generation (Optional)](#ai-image-generation-optional)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- A **LinkedIn account** (personal or company admin)
- Access to the [LinkedIn Developer Portal](https://developer.linkedin.com/)
- Octa Bot installed and `config/settings.json` present (copy from `settings.example.json` if not)
- Python environment activated

---

## Create a LinkedIn Developer App

1. Go to [https://developer.linkedin.com/apps](https://developer.linkedin.com/apps) and click **Create app**.
2. Fill in:
   | Field | Value |
   |---|---|
   | App name | `Octa Bot` (or any name you like) |
   | LinkedIn Page | Your personal or company page URL |
   | App logo | Upload any logo |
   | Legal agreement | Check the box |
3. Click **Create app**.
4. After creation, go to the **Auth** tab and note down:
   - **Client ID**
   - **Client Secret**
5. Under **Authorized redirect URLs**, add:
   ```
   http://localhost:8080/callback
   ```
   (This is what `redirect_uri` refers to in `settings.json`.)

---

## Request the Required Scopes

LinkedIn restricts posting API access — you need to request the following products from the **Products** tab of your app:

| Product | Scopes it enables | Required for |
|---|---|---|
| Share on LinkedIn | `w_member_social` | Posting to personal profile |
| Sign In with LinkedIn using OpenID Connect | `openid`, `profile`, `email` | Identifying yourself |
| Marketing Developer Platform (optional) | `r_organization_social`, `w_organization_social` | Company page posting |

> **Note:** Some products require LinkedIn review (1–5 business days). `Share on LinkedIn` is approved automatically for personal use.

---

## Run the OAuth2 Flow

Octa Bot provides a helper to complete the OAuth2 authorisation. With your virtual environment activated, run:

```bash
python -c "
from src.linkedin.linkedin_service import get_access_token_url
url = get_access_token_url()
print('Visit this URL:', url)
"
```

1. Copy the printed URL and open it in your browser.
2. Log in with LinkedIn and click **Allow**.
3. LinkedIn will redirect to `http://localhost:8080/callback?code=AQxxx...`.
4. Copy the `code` parameter from the URL bar, then run:

```bash
python -c "
from src.linkedin.linkedin_service import exchange_code_for_token
token = exchange_code_for_token('PASTE_CODE_HERE')
print('Access token:', token)
"
```

5. Copy the printed access token — you will paste it into `settings.json` next.

> **Access tokens expire** after 60 days for personal use. Run this flow again when it expires, or request a long-lived token through the Marketing Developer Platform.

---

## Find Your Organisation URN

If you want Octa to post on behalf of a **LinkedIn Company Page** (not your personal profile), you need the page's Organisation URN.

### Method 1 — LinkedIn Admin URL

1. Go to your Company Page admin panel.
2. The URL will look like: `https://www.linkedin.com/company/12345678/admin/`
3. The numeric ID (`12345678`) is your org ID.
4. Your URN is: `urn:li:organization:12345678`

### Method 2 — API call

```bash
python -c "
import requests, json
token = 'YOUR_ACCESS_TOKEN'
r = requests.get(
    'https://api.linkedin.com/v2/organizationAcls?q=roleAssignee',
    headers={'Authorization': f'Bearer {token}', 'X-Restli-Protocol-Version': '2.0.0'}
)
print(json.dumps(r.json(), indent=2))
"
```

Look for `organization~.id` in the response.

---

## Configure `settings.json`

Open `config/settings.json` and fill in the `linkedin` section:

```json
{
  "linkedin": {
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "access_token": "YOUR_ACCESS_TOKEN",
    "redirect_uri": "http://localhost:8080/callback",
    "org_urn": "urn:li:organization:YOUR_ORG_ID",
    "post_as_org": true,
    "image_gen_backend": "dalle3"
  }
}
```

| Key | Description |
|---|---|
| `client_id` | From the LinkedIn Developer App Auth tab |
| `client_secret` | From the LinkedIn Developer App Auth tab |
| `access_token` | Obtained from the OAuth2 flow above |
| `redirect_uri` | Must match what you added in the Developer Portal |
| `org_urn` | Leave as `""` to post to your personal profile |
| `post_as_org` | `true` ? post as company page; `false` ? post as personal profile |
| `image_gen_backend` | `"dalle3"` (requires OpenAI key) or `"stable_diffusion"` |

---

## Enable the LinkedIn Agent

The LinkedIn Agent is already registered in the code. To use it:

1. Launch the Agent Hub:
   ```bash
   python run_agent_hub.py
   ```
2. Open the dashboard at [http://localhost:8501](http://localhost:8501).
3. Click **+ Add Agent / Skill** ? select **LinkedIn**.
4. Give it a name (e.g., "Company Page Manager") and save.

The agent will now appear in your Hub and respond to natural language requests like:

> "Post a LinkedIn update about our new open-source release with an AI-generated image."
> "Schedule a motivational post for Monday."
> "Show me analytics for last week's posts."

---

## Verify the Connection

Run this quick check to make sure your token and ORN are working:

```bash
python -c "
from src.linkedin.linkedin_service import get_org_followers
result = get_org_followers()
print(result)
"
```

A successful response looks like:
```json
{"status": "success", "followers": 142, "org_urn": "urn:li:organization:12345678"}
```

If you see an error, check the [Troubleshooting](#troubleshooting) section.

---

## AI Image Generation (Optional)

The LinkedIn Agent can generate images using DALL·E 3 or Stable Diffusion before attaching them to posts.

### DALL·E 3 (OpenAI)

1. Make sure `openai` is installed:
   ```bash
   pip install openai
   ```
2. Add your OpenAI API key to `config/settings.json`:
   ```json
   {
     "openai": {
       "api_key": "sk-..."
     }
   }
   ```
3. Set `"image_gen_backend": "dalle3"` in the `linkedin` section.

### Stable Diffusion (local / self-hosted)

1. Set `"image_gen_backend": "stable_diffusion"` in the `linkedin` section.
2. Ensure a `diffusers`-compatible installation is available:
   ```bash
   pip install diffusers transformers accelerate
   ```
3. The agent will use `runwayml/stable-diffusion-v1-5` by default (downloaded automatically on first use).

---

## Troubleshooting

### `401 Unauthorized`

- Your access token has expired (tokens last ~60 days). Re-run the [OAuth2 flow](#run-the-oauth2-flow).
- Double-check `client_id`, `client_secret`, and `access_token` in `settings.json`.

### `403 Forbidden`

- You are missing a required scope. Go to your LinkedIn Developer App ? Products and verify `Share on LinkedIn` is active.
- If posting to a company page, verify you are a Page Admin and `w_organization_social` scope is granted.

### `POST https://api.linkedin.com/v2/ugcPosts` returns `404`

- The `author` URN is incorrect. Make sure `org_urn` is in the exact format `urn:li:organization:12345678` (no trailing spaces).
- If posting as personal profile, leave `org_urn` empty — the agent will use your member URN from `/v2/me`.

### Image upload fails

- Verify your token has the `w_member_social` (or `w_organization_social`) scope.
- Image must be JPEG or PNG, = 10 MB. The agent resizes automatically if using DALL·E 3 output.

### Agent not appearing in the dashboard

- Make sure the agent_hub was restarted after any code changes.
- Check that `"linkedin"` is present in `AGENT_TYPES` (`src/agent/core/agent_manager.py`) and `AGENT_REGISTRY` (`src/agent/workflows/agent_registry.py`).
- Check the Streamlit logs for import errors:
  ```bash
  python -c "from src.agent.ui.linkedin_agent.orchestrator import execute_with_llm_orchestration; print('OK')"
  ```

### Getting more help

Open a [GitHub Issue](https://github.com/your-org/Octa Bot/issues) with the label `linkedin` and include the full error traceback (redact any tokens).

---

*See also: [CONTRIBUTING.md](../../CONTRIBUTING.md) if you want to improve this agent.*
