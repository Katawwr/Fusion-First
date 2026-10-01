# fusion-safety

**Measure and guard AI agents.** Fusion attacks an agent's system prompt with OWASP-mapped attacks, grades the
transcripts with a cross-family judge whose accuracy is checked on known answers in every run (the grade is
withheld when it falls short), and ships a deterministic runtime guard that redacts secrets, blocks
system-prompt dumps, and blocks tool calls (other than reads) the user's request does not cover. Results and
their pre-registrations:
[Trust Report](https://fusion-first-testing.com/trust).

## Install

```bash
pip install fusion-safety            # CLI, runs, runtime guardrail
pip install "fusion-safety[serve]"   # + local web app: fusion serve
pip install "fusion-safety[mcp]"     # + MCP server: fusion-mcp
```

## Use

```bash
fusion doctor                                        # what can run here, no model calls
fusion run start --prompt agent.txt --target ollama:llama3.2:1b --grader claude-cli
fusion run finalize --min-grade B
fusion serve                                         # the web app on 127.0.0.1:8765
```

Targets: `ollama:<model>`, `openai-compat:<url>#<model>`, `claude-cli:<model>`, hosted APIs with your own key
(`openai:`, `anthropic:`, `hf:`, ...; needs `FUSION_ALLOW_API_SPEND=1`), or any program via `cmd:<command>`.

## Runtime guardrail

```python
from fusion_first.guardrail.guard import Guardrail
from fusion_first.guardrail.policy import GuardConfig

guard = Guardrail(GuardConfig(allowlisted_domains=["your-co.com"], require_authorization=True))
outcome = guard.guard_tool_call(tool_name, tool_args, user_request=user_message,
                                untrusted_context=True, untrusted_text=tool_results)
if outcome.blocked:
    ...  # don't run it
```

Claude Code plugin: `claude plugin marketplace add "$(fusion plugin-dir)"`, then
`claude plugin install fusion@fusion-first`.

Docs and setup options: [fusion-first-testing.com/use](https://fusion-first-testing.com/use).
