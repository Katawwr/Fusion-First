"""Modal deployment wrapper: THE ONLY module in the repo that imports `modal`.

Deploys the pure FastAPI app (app.factory.create_app, i.e. fusion_first.web.factory) as the Modal
app `fusion-safety-api`.

    FUSION_VERSION=$(git rev-parse --short HEAD) modal deploy app/modal_app.py

The hosted app is the public demo: it attaches no secrets, so no provider key can reach it and every
scan is a labelled demonstration (nothing metered). Live scans run locally (`fusion serve`, the CLI,
the plugin). VERSION is provenance for /api/version, set as plain config.
"""

from __future__ import annotations

import os

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
    )
    .env({"VERSION": os.environ.get("FUSION_VERSION", "dev")})
    # The pure core + HTTP layer + committed datasets/cassettes/crosswalk the engine reads at runtime.
    .add_local_python_source("fusion_first", "app")
    .add_local_dir("datasets", remote_path="/root/datasets")
    .add_local_dir("cassettes", remote_path="/root/cassettes")
    .add_local_dir("crosswalk", remote_path="/root/crosswalk")
    .add_local_dir("evals", remote_path="/root/evals")
)

app = modal.App("fusion-safety-api")


@app.function(image=image, timeout=900, min_containers=0)
@modal.asgi_app()
def fastapi_app():
    from app.factory import create_app

    return create_app()
