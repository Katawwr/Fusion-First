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

  it("prefers the adopted current rules' measurement, with Llama Guard on the same attacks", () => {
    const sys = (r, o) => ({ recall: { point: r }, over_block: { point: o } });
    const step2 = {
      models: ["qwen2.5:7b", "llama3.1:8b"], decision: { new_rules: "adopted" },
      systems: { fusion: sys(0.89, 0.008), llama_guard_b: sys(0.52, 0.1) },
    };
    const text = guardrailDescription({ all: sys(0.71, 0.01) }, step2);
    expect(text).toMatch(/against qwen2.5:7b and llama3.1:8b, the guardrail stopped 89% and wrongly blocked 1%/);
    expect(text).toMatch(/Llama Guard 3 stopped 52% of the same attacks/);
    expect(guardrailDescription({ all: sys(0.71, 0.01) }, { ...step2, decision: { new_rules: "not adopted" } }))
      .toMatch(/guardrail stopped 71%/);
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
