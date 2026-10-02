// Which targets the scan page offers, from what this server can run (/api/version -> backends; null
// while unknown). An option is listed only when a scan with it can start AND be graded here now; nothing
// is shown disabled. A server without local backends (the hosted demo, `fusion serve --demo-only`)
// offers the demo, plus a hosted scan when its operator enabled one.

const DEMO = {
  id: "demo",
  title: "Demo scan",
};

// True when this server can run live models itself (`fusion serve`), false on the hosted demo.
const runsLocalModels = (capabilities) => Boolean(capabilities?.local_backends_enabled);

// Built-in graders a web scan can run now, best first (claude-cli, ollama-prob:<qualified model>).
export const graderOptions = (capabilities) =>
  runsLocalModels(capabilities) ? capabilities.graders || [] : [];

// Hosted providers usable here (key set and FUSION_ALLOW_API_SPEND=1), as a target or a grader.
export const hostedProviders = (capabilities) =>
  runsLocalModels(capabilities) ? capabilities.hosted_providers || [] : [];

const hasGrader = (capabilities) =>
  graderOptions(capabilities).length > 0 || hostedProviders(capabilities).length > 0;

// The grader a scan starts with: the best built-in one, else none (a hosted grader needs a model name).
const defaultGrader = (capabilities) => graderOptions(capabilities)[0] || "";

// The grader actually sent: the user's choice when it can run here, else the default. With hosted
// providers the grader is typed (`<provider>:<model>`), so any non-empty value is kept.
export function effectiveGrader(capabilities, chosen) {
  const value = String(chosen || "").trim();
  if (hostedProviders(capabilities).length > 0) return value || defaultGrader(capabilities);
  return graderOptions(capabilities).includes(value) ? value : defaultGrader(capabilities);
}

// Spec prefixes a local page can run as the target, for the Any-model hint and placeholder.
function specExamples(capabilities) {
  const hosted = hostedProviders(capabilities).map((p) => `${p}:<model>`);
  return [
    ...hosted,
    ...((capabilities?.ollama_models || []).length ? ["ollama:<model>"] : []),
    "openai-compat:<url>#<model>",
  ];
}

export function specPlaceholder(capabilities) {
  const hosted = hostedProviders(capabilities);
  if (hosted.length) return `${hosted[0]}:<model>`;
  const models = capabilities?.ollama_models || [];
  if (models.length) return `ollama:${models[0]}`;
  return "openai-compat:http://127.0.0.1:8000/v1#<model>";
}

export function targetOptions(capabilities) {
  const caps = capabilities || null;
  if (!runsLocalModels(caps)) {
    // Hosted scans (the operator's keys) only make sense on a hosted server, never on your machine.
    return caps?.api
      ? [DEMO, { id: "hosted", title: "Hosted scan", note: "Your prompt, this server's API keys." }]
      : [DEMO];
  }
  // Nothing live can be graded here, so nothing live is offered.
  if (!hasGrader(caps)) return [DEMO];
  const options = [DEMO];
  if ((caps.ollama_models || []).length) {
    options.push({ id: "ollama", title: "Open-weight model", note: "Local, via Ollama." });
  }
  if (caps.cli) {
    options.push({ id: "cli", title: "Claude", note: "Via the claude CLI on your subscription." });
  }
  options.push({ id: "spec", title: "Any model", note: `By spec: ${specExamples(caps).join(", ")}.` });
  return options;
}

// The backend fields of a scan request. One `target` drives everything: demo replays recorded runs,
// anything else is live. An open-weight model graded by anything but the claude CLI runs as a spec scan.
export function scanBackend(target, { targetModel = "", targetSpec = "", grader = "" } = {}) {
  const none = { backend: null, target_model: null, target_spec: null, grader_spec: null };
  if (target === "ollama" && grader !== "claude-cli") {
    return { ...none, backend: "spec", target_spec: `ollama:${targetModel}`, grader_spec: grader };
  }
  if (target === "ollama") return { ...none, backend: "ollama", target_model: targetModel };
  if (target === "cli") return { ...none, backend: "cli" };
  if (target === "spec") return { ...none, backend: "spec", target_spec: targetSpec.trim(), grader_spec: grader };
  return none;
}

// Whether the target's own fields are filled in: a spec needs a target, and every grader is named.
export function targetReady(target, { targetSpec = "", grader = "" } = {}) {
  if (target === "spec") return targetSpec.trim().length > 0 && grader.trim().length > 0;
  if (target === "ollama") return grader.trim().length > 0;
  return true;
}

// True when some live target can run here (quality checks and edited-prompt re-runs need one).
export const hasLiveTarget = (capabilities) => targetOptions(capabilities).some((o) => o.id !== "demo");

// Quality grading outside a scan (/api/grade-quality) runs on the server's default backend: the claude CLI.
export const canGradeQuality = (capabilities) =>
  runsLocalModels(capabilities) && Boolean(capabilities?.cli);

// The one line shown where live scans can't run. `kind`: "install" (no local server) or "grader"
// (a local server with nothing to grade with). Null while the server hasn't answered, or when live runs.
export function liveSetupHint(capabilities, checking = false) {
  if (checking) return null;
  if (!runsLocalModels(capabilities)) return { kind: "install" };
  if (hasGrader(capabilities)) return null;
  const reason = String(capabilities?.cli_reason || "");
  const cli = /not logged in/i.test(reason)
    ? "log in the claude CLI"
    : /isn't installed|not installed|PATH/i.test(reason)
      ? "install the claude CLI"
      : "run the claude CLI on subscription auth";
  const keys = capabilities?.hosted_keys || [];
  const hosted = keys.length ? "set FUSION_ALLOW_API_SPEND=1 for your hosted key" : "set a hosted key with FUSION_ALLOW_API_SPEND=1";
  return { kind: "grader", text: `Live scans need a grader: ${cli}, or ${hosted}.` };
}
