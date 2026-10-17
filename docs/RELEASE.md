# Releasing fusion-safety

The owner's steps for a release (0.1.1 below), in order. PyPI never accepts the same version twice, so a
mistake found after the upload means a new version.

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

Expect `dist/fusion_safety-0.1.1-py3-none-any.whl` and `dist/fusion_safety-0.1.1.tar.gz`. A recent setuptools
may warn that the license table and the License classifier are deprecated; those are warnings, not errors.

## 4. Smoke test in a clean venv

Install the built wheel, then run from outside the clone so the installed copy is what runs:

```bash
python -m venv ~/fusion-smoke
source ~/fusion-smoke/Scripts/activate   # Git Bash; bin/activate on macOS and Linux
pip install "./dist/fusion_safety-0.1.1-py3-none-any.whl[serve,mcp]"
cd ~
python -c "import fusion_first; print(fusion_first.__version__)"
fusion doctor
fusion prove --check all
fusion guard-bench
claude plugin validate "$(fusion plugin-dir)"
```

The MCP server over stdio, as a client starts it (prints `fusion-safety 0.1.1 18`):

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
        print(info.serverInfo.name, info.serverInfo.version, len(tools))


asyncio.run(main())
EOF
```

## 5. Upload

From a standalone Windows PowerShell window, not the app's terminal pane: the pane corrupts a token pasted into
twine's hidden prompt, and PyPI answers 403.

```powershell
cd ~\fusion-release
python -m twine upload dist/*
```

Then check that https://pypi.org/project/fusion-safety/0.1.1/ shows the MIT license, Python 3.11 to 3.13, and the
Source and Issues links. The plugin pins `fusion-safety==0.1.1`, so its MCP server starts only once this upload is
live.

## 6. Redeploy the site

From your checkout at the release commit (the script refuses uncommitted changes):

```bash
bash scripts/deploy_site.sh
```

Then date the 0.1.1 heading in `CHANGELOG.md` and commit it.
