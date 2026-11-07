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
  n_pairs: 8,
};

describe("BeforeAfterBars", () => {
  it("shows no illustration caveat", () => {
    render(<BeforeAfterBars ba={BA} />);
    expect(screen.queryByText(/Illustration only|hand-written/i)).toBeNull();
  });

  it("shows each arm's 95% interval and the sample-size hint", () => {
    render(
      <BeforeAfterBars
        ba={BA}
        baselineCi={{ point: 0.875, low: 0.529, high: 0.978 }}
        hardenedCi={{ point: 0, low: 0, high: 0.324 }}
        attacksFor10pt={36}
      />,
    );
    expect(screen.getByText("95% CI 53–98")).toBeTruthy();
    expect(screen.getByText("95% CI 0–32")).toBeTruthy();
    expect(screen.getByText(/±10 pts at this rate needs about 36 attacks \(had 8\)/)).toBeTruthy();
  });

  it("renders an older payload without the intervals", () => {
    render(<BeforeAfterBars ba={BA} />);
    expect(screen.getByText("As written")).toBeTruthy();
    expect(screen.queryByText(/95% CI/)).toBeNull();
    expect(screen.queryByText(/needs about/)).toBeNull();
  });
});
