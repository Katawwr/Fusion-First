import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ProveHeadline from "./ProveHeadline";

describe("ProveHeadline", () => {
  it("calls a live result a measurement of the same attacks on both prompts", () => {
    render(<ProveHeadline baselineGrade="D" hardenedGrade="B" />);
    expect(screen.getByText(/same attacks, run against your original and hardened agent/i)).toBeInTheDocument();
    expect(screen.queryByText(/hand-written/i)).toBeNull();
  });

  it("never calls the demo's before and after a measurement", () => {
    render(<ProveHeadline baselineGrade="F" hardenedGrade="A" canned />);
    expect(screen.getByText(/hand-written/i)).toBeInTheDocument();
    expect(screen.queryByText(/apples-to-apples measurement/i)).toBeNull();
  });
});
