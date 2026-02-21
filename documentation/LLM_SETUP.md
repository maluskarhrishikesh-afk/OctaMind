# Setting Up GitHub Models for Your Email Agent

## Quick Start

1. **Get GitHub Token** (you already have this!)
   - Go to GitHub.com → Settings → Developer settings → Personal access tokens
   - Generate new token (classic) - no special scopes needed
   - Copy your token: `ghp_xxxxxxxxxxxx`

2. **Create .env file**
   ```bash
   # In project root, create .env file:
   GITHUB_TOKEN=ghp_your_token_here
   ```

3. **Install Dependencies**
   ```bash
   py -m pip install openai python-dotenv
   ```

4. **Test LLM Parser**
   ```bash
   py tests/agent/test_llm_parser.py
   ```

## Usage

### Option 1: Use LLM in UI (Recommended)

The email agent UI will automatically use LLM parsing if available, falling back to rule-based parsing if not.

```bash
py -m streamlit run src/agent/email_agent_ui.py
```

### Option 2: Use LLM Programmatically

```python
from src.agent.llm_parser import parse_with_llm

# Parse complex commands
result = parse_with_llm("Delete all emails from LinkedIn sent last week")
print(result)
# {'action': 'delete', 'params': {'max_results': 1000, 'query': 'from:LinkedIn'}}
```

## Benefits of LLM Parsing

**Before (Rule-based):**
- Limited to exact keywords
- Can't understand variations
- Hard to add new patterns

**After (LLM-powered):**
- ✅ Understands natural language variations
- ✅ Handles complex queries
- ✅ No pattern maintenance needed
- ✅ Smarter parameter extraction

## Models Available

GitHub Models marketplace offers (free with your subscription):
- **gpt-4o-mini** (currently used) - Fast, intelligent, cost-effective
- **gpt-4o** - More powerful for complex queries
- **Claude 3.5 Sonnet** - Excellent for parsing
- **Llama 3.1** - Open source alternative

## Cost

**Free tier:**
- 150 requests/minute
- High rate limits for personal use
- No credit card required

Perfect for your email agent! 🎉
