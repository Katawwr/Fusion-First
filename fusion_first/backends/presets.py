"""Hosted providers: `<name>:<model>` means `openai-compat:<base_url>#<model>` with the provider's key.
All metered, so they need FUSION_ALLOW_API_SPEND=1 and are never selected automatically.
`mistral-api` (not `mistral`) so the Ollama model `mistral:7b` keeps meaning the local model.
"""

from __future__ import annotations

# name -> (OpenAI-compatible base URL, key environment variable)
PROVIDERS: dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "hf": ("https://router.huggingface.co/v1", "HF_TOKEN"),  # Hugging Face Inference Providers
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
    "mistral-api": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
}
ALIASES = {"huggingface": "hf"}
ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"
