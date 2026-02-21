"""
Model Downloader Module

This module provides functionality to download Gemma models from Hugging Face.
"""

import os
import argparse
from huggingface_hub import snapshot_download

# Set your Hugging Face token in the environment variable HUGGINGFACE_TOKEN
# e.g. in .env or shell: export HUGGINGFACE_TOKEN=hf_...
HF_TOKEN = os.environ.get("HUGGINGFACE_TOKEN")


def download_gemma(model_id: str = "mosaicml/gemma-3-4b",
                   cache_dir: str | None = None,
                   token: str | None = None) -> str:
    """Download a model repo snapshot using huggingface_hub.

    Args:
        model_id: The HF repo id (e.g. "mosaicml/gemma-3-4b").
        cache_dir: Optional local cache directory.
        token: Hugging Face token (or use HUGGINGFACE_TOKEN env var).

    Returns:
        Path to the downloaded repo snapshot.
    """
    token = token or os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get(
        "HF_TOKEN") or HF_TOKEN
    print(f"Downloading model '{model_id}' (cache_dir={cache_dir})...")
    try:
        path = snapshot_download(
            repo_id=model_id, cache_dir=cache_dir, token=token)
        print("Download finished:", path)
        return path
    except Exception as exc:
        print("Download failed:", exc)
        if "403" in str(exc) or "Unauthorized" in str(exc) or "Access" in str(exc):
            print(
                "This repo may be gated — accept the license on Hugging Face and set HUGGINGFACE_TOKEN.")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Download Gemma-3-4b model snapshot")
    parser.add_argument("--model-id", default="mosaicml/gemma-3-4b",
                        help="Hugging Face model repo id (default: mosaicml/gemma-3-4b)")
    parser.add_argument("--cache-dir", default=None,
                        help="Optional cache directory")
    parser.add_argument("--token", default=None,
                        help="Hugging Face token (or set HUGGINGFACE_TOKEN)")
    args = parser.parse_args()

    download_gemma(model_id=args.model_id,
                   cache_dir=args.cache_dir, token=args.token)


if __name__ == "__main__":
    main()
