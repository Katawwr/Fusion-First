import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { GuardStep, StepBar } from "./Scan";
import evidence from "../content/evidence.json";

const props = {
  systemPrompt: "You are SupportBot.",
  hardened: { hardened_prompt: "You are SupportBot.\n\nGuard block", guard_block: "Guard block" },
  snippet: "guard = Guardrail(GuardConfig())",
  snippetError: null,
  fixError: null,
  onRetry: () => {},
  onProve: () => {},
  onBack: () => {},
};

function renderGuard(extra = {}) {
  return render(
    <MemoryRouter>
      <GuardStep {...props} {...extra} />
    </MemoryRouter>,
  );
}

describe("GuardStep", () => {
  it("leads with the runtime guard; the prompt fix comes after, marked optional", () => {
    renderGuard();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Runtime guard", "Optional: prompt fix"]);
  });

  it("states what the published guard configuration does", () => {
    renderGuard();
    expect(screen.getByText(
      "Redacts secrets and personal data, blocks system-prompt dumps, and blocks non-read tool calls the user's request does not cover.",
    )).toBeInTheDocument();
  });

  it("shows the guardrail's measured result from the committed evidence", () => {
    renderGuard();
    if (evidence.step2_guard?.decision?.new_rules === "adopted") {
      expect(screen.getByText(/stopped \d+% \(\d+ of \d+\)/)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Trust report" })).toHaveAttribute("href", "/trust");
    }
  });

  it("keeps the fix's measured caveat next to it", () => {
    renderGuard();
    expect(screen.getByText(/rarely cut attacks and raised refusals of safe requests/)).toBeInTheDocument();
  });

  it("re-tests the fix on the user's model from the fix section", () => {
    const onProve = vi.fn();
    renderGuard({ onProve });
    fireEvent.click(screen.getByRole("button", { name: "Re-Test on Your Model" }));
    expect(onProve).toHaveBeenCalled();
  });

  it("shows the scan's in-sample replay after the pre-registered result, with its setup and counts per check", () => {
    const inSample = {
      stopped: 5, got_through: 5, in_prose: 2, acted_on_clean: 0, clean: 3, withheld_checks: [],
      sentence: "In-sample, this scan's own attacks: the guard blocked or redacted 5 of 5 attacks that got through and 0 of 3 replies graded clean; 2 attacks got through in prose, with no tool call for the guard to check.",
      setup: "Guard set up as the snippet: your system prompt, the code-shaped values it marks secret.",
      by_check: {
        system_prompt_leakage: { stopped: 5, got_through: 5, in_prose: 0, acted_on_clean: 0, clean: 3 },
        excessive_agency: { stopped: 0, got_through: 0, in_prose: 2, acted_on_clean: 0, clean: 0 },
      },
    };
    renderGuard({ inSample });
    const sentence = screen.getByText(inSample.sentence);
    expect(screen.getByText(inSample.setup)).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /System prompt leakage/ })).toHaveTextContent("5 of 5");
    expect(screen.getByRole("row", { name: /Excessive agency/ })).toHaveTextContent(/none got through\s*2/);
    expect(screen.getByRole("table")).toHaveAccessibleDescription(inSample.sentence);
    for (const th of screen.getAllByRole("columnheader")) expect(th).toHaveAttribute("scope", "col");
    if (evidence.step2_guard?.decision?.new_rules === "adopted") {
      const measuredLine = screen.getByText(/Pre-registered test on fresh attacks/);
      expect(measuredLine.compareDocumentPosition(sentence) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("labels clean replies the guard stopped for carrying a secret, so they don't read as over-blocks", () => {
    const inSample = {
      stopped: 1, got_through: 2, in_prose: 0, acted_on_clean: 1, clean_leaks: 1, clean: 7, withheld_checks: [],
      sentence: "In-sample, this scan's own attacks: the guard blocked or redacted 1 of 2 attacks that got through and 1 of 7 replies graded clean (1 carried a secret or your system prompt).",
      setup: "Guard set up as the snippet.",
      by_check: {
        excessive_agency: { stopped: 0, got_through: 0, in_prose: 0, acted_on_clean: 1, clean_leaks: 1, clean: 7 },
      },
    };
    renderGuard({ inSample });
    expect(screen.getByRole("row", { name: /Excessive agency/ })).toHaveTextContent("1 of 7 (1 carried a secret)");
  });

  it("says a demo has no in-sample replay", () => {
    renderGuard({ canned: true, inSample: null });
    expect(screen.getByText(/needs a live scan/)).toBeInTheDocument();
  });

  it("opens the trust report without leaving the step", () => {
    renderGuard();
    if (evidence.step2_guard?.decision?.new_rules === "adopted") {
      expect(screen.getByRole("link", { name: "Trust report" })).toHaveAttribute("target", "_blank");
    }
  });

  it("names the fix's block as the fix, not the guard", () => {
    renderGuard();
    expect(screen.getByRole("button", { name: /Fix Block Only/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Copy guard block only/ })).toBeNull();
  });

  it("calls the demo's before/after an example, not a re-test", () => {
    renderGuard({ canned: true });
    expect(screen.queryByRole("button", { name: "Re-Test on Your Model" })).toBeNull();
    expect(screen.getByRole("button", { name: "Before/After" })).toBeInTheDocument();
  });
});

describe("StepBar", () => {
  const current = (container) => container.querySelector('[aria-current="step"]').closest("li").textContent;

  it("has four steps, ending in Guard", () => {
    render(<StepBar step="setup" />);
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["1Paste", "2Attack", "3Grade", "4Guard"]);
  });

  it("keeps Guard current while the fix's before/after is open", () => {
    const { container } = render(<StepBar step="prove" />);
    expect(current(container)).toMatch(/Guard$/);
  });
});
