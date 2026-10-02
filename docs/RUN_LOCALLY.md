# Run Fusion locally

Every command marked **verified** was run from a source checkout (Windows 11, Python 3.13) while
writing this guide, and the output shown is what it printed. Commands that need a model were not run
here; they are marked **needs a model**.

Offline output comes from a deterministic stand-in judge over committed cassettes. Every card it
produces is stamped `DEMONSTRATION` and is not evidence; measured results are in
[TRUST_REPORT.md](../TRUST_REPORT.md).

## 1. Install

Requires Python 3.11+.

```bash
pip install "fusion-safety[serve,mcp]"      # from PyPI: CLI, web app, MCP server
pip install -e ".[dev,mcp,serve]"           # or from a checkout, with the test tools
```

From a checkout, `python -m fusion_first.cli` is equivalent to `fusion`. Building the web app from
source needs Node 22.

## 2. Check what can run here

**Verified.** `doctor` lists the keyless backends without calling a model. With `FUSION_OFFLINE=1`
(every real provider disabled, as in CI):

```bash
FUSION_OFFLINE=1 fusion doctor
```

```text
Fusion doctor: keyless backends (FUSION_OFFLINE=1)
  claude CLI : not found; subscription auth: not checked
  Ollama     : not running; models: none
  host agent : grade via MCP (get_grading_tasks / submit_grades)
  metered API: disabled (zero spend: True)
Recommended: --target <pull a model> --grader host
  hint: Install Ollama and run `ollama serve` to test open-weight models locally (free).
  hint: Install the Claude Code CLI to use Claude as a grader on your subscription.
```

Without the variable it reports the Ollama models you have pulled and whether the `claude` CLI is
logged in with a subscription.

## 3. Offline demo (no model, no network)

**Verified.** Each command exits 0.

```bash
fusion prove --check all --html report.html      # one Safety Report Card per check + branded HTML
fusion scan --prompt agent.txt --check all --html scan.html   # the same cards for your own prompt
fusion eval --check all                          # accuracy gate vs committed baselines
fusion guard-bench                               # runtime guard on the in-house labelled corpus
fusion harden --prompt agent.txt                 # print the prompt with the optional fix appended
```

`prove` prints a card per check; the head of the first one:

```text
FUSION SAFETY REPORT CARD: Demo target  [DEMONSTRATION - offline stand-in judge, not a real efficacy claim]
Check: direct_prompt_injection   Grade (your prompt): F  →  B with the optional prompt fix
OWASP: LLM01/ASI01
```

followed by judge accuracy against the oracle, the paired before/after with its honesty badge, the top
fixes (the runtime guardrail first, the optional prompt fix second), and a provenance line with the
judge, gold-set, crosswalk and verification hashes. `eval` prints one `[eval:PASS]` or `[eval:FAIL]`
line per check and exits non-zero on a failure.

## 4. Local web app

```bash
npm --prefix frontend ci && npm --prefix frontend run build   # from a checkout; the wheel ships it built
fusion serve                                                  # http://127.0.0.1:8765
fusion serve --demo-only --no-open --port 8799                # live backends off, no browser tab
```

**Verified** (`fusion serve --demo-only --no-open --port 8799` on a built frontend). Without a build
it exits 2 and names the fix:

```text
Error: no built frontend (index.html) found at ...\frontend\dist or ...\fusion_first\_bundled\web: build it with `npm --prefix frontend run build`, or point --dist at a built frontend
```

The three locks, checked with curl:

```bash
curl -s http://127.0.0.1:8799/api/health
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: evil.example" http://127.0.0.1:8799/api/health
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" -d "{}" http://127.0.0.1:8799/api/harden
```

```text
{"status":"ok","mode":"demo","version":"0.1.0"}
400
403
```

A foreign Host header is refused (400), and a state-changing call without the per-launch token is
refused (403). The served page carries the token in `<meta name="fusion-token">`.

## 5. Test your own agent with the run engine

A run has three phases: collect (test the target), grade, finalize. The grader can be the agent
that called Fusion (`host`, the default), the `claude` CLI, or any chat model.

### Any workflow, via `cmd:`

Copy `integrations/examples/fusion_adapter.py` and replace `reply()` with a call into your agent. Fusion
writes one JSON request to its stdin and reads the reply from stdout.

**Verified** with the unmodified template (it returns a fixed string, so no model runs):

```bash
fusion run start --prompt agent.txt --target "cmd:python fusion_adapter.py" --tier quick
fusion run status
```

