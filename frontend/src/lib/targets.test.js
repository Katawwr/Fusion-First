import { describe, expect, it } from "vitest";
import {
  canGradeQuality,
  effectiveGrader,
  hasLiveTarget,
  liveSetupHint,
  scanBackend,
  specPlaceholder,
  targetOptions,
  targetReady,
} from "./targets";

const ids = (opts) => opts.map((o) => o.id);

// What /api/version reports for a local `fusion serve`, by machine state.
const LOCAL = {
  demo: true,
  local_backends_enabled: true,
  cli: false,
  cli_reason: "the `claude` CLI is not logged in: run `claude auth login`",
  ollama: false,
  ollama_models: [],
  graders: [],
  hosted_providers: [],
  hosted_keys: [],
  spend_opt_in: false,
  api: false,
};
const NOTHING = LOCAL;
const OLLAMA_NO_GRADER = { ...LOCAL, ollama: true, ollama_models: ["llama3.2:1b", "qwen2.5:7b"] };
const CLI_ONLY = { ...LOCAL, cli: true, cli_reason: "ok", graders: ["claude-cli"] };
const OLLAMA_AND_CLI = { ...OLLAMA_NO_GRADER, cli: true, cli_reason: "ok", graders: ["claude-cli"] };
const OLLAMA_AND_LOCAL_GRADER = { ...OLLAMA_NO_GRADER, graders: ["ollama-prob:qwen2.5:7b"] };
const HOSTED_GRADER = { ...LOCAL, hosted_providers: ["openai"], hosted_keys: ["openai"], spend_opt_in: true };
const DEMO_ONLY = { ...LOCAL, local_backends_enabled: false, cli_reason: "local backends are off on this server" };

describe("targetOptions: only what can start and be graded here", () => {
  it("nothing available: the demo only, nothing disabled", () => {
    expect(ids(targetOptions(NOTHING))).toEqual(["demo"]);
    expect(hasLiveTarget(NOTHING)).toBe(false);
  });

  it("Ollama models without a grader are not offered", () => {
    expect(ids(targetOptions(OLLAMA_NO_GRADER))).toEqual(["demo"]);
  });

  it("a grader only (the claude CLI): Claude and Any model", () => {
    expect(ids(targetOptions(CLI_ONLY))).toEqual(["demo", "cli", "spec"]);
  });

  it("Ollama plus the claude CLI: every live target", () => {
    expect(ids(targetOptions(OLLAMA_AND_CLI))).toEqual(["demo", "ollama", "cli", "spec"]);
  });

  it("Ollama plus a qualified local grader: open-weight and Any model, no Claude", () => {
    expect(ids(targetOptions(OLLAMA_AND_LOCAL_GRADER))).toEqual(["demo", "ollama", "spec"]);
  });

  it("a hosted key with the spend opt-in grades Any model", () => {
    const opts = targetOptions(HOSTED_GRADER);
    expect(ids(opts)).toEqual(["demo", "spec"]);
    expect(opts[1].note).toMatch(/openai:<model>/);
  });

  it("a demo-only server offers the demo, whatever the machine has", () => {
    expect(ids(targetOptions({ ...OLLAMA_AND_CLI, local_backends_enabled: false }))).toEqual(["demo"]);
    expect(ids(targetOptions(DEMO_ONLY))).toEqual(["demo"]);
    expect(ids(targetOptions(null))).toEqual(["demo"]);
  });

  it("adds a hosted scan only when the hosted server enabled one", () => {
    expect(ids(targetOptions({ local_backends_enabled: false, api: true }))).toEqual(["demo", "hosted"]);
  });

  it("never marks an option disabled", () => {
    for (const caps of [NOTHING, CLI_ONLY, OLLAMA_AND_CLI, OLLAMA_AND_LOCAL_GRADER, HOSTED_GRADER, DEMO_ONLY]) {
      expect(targetOptions(caps).every((o) => !o.disabled)).toBe(true);
    }
  });
});

