"""Modal deployment wrapper — THE ONLY module in the repo that imports `modal`.

Deploys the pure FastAPI app (app.factory.create_app) as a NEW Modal app, entirely separate from
the legacy `fusion-quality-tester`. The legacy deployment is never touched; rollback is a one-line
frontend env change (point VITE_API_URL back).

    modal deploy app/modal_app.py

Secrets (Modal secret `fusion-api-secrets`, all optional — absent keys => demo-only):
    ANTHROPIC_API_KEY, OPENAI_API_KEY, WEBHOOK_SECRET, VERSION,
    SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_JWKS_URL   (Supabase wired in M4)
"""

from __future__ import annotations

import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.115",
        "pydantic>=2.9",
        "pydantic-settings>=2.4",
        "anthropic>=0.40",
        "openai>=1.50",
        "httpx>=0.27",
        "numpy>=1.26",
        "scipy>=1.13",
        "pyyaml>=6.0",
        "pyjwt[crypto]>=2.9",
    )
    # The pure core + HTTP layer + committed datasets/cassettes/crosswalk the engine reads at runtime.
    .add_local_python_source("fusion", "app")
    .add_local_dir("datasets", remote_path="/root/datasets")
    .add_local_dir("cassettes", remote_path="/root/cassettes")
    .add_local_dir("crosswalk", remote_path="/root/crosswalk")
    .add_local_dir("evals", remote_path="/root/evals")
)

app = modal.App("fusion-safety-api")

_secrets = [modal.Secret.from_name("fusion-api-secrets")]


@app.function(image=image, secrets=_secrets, timeout=900, min_containers=0)
@modal.asgi_app()
def fastapi_app():
    from app.factory import create_app

    return create_app()
