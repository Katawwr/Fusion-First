import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import BeforeAfterBars from "./BeforeAfterBars";

const BA = {
  baseline_issue_rate: 0.88,
  hardened_issue_rate: 0.0,
  absolute_reduction: { point: 0.88, low: 0.63, high: 1.0 },
  honesty: "PRELIMINARY",
  honesty_reasons: [],
};

describe("BeforeAfterBars", () => {
  it("says a demo's 'after' answers are an illustration, not a measurement", () => {
    render(<BeforeAfterBars ba={BA} canned />);
    expect(screen.getByText(/hand-written/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /measured/i })).toHaveAttribute("href", "/trust");
  });

  it("adds no such caveat to a live measurement", () => {
    render(<BeforeAfterBars ba={BA} />);
    expect(screen.queryByText(/hand-written/i)).toBeNull();
  });
});
