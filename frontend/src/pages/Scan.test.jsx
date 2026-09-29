import React, { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";

// The page drives its own step state; the stream and the API are replaced with in-memory fakes.
const api = vi.hoisted(() => ({ harden: null, guardrailSnippet: null, starts: [] }));

vi.mock("../hooks", () => ({
  useScanQuota: () => ({ backends: null }),
  useScanStream: () => ({
    result: null, scanId: null, lanes: {}, feed: [], completed: 0, total: 0, message: "", error: null,
    demonstration: false,
    reset: () => {},
    start: (payload, opts) => api.starts.push({ payload, opts }),
  }),
}));
vi.mock("../lib/scanApi", () => ({
  harden: (...args) => api.harden(...args),
  guardrailSnippet: (...args) => api.guardrailSnippet(...args),
  reportHtmlUrl: () => "#",
}));

import Scan from "./Scan";

const live = (prompt) => ({
  checks: ["direct_prompt_injection"], outcomes: [], overall_grade: "C", execution: "live", target_name: prompt,
  cards: [{ check: "direct_prompt_injection", kind: "safety", grade: "C", hardened_grade: "B", owasp_tags: [],
            before_after: null, trust: { execution: "live" } }],
});

function Harness() {
  const [scanState, setScanState] = useState({});
  return (
    <HelmetProvider>
      <MemoryRouter>
        <Scan scanState={scanState} setScanState={setScanState} />
      </MemoryRouter>
    </HelmetProvider>
  );
}

async function scanPrompt(text) {
  fireEvent.change(screen.getByPlaceholderText(/You are a helpful assistant/), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Run the scan" }));
  const { opts } = api.starts.at(-1);
  await act(async () => opts.onCompleted(live(text)));
}

afterEach(() => {
  api.starts.length = 0;
});

describe("Scan page: the Guard step never shows another prompt's fix", () => {
  it("rebuilds the hardened prompt after a cancelled re-run and a new prompt", async () => {
    api.guardrailSnippet = vi.fn(async () => ({ snippet: "guard code" }));
    api.harden = vi.fn(async (p) => ({ hardened_prompt: `${p}\nFIX`, guard_block: `FIX for ${p}` }));
    render(<Harness />);
    await scanPrompt("Prompt A");
    fireEvent.click(screen.getByRole("button", { name: "Guard it" }));
    await screen.findByText("FIX for Prompt A");
    fireEvent.click(screen.getByRole("button", { name: "Re-test it on your model" }));
    fireEvent.click(screen.getByRole("button", { name: "Re-run" }));  // live: re-runs, and we cancel it
    fireEvent.click(screen.getByRole("button", { name: /Cancel and edit/ }));
    await scanPrompt("Prompt B");
    fireEvent.click(screen.getByRole("button", { name: "Guard it" }));
    await screen.findByText("FIX for Prompt B");
    expect(screen.queryByText("FIX for Prompt A")).toBeNull();
  });

  it("ignores a hardened prompt that arrives after the user started over", async () => {
    let release;
    api.guardrailSnippet = vi.fn(async () => ({ snippet: "guard code" }));
    api.harden = vi.fn()
      .mockImplementationOnce((p) => new Promise((r) => { release = () => r({ hardened_prompt: p, guard_block: `FIX for ${p}` }); }))
      .mockImplementation(async (p) => ({ hardened_prompt: p, guard_block: `FIX for ${p}` }));
    render(<Harness />);
    await scanPrompt("Prompt A");
    fireEvent.click(screen.getByRole("button", { name: "Guard it" }));
    await waitFor(() => expect(api.harden).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Scan another prompt" }));
    await act(async () => release());  // A's late answer
    await scanPrompt("Prompt B");
    fireEvent.click(screen.getByRole("button", { name: "Guard it" }));
    await screen.findByText("FIX for Prompt B");
    expect(screen.queryByText("FIX for Prompt A")).toBeNull();
  });

  it("keeps the guardrail when only the optional fix fails", async () => {
    api.guardrailSnippet = vi.fn(async () => ({ snippet: "guard code" }));
    api.harden = vi.fn(async () => { throw new Error("harden failed"); });
    render(<Harness />);
    await scanPrompt("Prompt A");
    fireEvent.click(screen.getByRole("button", { name: "Guard it" }));
    expect(await screen.findByText("guard code")).toBeInTheDocument();
    expect(await screen.findByText(/harden failed/)).toBeInTheDocument();
    expect(screen.queryByText("The snippet couldn't be loaded.")).toBeNull();
  });

  it("still builds the optional fix when the snippet fails", async () => {
    api.guardrailSnippet = vi.fn(async () => { throw new Error("snippet failed"); });
    api.harden = vi.fn(async (p) => ({ hardened_prompt: p, guard_block: `FIX for ${p}` }));
    render(<Harness />);
    await scanPrompt("Prompt A");
    fireEvent.click(screen.getByRole("button", { name: "Guard it" }));
    expect(await screen.findByText("FIX for Prompt A")).toBeInTheDocument();
    expect(await screen.findByText(/snippet failed/)).toBeInTheDocument();
  });
});
