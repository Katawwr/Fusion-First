import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ProveHeadline from "./ProveHeadline";

describe("ProveHeadline", () => {
  it("calls a live result a measurement of the same attacks on both prompts", () => {
    render(<ProveHeadline baselineGrade="D" hardenedGrade="B" />);
    expect(
      screen.getByText(/Paired measurement on your model/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/hand-written/i)).toBeNull();
  });

  it("names the two arms: the prompt as written and with the fix", () => {
    render(<ProveHeadline baselineGrade="D" hardenedGrade="B" />);
    expect(screen.getByText("as written")).toBeInTheDocument();
    expect(screen.getByText("with fix")).toBeInTheDocument();
  });

  it("never calls the demo's before and after a measurement", () => {
    render(<ProveHeadline baselineGrade="F" hardenedGrade="A" canned />);
    expect(screen.queryByText(/hand-written/i)).toBeNull();
    expect(screen.queryByText(/Paired measurement/i)).toBeNull();
    expect(screen.queryByText(/apples-to-apples measurement/i)).toBeNull();
  });
});