describe("graders", () => {
  it("keeps only a grader that can run, else the best one", () => {
    expect(effectiveGrader(CLI_ONLY, "")).toBe("claude-cli");
    expect(effectiveGrader(CLI_ONLY, "host")).toBe("claude-cli");
    expect(effectiveGrader(OLLAMA_AND_LOCAL_GRADER, "claude-cli")).toBe("ollama-prob:qwen2.5:7b");
  });

  it("a hosted grader is typed, so it starts empty when no built-in grader runs", () => {
    expect(effectiveGrader(HOSTED_GRADER, "")).toBe("");
    expect(effectiveGrader(HOSTED_GRADER, "openai:gpt-4o-mini")).toBe("openai:gpt-4o-mini");
  });

  it("the spec placeholder is a target that can run here", () => {
    expect(specPlaceholder(HOSTED_GRADER)).toBe("openai:<model>");
    expect(specPlaceholder(OLLAMA_AND_CLI)).toBe("ollama:llama3.2:1b");
    expect(specPlaceholder(CLI_ONLY)).toMatch(/^openai-compat:/);
  });
});

describe("the request a target sends", () => {
  it("an open-weight model graded by the claude CLI uses the ollama backend", () => {
    expect(scanBackend("ollama", { targetModel: "llama3.2:1b", grader: "claude-cli" })).toEqual({
      backend: "ollama", target_model: "llama3.2:1b", target_spec: null, grader_spec: null,
    });
  });

  it("an open-weight model graded by anything else runs as a spec scan", () => {
    expect(scanBackend("ollama", { targetModel: "llama3.2:1b", grader: "ollama-prob:qwen2.5:7b" })).toEqual({
      backend: "spec", target_model: null, target_spec: "ollama:llama3.2:1b", grader_spec: "ollama-prob:qwen2.5:7b",
    });
  });

  it("Any model sends its spec and grader; the demo sends no backend", () => {
    expect(scanBackend("spec", { targetSpec: " openai:gpt-4o-mini ", grader: "claude-cli" })).toMatchObject({
      backend: "spec", target_spec: "openai:gpt-4o-mini", grader_spec: "claude-cli",
    });
    expect(scanBackend("demo")).toEqual({ backend: null, target_model: null, target_spec: null, grader_spec: null });
  });

  it("is ready only with a target spec and a named grader", () => {
    expect(targetReady("spec", { targetSpec: "", grader: "claude-cli" })).toBe(false);
    expect(targetReady("spec", { targetSpec: "openai:gpt-4o-mini", grader: "" })).toBe(false);
    expect(targetReady("spec", { targetSpec: "openai:gpt-4o-mini", grader: "claude-cli" })).toBe(true);
    expect(targetReady("ollama", { grader: "" })).toBe(false);
    expect(targetReady("demo")).toBe(true);
  });
});

describe("the setup line where live scans can't run", () => {
  it("nothing to grade with: one line naming what to set up", () => {
    expect(liveSetupHint(NOTHING)).toEqual({
      kind: "grader",
      text: "Live scans need a grader: log in the claude CLI, or set a hosted key with FUSION_ALLOW_API_SPEND=1.",
    });
    expect(liveSetupHint(OLLAMA_NO_GRADER).kind).toBe("grader");
  });

  it("names the step that is missing", () => {
    const missing = { ...NOTHING, cli_reason: "the `claude` CLI isn't installed here (or FUSION_OFFLINE=1 is set)" };
    expect(liveSetupHint(missing).text).toMatch(/install the claude CLI/);
    expect(liveSetupHint({ ...NOTHING, hosted_keys: ["openai"] }).text).toMatch(
      /set FUSION_ALLOW_API_SPEND=1 for your hosted key/,
    );
  });

  it("no line where a live scan can run, or while the server hasn't answered", () => {
    expect(liveSetupHint(CLI_ONLY)).toBeNull();
    expect(liveSetupHint(HOSTED_GRADER)).toBeNull();
    expect(liveSetupHint(null, true)).toBeNull();
  });

  it("a demo-only or unreachable server points to the local install", () => {
    expect(liveSetupHint(DEMO_ONLY)).toEqual({ kind: "install" });
    expect(liveSetupHint(null)).toEqual({ kind: "install" });
  });
});

describe("quality outside a scan", () => {
  it("needs the claude CLI on a local server", () => {
    expect(canGradeQuality(CLI_ONLY)).toBe(true);
    expect(canGradeQuality(HOSTED_GRADER)).toBe(false);
    expect(canGradeQuality({ ...CLI_ONLY, local_backends_enabled: false })).toBe(false);
  });
});
