// Which backends the scan page offers, from what this server says it can actually run
// (/api/version → backends; null while unknown). A backend it can't run — or hasn't yet said it can
// run — is shown disabled with the reason: never offered and left to fail at scan time.

const RUN_LOCALLY =
  "Runs when you use Fusion on your own machine: pip install fusion-safety, then fusion serve.";
const WAITING = "Waiting for this server to say what it can run.";

// Server reasons are written for a terminal (`code` in backticks); show them as plain text.
const plain = (text) => String(text || "").replace(/`/g, "");

const DEMO = {
  id: "demo",
  title: "Demo scan",
  note: "Instant, no signup. Recorded runs that show the full flow.",
};

export function targetOptions(capabilities) {
  const caps = capabilities || null;
  if (!caps) {
    return [
      DEMO,
      { id: "ollama", title: "Open-weight model", note: WAITING, disabled: true },
      { id: "cli", title: "Claude", note: WAITING, disabled: true },
    ];
  }
  const local = caps.local_backends_enabled;
  const cliOff = !caps.cli;
  const noOllama = !caps.ollama;
  const noModels = caps.ollama && (caps.ollama_models || []).length === 0;
  // A web scan of an open-weight model is graded by Claude through the CLI, so it needs both.
  const ollamaOff = noOllama || noModels || cliOff;
  const options = [
    DEMO,
    {
      id: "ollama",
      title: "Open-weight model",
      note: !ollamaOff
        ? "Runs locally through Ollama. Free, and where attacks actually land."
        : !local
          ? RUN_LOCALLY
          : noOllama
            ? "Ollama isn't running on this machine. Start it with ollama serve."
            : noModels
              ? "No models are installed in Ollama yet. Pull one first: ollama pull llama3.2:1b."
              : "Claude grades these scans through your claude CLI, which can't run here " +
                `(${plain(caps.cli_reason) || "not ready"}). Without it, run the audit from Claude Code ` +
                "(/fusion:audit), where your agent grades.",
      disabled: ollamaOff,
    },
    {
      id: "cli",
      title: "Claude",
      note: !cliOff
        ? "Uses this machine's Claude CLI subscription. No API key needed."
        : local
          ? `Not available: ${plain(caps.cli_reason) || "the claude CLI can't run here"}.`
          : RUN_LOCALLY,
      disabled: cliOff,
    },
  ];
  // Hosted scans (the operator's keys) only make sense on a hosted server, never on your machine.
  if (!local) {
    options.push({
      id: "hosted",
      title: "Hosted real scan",
      note: caps.api ? "Your prompt, our keys." : "Coming soon.",
      disabled: !caps.api,
    });
  }
  return options;
}
