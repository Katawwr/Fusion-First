import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import TargetPicker from "./TargetPicker";

// What /api/version says a local `fusion serve` can run, with the claude CLI logged out.
const LOCAL = {
  demo: true,
  cli: false,
  cli_reason: "the `claude` CLI is not logged in — run `claude auth login`",
  ollama: true,
  ollama_models: ["qwen2.5:3b", "llama3.2:1b"],
  local_backends_enabled: true,
  api: false,
};

const READY = { ...LOCAL, cli: true, cli_reason: "ok" };

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

describe("TargetPicker", () => {
  it("disables a backend the server can't run, and says why", () => {
    pick({ capabilities: LOCAL });
    expect(option("^Claude")).toBeDisabled();
    expect(screen.getAllByText(/not logged in/).length).toBeGreaterThan(0);
  });

  it("needs a working grader for an open-weight scan (Claude grades it)", () => {
    pick({ capabilities: LOCAL });
    expect(option("Open-weight model")).toBeDisabled();
    expect(option("Open-weight model")).toHaveTextContent(/grade/i);
    pick({ capabilities: READY });
    expect(screen.getAllByRole("radio", { name: /Open-weight model/ }).at(-1)).toBeEnabled();
  });

  it("offers the models Ollama actually has", () => {
    pick({ capabilities: READY, target: "ollama" });
    const select = screen.getByRole("combobox", { name: /Ollama model/ });
    expect([...select.options].map((o) => o.value)).toEqual(["qwen2.5:3b", "llama3.2:1b"]);
  });

  it("on the hosted demo, offers only the demo: no disabled live options", () => {
    pick({ capabilities: HOSTED_DEMO });
    expect(screen.getAllByRole("radio").map((r) => r.textContent)).toEqual([
      expect.stringMatching(/^Demo scan/),
    ]);
    expect(screen.queryByRole("radio", { name: /Open-weight model|^Claude|Any model/ })).toBeNull();
  });

  it("on the hosted demo, gives the install in one line and links the local setup", () => {
    pick({ capabilities: HOSTED_DEMO });
    expect(screen.getByText('pip install "fusion-safety[serve]"')).toBeInTheDocument();
    expect(screen.getByText("fusion serve")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run it locally" })).toHaveAttribute("href", "/use#local");
  });

  it("offers a hosted scan only where the server enabled one", () => {
    pick({ capabilities: { ...HOSTED_DEMO, api: true } });
    expect(option("Hosted scan")).toBeEnabled();
  });

  it("shows no install note on a local server", () => {
    pick({ capabilities: LOCAL });
    expect(screen.queryByRole("link", { name: "Run it locally" })).toBeNull();
  });

  it("never offers a hosted scan on a local server", () => {
    pick({ capabilities: { ...READY, api: true } });
    expect(screen.queryByRole("radio", { name: /^Hosted scan/ })).toBeNull();
  });

  it("offers only the demo, without the install note, while the server hasn't answered", () => {
    pick({ capabilities: null, checking: true });
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    expect(option("Demo scan")).toBeEnabled();
    expect(screen.queryByRole("link", { name: "Run it locally" })).toBeNull();
  });

  it("treats a server that never answered as the demo", () => {
    pick({ capabilities: null });
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Run it locally" })).toBeInTheDocument();
  });

  it("does not offer an Ollama that has no models pulled", () => {
    pick({ capabilities: { ...READY, ollama_models: [] } });
    expect(option("Open-weight model")).toBeDisabled();
    expect(option("Open-weight model")).toHaveTextContent(/ollama pull/);
  });

  it("asks for a target spec and a grader spec when Any model is chosen", () => {
    const setTargetSpec = vi.fn();
    pick({ capabilities: { ...LOCAL, spec: true }, target: "spec", targetSpec: "", setTargetSpec,
           graderSpec: "claude-cli", setGraderSpec: vi.fn() });
    fireEvent.change(screen.getByLabelText("Target spec"), { target: { value: "hf:meta-llama/Llama-3.1-8B-Instruct" } });
    expect(setTargetSpec).toHaveBeenCalledWith("hf:meta-llama/Llama-3.1-8B-Instruct");
    expect(screen.getByLabelText("Grader spec")).toHaveValue("claude-cli");
  });
});
