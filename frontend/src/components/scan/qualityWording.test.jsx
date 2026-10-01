import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import CheckToggleCard from "./CheckToggleCard";
import CheckLane from "./CheckLane";
import AttackFeedRow from "./AttackFeedRow";

// Quality checks run normal requests, not attacks, and have no OWASP mapping.
describe("quality checks are not described as attacks or OWASP items", () => {
  it("only a safety check's code label carries the OWASP tooltip", () => {
    render(<CheckToggleCard check="direct_prompt_injection" enabled onToggle={() => {}} />);
    expect(screen.getByText("LLM01 · ASI01").getAttribute("title")).toMatch(/OWASP/);
    expect(screen.getByText("LLM01 · ASI01").getAttribute("title")).toMatch(/ASI \(Agentic\) codes are provisional/);
    render(<CheckToggleCard check="instruction_following" enabled onToggle={() => {}} />);
    expect(screen.getByText("Quality").getAttribute("title") || "").not.toMatch(/OWASP/);
  });

  it("a quality lane counts requests and defects", () => {
    render(<CheckLane check="instruction_following" run={5} issues={2} />);
    expect(screen.getByText("5 requests run, 2 with a defect")).toBeInTheDocument();
    render(<CheckLane check="direct_prompt_injection" run={5} issues={2} />);
    expect(screen.getByText("5 attacks run, 2 got through")).toBeInTheDocument();
  });

  it("a quality feed row reads Defect / OK", () => {
    const row = (issue) => ({ check: "instruction_following", baseline_issue: issue, attack_label: `item ${issue}` });
    render(<AttackFeedRow outcome={row(true)} />);
    render(<AttackFeedRow outcome={row(false)} />);
    expect(screen.getByText("Defect")).toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
    expect(screen.queryByText("Got through")).toBeNull();
  });
});
