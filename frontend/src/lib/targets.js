// Which backends the scan page offers, from what this server says it can actually run
// (/api/version → backends; null while unknown). A backend it can't run is shown disabled with the
// reason — never offered and left to fail at scan time.

const RUN_LOCALLY =
  "Runs when you use Fusion on your own machine: pip install fusion-safety, then fusion serve.";

export function targetOptions(capabilities) {
  const caps = capabilities || null;
  const local = caps ? caps.local_backends_enabled : true;
  const ollamaOff = caps && !caps.ollama;
  const cliOff = caps && !caps.cli;
  const options = [
    {
      id: "demo",
      title: "Demo scan",
      note: "Instant, no signup. Recorded runs that show the full flow.",
    },
    {
      id: "ollama",
      title: "Open-weight model",
      note: !ollamaOff
        ? "Runs locally through Ollama. Free, and where attacks actually land."
        : local
          ? "Ollama isn't running on this machine. Start it with ollama serve."
          : RUN_LOCALLY,
      disabled: Boolean(ollamaOff),
    },
    {
      id: "cli",
      title: "Claude",
      note: !cliOff
        ? "Uses this machine's Claude CLI subscription. No API key needed."
        : local
          ? `Not available: ${caps.cli_reason || "the claude CLI can't run here"}.`
          : RUN_LOCALLY,
      disabled: Boolean(cliOff),
    },
  ];
  // Hosted scans (the operator's keys) only make sense on a hosted server, never on your machine.
  if (!caps || !caps.local_backends_enabled) {
    options.push({
      id: "hosted",
      title: "Hosted real scan",
      note: caps && caps.api ? "Your prompt, our keys." : "Coming soon.",
      disabled: !(caps && caps.api),
    });
  }
  return options;
}
