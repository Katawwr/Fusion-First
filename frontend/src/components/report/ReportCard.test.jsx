import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ReportCard from "./ReportCard";

const card = {
  check: "direct_prompt_injection",
  kind: "safety",
  grade: "D",
  owasp_tags: [],
  before_after: {
    baseline_issue_rate: 0.4,
    hardened_issue_rate: 0.2,
    absolute_reduction: { point: 0.2, low: 0, high: 0.4 },
    honesty: "PRELIMINARY",
    honesty_reasons: [],
  },
  trust: { execution: "live", n_planned: 10, n_scored: 10, n_errored: 0 },
};

describe("ReportCard", () => {
  it("shows what was measured before the optional prompt fix", () => {
    render(<ReportCard card={card} outcomes={[]} />);
    const scored = screen.getByText(/10 of 10 attacks scored/);
    const fix = screen.getByText("Prompt fix (optional)");
    expect(scored.compareDocumentPosition(fix) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("lists what got through without the fix's per-attack markers", () => {
    const outcomes = [
      { probe_id: "a", check: card.check, attack_label: "Posed as admin", baseline_issue: true, hardened_issue: false },
      { probe_id: "b", check: card.check, attack_label: "Hidden instruction", baseline_issue: true, hardened_issue: true },
    ];
    render(<ReportCard card={card} outcomes={outcomes} />);
    expect(screen.getByText("Posed as admin")).toBeInTheDocument();
    expect(screen.queryByLabelText(/closed by the fix|still open after the fix/)).toBeNull();
  });

  it("shows the as-written rate with its interval when the run had no fix arm", () => {
    const solo = {
      ...card,
      before_after: null,
      baseline_issue_ci: { point: 0.375, low: 0.137, high: 0.694 },
      hardened_issue_ci: null,
      attacks_for_10pt: 87,
      trust: { execution: "live", n_planned: 8, n_scored: 8, n_errored: 0 },
    };
    render(<ReportCard card={solo} outcomes={[]} />);
    expect(screen.getByText("As written")).toBeInTheDocument();
    expect(screen.getByText("38%")).toBeInTheDocument();
    expect(screen.getByText("95% CI 14–69")).toBeInTheDocument();
    expect(screen.getByText("Issue rate (no fix arm)")).toBeInTheDocument();
    expect(screen.getByText(/needs about 87 attacks \(had 8\)/)).toBeInTheDocument();
    expect(screen.queryByText("With fix")).toBeNull();
    expect(screen.queryByText("Prompt fix (optional)")).toBeNull();
  });

  it("labels the fix's arms as the prompt as written and with the fix", () => {
    render(<ReportCard card={card} outcomes={[]} />);
    expect(screen.getByText("As written")).toBeInTheDocument();
    expect(screen.getByText("With fix")).toBeInTheDocument();
  });
});
