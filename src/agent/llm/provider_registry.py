"""
Octa Bot LLM Provider Registry
================================
Single source of truth for all LLM backends.

Supported provider types
------------------------
openai_compatible  — any server that speaks the OpenAI chat-completions API
                     (GitHub Models, OpenAI, Ollama, LM Studio, llama.cpp, vLLM, …)
anthropic          — Anthropic Claude (uses anthropic SDK; adapted to OpenAI interface)
local_hf           — locally cached HuggingFace model (uses transformers; adapted)

Config files
------------
config/providers.json    — which providers exist and which is active
config/credentials.json  — API keys (override env-vars of the same name)

Usage
-----
    from src.agent.llm.provider_registry import build_client

    client, model, provider_type = build_client()
    # client.chat.completions.create(...)  ← same interface for every provider
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("llm.provider_registry")

# Resolve paths relative to project root (three levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PROVIDERS_PATH  = _PROJECT_ROOT / "config" / "providers.json"
_CREDENTIALS_PATH = _PROJECT_ROOT / "config" / "settings.json"


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------

def load_provider_config() -> Dict[str, Any]:
    """Load config/providers.json. Returns empty dict on error."""
    try:
        with open(_PROVIDERS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("config/providers.json not found — falling back to github_models")
        return {}
    except Exception as exc:
        logger.error("Failed to load config/providers.json: %s", exc)
        return {}


def load_credentials() -> Dict[str, Any]:
    """
    Load config/credentials.json.
    Keys defined here override environment variables of the same name.
    """
    try:
        with open(_CREDENTIALS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("Failed to load config/credentials.json: %s", exc)
        return {}


def _resolve_api_key(provider_cfg: Dict[str, Any], credentials: Dict[str, Any]) -> str:
    """
    Resolve an API key for a provider.

    Priority order:
      1. Inline ``api_key`` in provider config (static, e.g. "ollama")
      2. Key in credentials.json llm_api_keys under ``api_key_credential``
      3. Environment variable named by ``api_key_env``
      4. Empty string (provider may not need a key, e.g. local server)
    """
    # Static inline key (e.g. Ollama uses "ollama" as a placeholder)
    if "api_key" in provider_cfg:
        return provider_cfg["api_key"]

    key_name = provider_cfg.get("api_key_credential") or provider_cfg.get("api_key_env")
    if not key_name:
        return ""

    # Check credentials.json first
    cred_keys = credentials.get("llm_api_keys", {})
    if key_name in cred_keys and cred_keys[key_name]:
        return cred_keys[key_name]

    # Fall back to environment variable
    return os.getenv(key_name, "")


def get_credential(key: str) -> str:
    """
    Resolve a credential by name. Checks credentials.json first, then env.
    Used by auth modules (gmail_auth, drive_auth) for Google OAuth paths.
    """
    creds = load_credentials()

    # Check llm_api_keys section
    llm_keys = creds.get("llm_api_keys", {})
    if key in llm_keys and llm_keys[key]:
        return llm_keys[key]

    # Return from env
    return os.getenv(key, "")


def get_google_credential_path(key: str) -> str:
    """
    Return a Google credential file path from credentials.json.
    Falls back to the project-root default.

    key: "oauth_credentials_path" | "gmail_token_path" | "drive_token_path"
    """
    creds = load_credentials()
    google = creds.get("google", {})
    raw = google.get(key, "")
    if not raw:
        return ""
    p = Path(raw)
    # Resolve relative paths against project root
    if not p.is_absolute():
        return str(_PROJECT_ROOT / p)
    return str(p)


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------

class _AnthropicCompletions:
    """Translates client.chat.completions.create() → Anthropic API."""

    def __init__(self, client: Any, model: str):
        self._client = client
        self._model = model

    def create(self, model: str = None, messages=None, temperature=0.2,
               max_tokens=3000, timeout=40, **kwargs) -> Any:
        import anthropic as _anthropic

        messages = messages or []
        target_model = model or self._model

        # Anthropic separates the system prompt from conversation messages
        system_content = ""
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system_content += m["content"] + "\n"
            else:
                filtered.append(m)

        kwargs_call: Dict[str, Any] = dict(
            model=target_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=filtered,
        )
        if system_content.strip():
            kwargs_call["system"] = system_content.strip()

        response = self._client.messages.create(**kwargs_call)

        # Wrap in an OpenAI-shaped object so callers don't change
        class _Choice:
            class _Message:
                def __init__(self, text):
                    self.content = text
            def __init__(self, text):
                self.message = self._Message(text)

        class _Response:
            def __init__(self, text):
                self.choices = [_Choice(text)]

        text = response.content[0].text if response.content else ""
        return _Response(text)


class _AnthropicChatWrapper:
    """Wraps Anthropic client to look like an OpenAI client."""

    def __init__(self, api_key: str, model: str):
        try:
            import anthropic as _anthropic
            inner = _anthropic.Anthropic(api_key=api_key)
            self.chat = type("_Chat", (), {
                "completions": _AnthropicCompletions(inner, model)
            })()
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            )


# ---------------------------------------------------------------------------
# Local HuggingFace adapter
# ---------------------------------------------------------------------------

class _LocalHFCompletions:
    """
    Wraps a HuggingFace Gemma / transformer model so it speaks
    client.chat.completions.create() like the OpenAI SDK.

    Model is loaded lazily on first call to avoid import cost at startup.
    """

    def __init__(self, model_id: str, model_cache: str, device: str, max_new_tokens: int):
        self._model_id    = model_id
        self._model_cache = model_cache
        self._device      = device
        self._max_new_tokens = max_new_tokens
        self._model     = None
        self._processor = None
        self._loaded_device = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        logger.info("Loading local HF model: %s …", self._model_id)
        try:
            from src.agent.llm.gemma_runner import load_model_and_processor
            cache_dir = str(_PROJECT_ROOT / self._model_cache) if self._model_cache else None
            model, processor, device = load_model_and_processor(
                model_id=self._model_id,
                cache_dir=cache_dir,
            )
            self._model = model
            self._processor = processor
            self._loaded_device = device
            logger.info("Local HF model loaded on device: %s", device)
        except Exception as exc:
            logger.error("Failed to load local HF model: %s", exc)
            raise RuntimeError(
                f"Could not load local model '{self._model_id}': {exc}\n"
                "Make sure transformers, torch, and the model cache are available."
            ) from exc

    def create(self, model: str = None, messages=None, temperature=0.2,
               max_tokens: int = None, timeout=None, **kwargs) -> Any:
        from src.agent.llm.gemma_runner import generate_response

        self._ensure_loaded()
        messages = messages or []
        max_tok = max_tokens or self._max_new_tokens

        # Flatten messages into a single prompt for the HF model
        # (Gemma uses a chat template via apply_chat_template — pass messages list)
        user_text = ""
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                user_text = f"[System]: {content}\n[User]: "
            elif role == "user":
                user_text += content
            # assistant turns are context — skip for single-turn inference

        raw = generate_response(
            self._model, self._processor, self._loaded_device,
            user_text, max_tokens=max_tok,
        )

        class _Choice:
            class _Message:
                def __init__(self, text):
                    self.content = text
            def __init__(self, text):
                self.message = self._Message(text)

        class _Response:
            def __init__(self, text):
                self.choices = [_Choice(text)]

        return _Response(raw)


class _LocalHFClientWrapper:
    def __init__(self, model_id: str, model_cache: str, device: str, max_new_tokens: int):
        self.chat = type("_Chat", (), {
            "completions": _LocalHFCompletions(
                model_id, model_cache, device, max_new_tokens
            )
        })()


# ---------------------------------------------------------------------------
# Main factory
# ---------------------------------------------------------------------------

def build_client(provider_name: Optional[str] = None) -> Tuple[Any, str, str]:
    """
    Build and return an LLM client for the specified (or active) provider.

    Returns:
        (client, model_name, provider_type)

    The returned client always exposes:
        client.chat.completions.create(model, messages, temperature, max_tokens, timeout)
    """
    from dotenv import load_dotenv
    load_dotenv()

    config      = load_provider_config()
    credentials = load_credentials()

    # Determine which provider to activate
    active_name = provider_name or config.get("active", "github_models")
    providers   = config.get("providers", {})
    cfg         = providers.get(active_name)

    if cfg is None:
        logger.warning(
            "Provider '%s' not found in providers.json — falling back to github_models",
            active_name,
        )
        active_name = "github_models"
        cfg = providers.get("github_models") or {
            "type": "openai_compatible",
            "base_url": "https://models.inference.ai.azure.com",
            "model": "gpt-4o-mini",
            "api_key_env": "GITHUB_TOKEN",
        }

    ptype = cfg.get("type", "openai_compatible")
    label = cfg.get("label", active_name)

    # ── openai_compatible ──────────────────────────────────────────────────
    if ptype == "openai_compatible":
        from openai import OpenAI
        api_key  = _resolve_api_key(cfg, credentials) or "none"
        base_url = cfg["base_url"]
        model    = cfg.get("model", "gpt-4o-mini")

        if not api_key or api_key in ("none", "ollama", "lm-studio"):
            pass  # local servers don't need a real key
        elif not api_key:
            raise ValueError(
                f"Provider '{active_name}' requires an API key. "
                f"Set '{cfg.get('api_key_env')}' in config/credentials.json or as an env var."
            )

        client = OpenAI(base_url=base_url, api_key=api_key)
        logger.info("LLM provider: %s  model: %s  type: %s", label, model, ptype)
        return client, model, ptype

    # ── anthropic ─────────────────────────────────────────────────────────
    elif ptype == "anthropic":
        api_key = _resolve_api_key(cfg, credentials)
        if not api_key:
            raise ValueError(
                f"Provider '{active_name}' (Anthropic) requires ANTHROPIC_API_KEY. "
                "Set it in config/credentials.json or as an env var."
            )
        model = cfg.get("model", "claude-3-5-sonnet-20241022")
        client = _AnthropicChatWrapper(api_key=api_key, model=model)
        logger.info("LLM provider: %s  model: %s  type: %s", label, model, ptype)
        return client, model, ptype

    # ── local_hf ──────────────────────────────────────────────────────────
    elif ptype == "local_hf":
        model_id      = cfg.get("model_id", "google/gemma-3-4b-it")
        model_cache   = cfg.get("model_cache", "model_cache")
        device        = cfg.get("device", "auto")
        max_new_tokens = int(cfg.get("max_new_tokens", 3000))
        client = _LocalHFClientWrapper(model_id, model_cache, device, max_new_tokens)
        logger.info("LLM provider: %s  model: %s  type: %s (lazy load)", label, model_id, ptype)
        return client, model_id, ptype

    else:
        raise ValueError(
            f"Unknown provider type '{ptype}' for provider '{active_name}'. "
            "Supported types: openai_compatible, anthropic, local_hf"
        )


# ---------------------------------------------------------------------------
# Utility helpers (used by UI and settings pages)
# ---------------------------------------------------------------------------

def list_providers() -> Dict[str, Dict[str, str]]:
    """Return {name: {label, type}} for all configured providers."""
    config = load_provider_config()
    out = {}
    for name, cfg in config.get("providers", {}).items():
        if not name.startswith("_"):
            out[name] = {
                "label": cfg.get("label", name),
                "type":  cfg.get("type", "?"),
            }
    return out


def get_active_provider() -> str:
    """Return the name of the currently active provider."""
    return load_provider_config().get("active", "github_models")


def set_active_provider(name: str) -> None:
    """
    Persist a new active provider to config/providers.json and
    invalidate the LLM client singleton so it is rebuilt on next use.
    """
    config = load_provider_config()
    if name not in config.get("providers", {}):
        raise ValueError(f"Unknown provider: '{name}'")
    config["active"] = name
    with open(_PROVIDERS_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    logger.info("Active LLM provider changed to: %s", name)

    # Invalidate singleton in llm_parser so next get_llm_client() rebuilds
    try:
        import src.agent.llm.llm_parser as _lp
        _lp._llm_client = None
    except Exception:
        pass
