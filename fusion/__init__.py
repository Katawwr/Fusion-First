"""Fusion First — pure, modal-free core for the agentic AI-safety test-and-prove engine.

Nothing in this package may import `modal`. The Modal/FastAPI wrappers live in `app/`.
This rule keeps the whole engine runnable and testable offline under plain `pytest`/`uvicorn`
and is enforced by tests/test_no_modal_import.py.
"""

__version__ = "0.1.0"
