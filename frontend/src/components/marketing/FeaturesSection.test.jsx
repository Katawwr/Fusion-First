import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import FeaturesSection from "./FeaturesSection";
import { guardrailDescription } from "../../lib/evidence";
import evidence from "../../content/evidence.json";

vi.mock("../../hooks/useReveal", () => ({ default: () => [{ current: null }, true] }));

describe("FeaturesSection", () => {
  it("states the guardrail's measured result from the evidence, not from the source", () => {
    const text = guardrailDescription({ all: { recall: { point: 0.78 }, over_block: { point: 0.05 } } });
    expect(text).toMatch(/guardrail stopped 78%/);
    expect(text).toMatch(/wrongly blocked 5% of clean conversations/);
  });

  it("makes no number claim when the guardrail hasn't been measured", () => {
    expect(guardrailDescription(null)).not.toMatch(/\d+%/);
  });

  it("keeps the fix's measured downside next to the guardrail", () => {
    const text = guardrailDescription(null);
    expect(text).toMatch(/re-tested on your model/);
    expect(text).toMatch(/rarely cut attacks and raised refusals of safe requests/);
  });

  it("renders the committed evidence", () => {
    render(<FeaturesSection />);
    if (evidence.runtime_guardrail) {
      expect(screen.getByText(/guardrail stopped \d+%/)).toBeInTheDocument();
    }
  });
});
