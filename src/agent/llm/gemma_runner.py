"""
Gemma Runner Module

This module provides functionality to run Gemma models for text generation.
"""

import os
import torch
from .model_downloader import HF_TOKEN
from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig


def find_local_snapshot(cache_dir, model_id):
    """Find the latest local model snapshot."""
    repo_dir = os.path.join(
        cache_dir, "models--" + model_id.replace("/", "--"))
    snapshots_dir = os.path.join(repo_dir, "snapshots")
    if os.path.isdir(snapshots_dir):
        entries = [os.path.join(snapshots_dir, d) for d in os.listdir(
            snapshots_dir) if os.path.isdir(os.path.join(snapshots_dir, d))]
        if entries:
            entries.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return entries[0]
    return None


def generate_response(model, processor, device, user_query, max_tokens=400):
    """Generate a response for a given user query."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_query}
            ]
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )

    # move tensors to device
    inputs = {k: (v.to(device) if hasattr(v, 'to') else v)
              for k, v in inputs.items()}

    try:
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            top_k=50,
            repetition_penalty=1.1,
        )
        seq_len = inputs["input_ids"].shape[-1]
        gen = outputs[0][seq_len:]
        result = processor.decode(gen)
        return result
    except RuntimeError as e:
        return f"Runtime error: {e}\nYou may need a GPU or to use quantized/accelerated runtimes."


def load_model_and_processor(model_id="google/gemma-3-4b-it", cache_dir=None):
    """Load the Gemma model and processor.

    Args:
        model_id: Hugging Face model ID
        cache_dir: Optional cache directory path

    Returns:
        Tuple of (model, processor, device)
    """
    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv(
        "HF_TOKEN") or HF_TOKEN

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Using device:", device)

    print("Loading processor...")
    if cache_dir is None:
        cache_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "model_cache"))

    local_snapshot = find_local_snapshot(cache_dir, model_id)
    if local_snapshot:
        print("Found local snapshot:", local_snapshot)
        processor = AutoProcessor.from_pretrained(local_snapshot)
    else:
        processor = AutoProcessor.from_pretrained(
            model_id, use_auth_token=token)

    print("Loading model (this may take a while)...")
    # Configure int8 quantization to reduce memory and speed up inference
    bnb_config = BitsAndBytesConfig(
        load_in_8bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
    )
    if local_snapshot:
        model = AutoModelForImageTextToText.from_pretrained(
            local_snapshot, quantization_config=bnb_config, trust_remote_code=True)
    else:
        model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            quantization_config=bnb_config,
            use_auth_token=token,
            trust_remote_code=True,
        )
    model.to(device)
    print("Model loaded successfully!\n")

    return model, processor, device


def main():
    """Run interactive chat with Gemma"""
    MODEL_ID = "google/gemma-3-4b-it"

    model, processor, device = load_model_and_processor(MODEL_ID)

    # Interactive loop
    print("=" * 60)
    print("Gemma 3 Interactive Chat")
    print("Type 'quit' or 'exit' to exit")
    print("=" * 60 + "\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ["quit", "exit"]:
            print("Exiting...")
            break

        print("\nGenerating response...")
        response = generate_response(model, processor, device, user_input)
        print(f"\nAssistant: {response}\n")


if __name__ == "__main__":
    main()
