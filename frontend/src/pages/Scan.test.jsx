import React, { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";

// The page drives its own step state; the stream and the API are replaced with in-memory fakes.
const api = vi.hoisted(() => ({ harden: null, guardrailSnippet: null, starts: [] }));

vi.mock("../hooks", () => ({
  useBackends: () => ({ backends: null }),
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
  downloadReportHtml: (...args) => api.downloadReportHtml?.(...args),
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
  fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
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
    fireEvent.click(screen.getByRole("button", { name: "Guard It" }));
    await screen.findByText("FIX for Prompt A");
    fireEvent.click(screen.getByRole("button", { name: "Re-Test on Your Model" }));
    fireEvent.click(screen.getByRole("button", { name: "Re-Run" }));  // live: re-runs, and we cancel it
    fireEvent.click(screen.getByRole("button", { name: /Cancel and Edit/ }));
    await scanPrompt("Prompt B");
    fireEvent.click(screen.getByRole("button", { name: "Guard It" }));
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
    fireEvent.click(screen.getByRole("button", { name: "Guard It" }));
    await waitFor(() => expect(api.harden).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Scan Another Prompt" }));
    // B's run starts (which clears the Guard step), THEN A's late answer lands: only the request id
    // keeps it from filling B's Guard step.
    fireEvent.change(screen.getByPlaceholderText(/You are a helpful assistant/), { target: { value: "Prompt B" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
    await act(async () => release());
    await act(async () => api.starts.at(-1).opts.onCompleted(live("Prompt B")));
    fireEvent.click(screen.getByRole("button", { name: "Guard It" }));
    await screen.findByText("FIX for Prompt B");
    expect(screen.queryByText("FIX for Prompt A")).toBeNull();
  });

  it("shows the snippet while the optional fix is still loading", async () => {
    api.guardrailSnippet = vi.fn(async () => ({ snippet: "guard code" }));
    api.harden = vi.fn(() => new Promise(() => {}));  // never answers
    render(<Harness />);
    await scanPrompt("Prompt A");
    fireEvent.click(screen.getByRole("button", { name: "Guard It" }));
    expect(await screen.findByText("guard code")).toBeInTheDocument();
    expect(screen.getByText("Building the hardened prompt…")).toBeInTheDocument();
  });

  it("keeps the guardrail when only the optional fix fails", async () => {
    api.guardrailSnippet = vi.fn(async () => ({ snippet: "guard code" }));
    api.harden = vi.fn(async () => { throw new Error("harden failed"); });
    render(<Harness />);
    await scanPrompt("Prompt A");
    fireEvent.click(screen.getByRole("button", { name: "Guard It" }));
    expect(await screen.findByText("guard code")).toBeInTheDocument();
    expect(await screen.findByText(/harden failed/)).toBeInTheDocument();
    expect(screen.queryByText("The snippet couldn't be loaded.")).toBeNull();
  });

  it("shows the live scan's in-sample guard replay on the Guard step", async () => {
    api.guardrailSnippet = vi.fn(async () => ({ snippet: "guard code" }));
    api.harden = vi.fn(async (p) => ({ hardened_prompt: p, guard_block: `FIX for ${p}` }));
    render(<Harness />);
    fireEvent.change(screen.getByPlaceholderText(/You are a helpful assistant/), { target: { value: "Prompt A" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Scan" }));
    const outcomes = [
      { check: "direct_prompt_injection", probe_id: "1", attack_label: "a", baseline_issue: true, hardened_issue: true, guard_replay: "stopped" },
      { check: "direct_prompt_injection", probe_id: "2", attack_label: "b", baseline_issue: false, hardened_issue: false, guard_replay: "allowed" },
    ];
    await act(async () => api.starts.at(-1).opts.onCompleted({ ...live("Prompt A"), outcomes }));
    fireEvent.click(screen.getByRole("button", { name: "Guard It" }));
    expect(await screen.findByText(/the guard blocked or redacted 1 of 1 attack that got through and 0 of 1 reply/))
      .toBeInTheDocument();
  });

  it("still builds the optional fix when the snippet fails", async () => {
    api.guardrailSnippet = vi.fn(async () => { throw new Error("snippet failed"); });
    api.harden = vi.fn(async (p) => ({ hardened_prompt: p, guard_block: `FIX for ${p}` }));
    render(<Harness />);
    await scanPrompt("Prompt A");
    fireEvent.click(screen.getByRole("button", { name: "Guard It" }));
    expect(await screen.findByText("FIX for Prompt A")).toBeInTheDocument();
    expect(await screen.findByText(/snippet failed/)).toBeInTheDocument();
  });
});
