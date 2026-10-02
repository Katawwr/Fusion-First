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
  it("shows no illustration caveat", () => {
    render(<BeforeAfterBars ba={BA} />);
    expect(screen.queryByText(/Illustration only|hand-written/i)).toBeNull();
  });
});
