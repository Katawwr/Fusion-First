import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";

// The setup step offers only what this server can run; /api/version's backends are set per test.
const env = vi.hoisted(() => ({ backends: null, starts: [] }));

vi.mock("../hooks", () => ({
  useBackends: () => ({ backends: env.backends, loading: false }),
  useScanStream: () => ({
    result: null, scanId: null, lanes: {}, feed: [], completed: 0, total: 0, message: "", error: null,
    demonstration: false,
    reset: () => {},
    start: (payload) => env.starts.push(payload),
  }),
}));

import Scan from "./Scan";

const LOCAL = {
  demo: true, local_backends_enabled: true, cli: false,
  cli_reason: "the `claude` CLI is not logged in: run `claude auth login`",
  ollama: true, ollama_models: ["llama3.2:1b"], graders: [], hosted_providers: [], hosted_keys: [],
  spend_opt_in: false, api: false,
};

function open(backends) {
  env.backends = backends;
  render(
    <HelmetProvider>
      <MemoryRouter>
        <Scan scanState={{}} setScanState={() => {}} />
      </MemoryRouter>
    </HelmetProvider>,
  );
  fireEvent.change(screen.getByPlaceholderText(/You are a helpful assistant/), { target: { value: "p" } });
}

const run = () => {
  fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
  return env.starts.at(-1);
};

afterEach(() => {
  env.starts.length = 0;
});

describe("Scan setup: only what can run here", () => {
  it("with nothing to grade with, leaves out the Quality section and runs the demo", () => {
    open(LOCAL);
    expect(screen.queryByRole("heading", { name: "Quality checks" })).toBeNull();
    expect(within(screen.getByRole("radiogroup", { name: "Target model" })).getAllByRole("radio")).toHaveLength(1);
    expect(screen.getByRole("radiogroup", { name: "Attack set" })).toBeInTheDocument();
    const payload = run();
    expect(payload).toMatchObject({ mode: "demo", backend: null });
    expect(payload.checks).not.toContain("instruction_following");
  });

  it("a demo-only server shows the demo without a Quality section", () => {
    open({ ...LOCAL, local_backends_enabled: false });
    expect(screen.queryByRole("heading", { name: "Quality checks" })).toBeNull();
    expect(screen.getByRole("link", { name: "Run Locally" })).toBeInTheDocument();
  });

  it("with a grader, quality checks say once that they need a live target", () => {
    open({ ...LOCAL, cli: true, cli_reason: "ok", graders: ["claude-cli"] });
    expect(screen.getByRole("heading", { name: "Quality checks" })).toBeInTheDocument();
    expect(screen.getAllByText("Run on a live target.")).toHaveLength(1);
    fireEvent.click(screen.getByRole("radio", { name: /^Claude/ }));
    expect(screen.queryByText("Run on a live target.")).toBeNull();
    const payload = run();
    expect(payload).toMatchObject({ mode: "live", backend: "cli" });
    expect(payload.checks).toContain("instruction_following");
  });

  it("an open-weight model graded by a local grader starts as a spec scan", () => {
    open({ ...LOCAL, ollama_models: ["llama3.2:1b", "qwen2.5:7b"], graders: ["ollama-prob:qwen2.5:7b"] });
    expect(screen.queryByRole("radio", { name: /^Claude/ })).toBeNull();
    fireEvent.click(screen.getByRole("radio", { name: /Open-weight model/ }));
    expect(run()).toMatchObject({
      mode: "live", backend: "spec", target_spec: "ollama:llama3.2:1b", grader_spec: "ollama-prob:qwen2.5:7b",
    });
  });

  it("Any model with a hosted grader waits for a target and a grader", () => {
    open({ ...LOCAL, ollama_models: [], hosted_providers: ["openai"], hosted_keys: ["openai"], spend_opt_in: true });
    fireEvent.click(screen.getByRole("radio", { name: /Any model/ }));
    const button = screen.getByRole("button", { name: "Run Scan" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Target spec"), { target: { value: "openai:gpt-4o-mini" } });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Grader spec"), { target: { value: "openai:gpt-4o" } });
    expect(button).toBeEnabled();
    expect(run()).toMatchObject({ backend: "spec", target_spec: "openai:gpt-4o-mini", grader_spec: "openai:gpt-4o" });
  });
});
