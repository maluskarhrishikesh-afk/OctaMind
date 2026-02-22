"""
LLM and local model utilities: cloud LLM client, Gemma runner, model downloader.

Note: gemma_runner (and its transformers dependency) is imported lazily
by provider_registry.py only when the local_hf provider is active.
"""

from .llm_parser import GitHubModelsLLM, get_llm_client
from .model_downloader import download_gemma, HF_TOKEN

__all__ = [
    "GitHubModelsLLM",
    "get_llm_client",
    "download_gemma",
    "HF_TOKEN",
    # gemma_runner symbols available via lazy import:
    # from src.agent.llm.gemma_runner import load_model_and_processor, generate_response
]
