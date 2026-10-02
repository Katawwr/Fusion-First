import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import TargetPicker from "./TargetPicker";

// What /api/version says a local `fusion serve` can run: the claude CLI logged out, Ollama with models.
const LOCAL = {
  demo: true,
  cli: false,
  cli_reason: "the `claude` CLI is not logged in: run `claude auth login`",
  ollama: true,
  ollama_models: ["qwen2.5:3b", "llama3.2:1b"],
  local_backends_enabled: true,
  graders: [],
  hosted_providers: [],
  hosted_keys: [],
  spend_opt_in: false,
  api: false,
};

const READY = { ...LOCAL, cli: true, cli_reason: "ok", graders: ["claude-cli"] };
const TWO_GRADERS = { ...READY, graders: ["claude-cli", "ollama-prob:qwen2.5:7b"] };
const HOSTED = { ...LOCAL, ollama_models: [], hosted_providers: ["openai"], hosted_keys: ["openai"], spend_opt_in: true };

const HOSTED_DEMO = {
  demo: true,
  cli: false,
  cli_reason: "local backends are off on this server",
  ollama: false,
  ollama_models: [],
  local_backends_enabled: false,
  api: false,
};

function pick(props = {}) {
  return render(
    <TargetPicker
      target="demo"
      onChange={vi.fn()}
      targetModel="llama3.2:1b"
      setTargetModel={vi.fn()}
      {...props}
    />,
  );
}

const option = (name) => screen.getByRole("radio", { name: new RegExp(name) });
const radios = () => screen.getAllByRole("radio").map((r) => r.textContent);

describe("TargetPicker", () => {
  it("with nothing to grade with, offers only the demo and one setup line", () => {
    pick({ capabilities: LOCAL });
    expect(radios()).toEqual([expect.stringMatching(/^Demo scan/)]);
    const line = screen.getByText(/Live scans need a grader/);
    expect(line).toHaveTextContent(
      "Live scans need a grader: log in the claude CLI, or set a hosted key with FUSION_ALLOW_API_SPEND=1. Setup",
    );
    expect(screen.getByRole("link", { name: "Setup" })).toHaveAttribute("href", "/use#local");
    expect(screen.queryByText(/not logged in/)).toBeNull();
  });

  it("never renders a disabled option", () => {
    for (const caps of [LOCAL, READY, HOSTED, HOSTED_DEMO, null]) {
      const { unmount } = pick({ capabilities: caps });
      screen.getAllByRole("radio").forEach((r) => expect(r).toBeEnabled());
      unmount();
    }
  });

  it("offers every live target once the claude CLI can grade", () => {
    pick({ capabilities: READY });
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    expect(option("Open-weight model")).toBeEnabled();
    expect(option("^Claude")).toBeEnabled();
    expect(option("Any model")).toBeEnabled();
    expect(screen.queryByText(/Live scans need a grader/)).toBeNull();
  });

  it("offers the models Ollama actually has, and states its one grader", () => {
    pick({ capabilities: READY, target: "ollama" });
    const select = screen.getByRole("combobox", { name: /Ollama model/ });
    expect([...select.options].map((o) => o.value)).toEqual(["qwen2.5:3b", "llama3.2:1b"]);
    expect(screen.getByText("claude-cli").tagName).toBe("CODE");
    expect(screen.getByText("claude-cli").parentElement).toHaveTextContent("Grader claude-cli");
    expect(screen.queryByLabelText("Grader spec")).toBeNull();
  });

  it("lets the user choose between graders that can run", () => {
    const setGraderSpec = vi.fn();
    pick({ capabilities: TWO_GRADERS, target: "ollama", setGraderSpec });
    const select = screen.getByRole("combobox", { name: "Grader" });
    expect([...select.options].map((o) => o.value)).toEqual(["claude-cli", "ollama-prob:qwen2.5:7b"]);
    fireEvent.change(select, { target: { value: "ollama-prob:qwen2.5:7b" } });
    expect(setGraderSpec).toHaveBeenCalledWith("ollama-prob:qwen2.5:7b");
  });

  it("Any model asks for a target spec; its grader is stated when only one can run", () => {
    const setTargetSpec = vi.fn();
    pick({ capabilities: READY, target: "spec", targetSpec: "", setTargetSpec });
    fireEvent.change(screen.getByLabelText("Target spec"), { target: { value: "hf:meta-llama/Llama-3.1-8B-Instruct" } });
    expect(setTargetSpec).toHaveBeenCalledWith("hf:meta-llama/Llama-3.1-8B-Instruct");
    expect(screen.getByLabelText("Target spec")).toHaveAttribute("placeholder", "ollama:qwen2.5:3b");
    expect(screen.queryByLabelText("Grader spec")).toBeNull();
    expect(screen.getByText("claude-cli")).toBeInTheDocument();
  });

  it("with a hosted grader, Any model takes a typed grader spec", () => {
    pick({ capabilities: HOSTED, target: "spec", graderSpec: "" });
    expect(radios()).toHaveLength(2);
    expect(screen.getByLabelText("Target spec")).toHaveAttribute("placeholder", "openai:<model>");
    expect(screen.getByLabelText("Grader spec")).toHaveValue("");
    expect(screen.getByLabelText("Grader spec")).toHaveAttribute("placeholder", "openai:<model>");
  });

  it("on the hosted demo, offers only the demo and the install in one line", () => {
    pick({ capabilities: HOSTED_DEMO });
    expect(radios()).toEqual([expect.stringMatching(/^Demo scan/)]);
    expect(screen.getByText('pip install "fusion-safety[serve]"')).toBeInTheDocument();
    expect(screen.getByText("fusion serve")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run Locally" })).toHaveAttribute("href", "/use#local");
  });

  it("keeps a space between inline code and the words around it", () => {
    const { container } = pick({ capabilities: HOSTED_DEMO });
    expect(container.textContent).toMatch(/Live models: pip install "fusion-safety\[serve\]", then fusion serve\. Run Locally/);
  });

  it("offers a hosted scan only where the server enabled one", () => {
    pick({ capabilities: { ...HOSTED_DEMO, api: true } });
    expect(option("Hosted scan")).toBeEnabled();
  });

  it("never offers a hosted scan on a local server", () => {
    pick({ capabilities: { ...READY, api: true } });
    expect(screen.queryByRole("radio", { name: /^Hosted scan/ })).toBeNull();
  });

  it("offers only the demo, without a setup line, while the server hasn't answered", () => {
    pick({ capabilities: null, checking: true });
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("treats a server that never answered as the demo", () => {
    pick({ capabilities: null });
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Run Locally" })).toBeInTheDocument();
  });

  it("does not offer an Ollama that has no models pulled", () => {
    pick({ capabilities: { ...READY, ollama_models: [] } });
    expect(screen.queryByRole("radio", { name: /Open-weight model/ })).toBeNull();
  });
});
