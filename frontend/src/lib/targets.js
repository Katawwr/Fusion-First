// Which targets the scan page offers, from what this server says it can run (/api/version → backends;
// null while unknown or unreachable). A server without local backends (the hosted demo) offers the demo
// only, plus a hosted scan when its operator enabled one: live models are listed only where they can
// run. A local server lists every live target; one it can't run now is disabled with a short reason.

// Server reasons are written for a terminal (`code` in backticks, advice after a dash); show the
// reason itself as plain text.
const plain = (text) => String(text || "").replace(/`/g, "").split(" — ")[0];

const DEMO = {
  id: "demo",
  title: "Demo scan",
  note: "Recorded responses; your prompt is not run.",
};

// True when this server can run live models itself (`fusion serve`), false on the hosted demo.
export const runsLocalModels = (capabilities) => Boolean(capabilities?.local_backends_enabled);

export function targetOptions(capabilities) {
  const caps = capabilities || null;
  if (!runsLocalModels(caps)) {
    // Hosted scans (the operator's keys) only make sense on a hosted server, never on your machine.
    return caps?.api
      ? [DEMO, { id: "hosted", title: "Hosted scan", note: "Your prompt, this server's API keys." }]
      : [DEMO];
  }
  const cliOff = !caps.cli;
  const noOllama = !caps.ollama;
  const noModels = caps.ollama && (caps.ollama_models || []).length === 0;
  const cliReason = plain(caps.cli_reason) || "the claude CLI can't run here";
  // A web scan of an open-weight model is graded by Claude through the CLI, so it needs both.
  const ollamaOff = noOllama || noModels || cliOff;
  return [
    DEMO,
    {
      id: "ollama",
      title: "Open-weight model",
      note: !ollamaOff
        ? "Local, via Ollama. Graded by Claude."
        : noOllama
          ? "Ollama isn't running: ollama serve."
          : noModels
            ? "No models pulled: ollama pull llama3.2:1b."
            : `Needs the claude CLI to grade: ${cliReason}.`,
      disabled: ollamaOff,
    },
    {
      id: "cli",
      title: "Claude",
      note: cliOff ? `Unavailable: ${cliReason}.` : "Via the claude CLI on your subscription.",
      disabled: cliOff,
    },
    {
      id: "spec",
      title: "Any model",
      note: "By spec: openai:, hf:, anthropic:, openai-compat:<url>#<model>. Hosted APIs need your key and FUSION_ALLOW_API_SPEND=1.",
      disabled: !caps.spec,
    },
  ];
}
