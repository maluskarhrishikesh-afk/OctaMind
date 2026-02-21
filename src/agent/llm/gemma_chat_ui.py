"""
Gemma Chat UI - Streamlit Interface

This module provides a Streamlit-based web interface for chatting with Gemma.
"""

import streamlit as st
import torch
import os
from .model_downloader import HARD_CODED_HF_TOKEN
from .gemma_runner import find_local_snapshot
from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig


@st.cache_resource
def load_model_and_processor():
    """Load model and processor once and cache them."""
    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv(
        "HF_TOKEN") or HARD_CODED_HF_TOKEN

    MODEL_ID = "google/gemma-3-4b-it"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    cache_dir = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "model_cache"))
    local_snapshot = find_local_snapshot(cache_dir, MODEL_ID)

    if local_snapshot:
        processor = AutoProcessor.from_pretrained(local_snapshot)
    else:
        processor = AutoProcessor.from_pretrained(
            MODEL_ID, use_auth_token=token)

    # Configure int8 quantization
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
            MODEL_ID,
            quantization_config=bnb_config,
            use_auth_token=token,
            trust_remote_code=True,
        )

    model.to(device)
    return model, processor, device


def generate_response(model, processor, device, user_query, conversation_history, max_tokens=200):
    """Generate a response for a given user query with full conversation context."""
    # Limit conversation history to last 10 messages to avoid context overflow
    # This keeps ~2000-3000 tokens available for model output
    max_history_messages = 10
    limited_history = conversation_history[-max_history_messages:] if len(
        conversation_history) > max_history_messages else conversation_history

    # Build messages list from conversation history
    messages = []

    # Add all previous messages for context
    for msg in limited_history:
        messages.append({
            "role": msg["role"],
            "content": [{"type": "text", "text": msg["content"]}]
        })

    # Add current user query with summary instruction
    summarized_query = f"{user_query}\n\n(Please provide a concise, summarized answer in 2-3 sentences or bullet points.)"
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": summarized_query}]
    })

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
            max_new_tokens=200,
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
        return f"Error: {e}"


def main():
    """Run the Streamlit app"""
    # Streamlit page config
    st.set_page_config(page_title="Gemma 3 Chat", layout="wide")
    st.title("💬 Gemma 3 Chat")
    st.markdown("Ask me anything! Powered by Gemma 3 4B-IT")

    # Load model and processor
    with st.spinner("Loading model... (this may take a minute on first run)"):
        model, processor, device = load_model_and_processor()

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Show context usage info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Messages", len(st.session_state.messages))
    with col2:
        st.metric("Recent Context", f"Last 10 msgs" if len(
            st.session_state.messages) > 10 else f"All {len(st.session_state.messages)}")
    with col3:
        st.metric("Status", "🟢 OK" if len(
            st.session_state.messages) < 40 else "🟡 HIGH")

    # User input
    user_input = st.chat_input("Type your question here...")

    if user_input:
        # Add user message to history
        st.session_state.messages.append(
            {"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Generate response (pass history without the current message to avoid duplication)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = generate_response(
                    model, processor, device, user_input, st.session_state.messages[:-1])
            st.markdown(response)

        # Add assistant message to history
        st.session_state.messages.append(
            {"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
