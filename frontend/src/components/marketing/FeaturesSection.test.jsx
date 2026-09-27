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
    expect(text).toMatch(/stopped 78% of the real attacks/);
    expect(text).toMatch(/wrongly blocking 5%/);
  });

  it("makes no number claim when the guardrail hasn't been measured", () => {
    expect(guardrailDescription(null)).not.toMatch(/\d+%/);
  });

  it("renders the committed evidence", () => {
    render(<FeaturesSection />);
    if (evidence.runtime_guardrail) {
      expect(screen.getByText(/stopped \d+% of the real attacks/)).toBeInTheDocument();
    }
  });
});
