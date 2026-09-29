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
  error: null,
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
  it("leads with the runtime guardrail; the prompt fix comes after, marked optional", () => {
    renderGuard();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Runtime guardrail", "Optional: prompt fix"]);
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
    fireEvent.click(screen.getByRole("button", { name: "Re-test it on your model" }));
    expect(onProve).toHaveBeenCalled();
  });

  it("calls the demo's before/after an example, not a re-test", () => {
    renderGuard({ canned: true });
    expect(screen.queryByRole("button", { name: "Re-test it on your model" })).toBeNull();
    expect(screen.getByRole("button", { name: "See the example before/after" })).toBeInTheDocument();
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