```text
run 7d8c56c3fbb3 · target: command · grader: you / your agent
awaiting_grades: 98 questions need grading: call get_grading_tasks, answer each from its transcript, then submit_grades (the fusion-judge agent can do this for you).
```

`fusion run tasks` prints the questions as JSON: the rubric instructions, the transcript, and the
criteria to answer. Finalizing before they are answered is refused (`error: 98 questions are still
ungraded`, exit 2).

**Needs a model.** Grade and finish:

```bash
fusion run tasks > tasks.json                 # answer them yourself, or let a host agent do it over MCP
fusion run submit --file answers.json
fusion run finalize --min-grade B             # report card; exit 1 below the bar
fusion run verify                             # re-derive the card offline; exit 1 on drift
```

or let a built-in grader answer in the same command:

```bash
fusion run start --prompt agent.txt --target "cmd:python fusion_adapter.py" --grader claude-cli
```

The MCP server refuses `cmd:` targets unless `FUSION_ALLOW_CMD_TARGETS=1` is set where it runs.

### Your own model, free

**Needs a model.** A local Ollama model (any Hugging Face GGUF works as `ollama:hf.co/<user>/<repo>`):

```bash
ollama pull llama3.2:1b
fusion run start --prompt agent.txt --target ollama:llama3.2:1b --grader claude-cli
```

Your own OpenAI-compatible server (vLLM, TGI, LM Studio, llama.cpp). Loopback and private-network
URLs need no opt-in:

```bash
fusion run start --prompt agent.txt --target openai-compat:http://127.0.0.1:8000/v1#Qwen/Qwen2.5-7B-Instruct --grader claude-cli
```

No local grader is recommended: `ollama-prob:qwen2.5:7b` scored below the policy floor in its
pre-registered test. Any grader can still be chosen; each run measures it and withholds the grade
('?') when it falls short.

### Your own paid API key

Hosted providers are metered, so Fusion never selects one on its own. Each needs its usual key
variable and an explicit opt-in:

| Spec | Key variable |
|---|---|
| `openai:<model>` | `OPENAI_API_KEY` |
| `hf:<model>` | `HF_TOKEN` |
| `anthropic:<model>` | `ANTHROPIC_API_KEY` |
| `openrouter:<model>` | `OPENROUTER_API_KEY` |
| `together:<model>` | `TOGETHER_API_KEY` |
| `groq:<model>` | `GROQ_API_KEY` |
| `fireworks:<model>` | `FIREWORKS_API_KEY` |
| `mistral-api:<model>` | `MISTRAL_API_KEY` |
| `deepseek:<model>` | `DEEPSEEK_API_KEY` |

`openai-compat:<url>#<model>` pointing at a public URL needs the same opt-in.

**Verified** (both refused before any network call):

```bash
fusion run start --prompt agent.txt --target openai:gpt-4o-mini --collect-only
```

```text
Error: https://api.openai.com/v1 is a public endpoint and may be a metered API, so it is off by default: set FUSION_ALLOW_API_SPEND=1 to allow it (local and private-network servers need nothing)
```

With `FUSION_ALLOW_API_SPEND=1` but no key:

```text
error: set OPENAI_API_KEY to your openai API key
```

**Needs a model.** With both set (bash):

```bash
export OPENAI_API_KEY=...            # your key; Fusion reads it from the environment only
export FUSION_ALLOW_API_SPEND=1
fusion run start --prompt agent.txt --target openai:gpt-4o-mini --grader claude-cli
```

PowerShell:

```powershell
$env:OPENAI_API_KEY = "..."
$env:FUSION_ALLOW_API_SPEND = "1"
fusion run start --prompt agent.txt --target openai:gpt-4o-mini --grader claude-cli
```

A hosted model can also grade (`--grader openai:<model>`); grade a target with a model from a
different family, and a model grading itself is refused unless `--allow-self-grading` is passed.

## 6. Claude Code and MCP

**Verified:** `fusion plugin-dir` prints the marketplace path (the checkout in a source tree, the
bundled copy in an installed wheel).

```bash
claude plugin marketplace add "$(fusion plugin-dir)" && claude plugin install fusion@fusion-first
```

MCP clients start the server with:

```json
{ "mcpServers": { "fusion": { "command": "fusion-mcp" } } }
```

## 7. Develop

```bash
python -m pytest -q                              # offline suite
python -m ruff check fusion_first tests scripts app setup.py
npm --prefix frontend test                       # vitest
npm --prefix frontend run build && npm --prefix frontend run test:e2e   # Playwright on fusion serve
```
