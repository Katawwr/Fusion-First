"""Provider-agnostic model access.

`ModelClient` is the one interface the engine and judge depend on. Concrete providers
(anthropic, openai) implement it; `ReplayModelClient` implements it from recorded cassettes
so the whole offline test/eval loop is deterministic and free.
"""

from fusion_first.model.client import ModelClient, ModelRequest, ModelResponse, ModelRole
from fusion_first.model.registry import ModelRegistry, family_of

__all__ = [
    "ModelClient",
    "ModelRequest",
    "ModelResponse",
    "ModelRole",
    "ModelRegistry",
    "family_of",
]
