# Releasing fusion-safety

Releases publish from GitHub Actions by PyPI Trusted Publishing (`.github/workflows/release.yml`): pushing a
`v<version>` tag builds the web app and the wheel, checks them, smoke-tests the wheel and uploads it. No API token
exists anywhere. PyPI never accepts the same version twice, so a mistake found after the upload means a new version.

## One-time setup

On PyPI, open project fusion-safety, then Manage, then Publishing, and add a GitHub publisher: owner `Katawwr`,
repository `Fusion-First`, workflow `release.yml`, environment `pypi`. Delete any old API tokens afterwards.

## Each release

1. Bump the version in `pyproject.toml`, `fusion_first/__init__.py` and `plugins/fusion/.mcp.json`, add the
   CHANGELOG entry, commit, and push `main` once CI is green.
2. Tag and push the tag: `git tag v0.1.5 && git push origin v0.1.5`. `scripts/release_tag_check.py` refuses a tag
   that does not name the version.
3. Watch the release run (`gh run watch`), then check https://pypi.org/project/fusion-safety/ shows the version.
4. Redeploy the site from `main`: `bash scripts/deploy_site.sh`, then date the CHANGELOG heading and commit.

## Local rehearsal (optional)

Steps 1 to 4 below build and smoke-test the same files locally before tagging.

## 1. Fresh clone outside OneDrive

OneDrive marks folders read-only, and a working checkout carries untracked files. Clone the committed release
commit instead (`REPO` is your checkout, `post-0.1.0` the branch that holds the release commit):

```bash
git -c core.autocrlf=false clone --branch post-0.1.0 "$REPO" ~/fusion-release
cd ~/fusion-release
```

## 2. Build the web app

The wheel bundles it, and the build fails without it.

```bash
npm --prefix frontend ci
npm --prefix frontend run build
```

## 3. Build and check

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

Expect `dist/fusion_safety-0.1.5-py3-none-any.whl` and `dist/fusion_safety-0.1.5.tar.gz`. A recent setuptools
may warn that the license table and the License classifier are deprecated; those are warnings, not errors.

## 4. Smoke test in a clean venv

Install the built wheel, then run from outside the clone so the installed copy is what runs:

```bash
python -m venv ~/fusion-smoke
source ~/fusion-smoke/Scripts/activate   # Git Bash; bin/activate on macOS and Linux
pip install "./dist/fusion_safety-0.1.5-py3-none-any.whl[serve,mcp]"
cd ~
python -c "import fusion_first; print(fusion_first.__version__)"
fusion doctor
fusion prove --check all
fusion guard-bench
claude plugin validate "$(fusion plugin-dir)"
```

The MCP server over stdio, as a client starts it (prints `fusion-safety 0.1.5 18`):

```bash
python - <<'EOF'
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command="fusion-mcp")
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        info = await s.initialize()
        tools = (await s.list_tools()).tools
        print((getattr(info, 'server_info', None) or info.serverInfo).name, (getattr(info, 'server_info', None) or info.serverInfo).version, len(tools))


asyncio.run(main())
EOF
```
