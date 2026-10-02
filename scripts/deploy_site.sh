#!/usr/bin/env bash
# Deploy the site at HEAD: the demo API (Modal app fusion-safety-api) and the frontend (Vercel project
# secure-studio, fusion-first-testing.com). Usage: bash scripts/deploy_site.sh [api|web|all]  (default all)
set -euo pipefail
cd "$(dirname "$0")/.."

API_URL="https://katawwr--fusion-safety-api-fastapi-app.modal.run"
what="${1:-all}"

if ! git diff --quiet HEAD -- . ':!evals/validation/v1/agentdojo/dev'; then
  echo "refusing: uncommitted changes (the deployed version is named after HEAD)" >&2
  exit 1
fi
sha="$(git rev-parse --short HEAD)"

if [[ "$what" == "api" || "$what" == "all" ]]; then
  PYTHONIOENCODING=utf-8 FUSION_VERSION="rebuild-$sha" modal deploy app/modal_app.py
fi

if [[ "$what" == "web" || "$what" == "all" ]]; then
  (cd frontend && VITE_API_URL="$API_URL" npx vite build --outDir .vercel/output/static && vercel deploy --prebuilt --prod)
fi

echo "deployed $what at $sha"
