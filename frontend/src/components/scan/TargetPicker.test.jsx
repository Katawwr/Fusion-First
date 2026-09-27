import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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
    expect(screen.getByText(/not logged in/)).toBeInTheDocument();
    expect(option("Open-weight model")).toBeEnabled();
  });

  it("offers the models Ollama actually has", () => {
    pick({ capabilities: LOCAL, target: "ollama" });
    const select = screen.getByRole("combobox", { name: /Ollama model/ });
    expect([...select.options].map((o) => o.value)).toEqual(["qwen2.5:3b", "llama3.2:1b"]);
  });

  it("on a server without local backends, points to running Fusion on your machine", () => {
    pick({ capabilities: HOSTED_DEMO });
    expect(option("Open-weight model")).toBeDisabled();
    expect(option("^Claude")).toBeDisabled();
    expect(screen.getAllByText(/fusion serve/).length).toBeGreaterThan(0);
  });

  it("never offers a hosted scan on a local server", () => {
    pick({ capabilities: LOCAL });
    expect(screen.queryByRole("radio", { name: /Hosted/ })).toBeNull();
  });

  it("keeps the local options selectable while capabilities are unknown", () => {
    pick({ capabilities: null });
    expect(option("Open-weight model")).toBeEnabled();
    expect(option("^Claude")).toBeEnabled();
  });
});
