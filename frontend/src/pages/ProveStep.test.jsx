import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProveStep } from "./Scan";

const card = (check, kind) => ({ check, kind, grade: "B", hardened_grade: "A", before_after: null, trust: {} });

describe("ProveStep", () => {
  it("offers the Quality section only when the scan had no quality cards", () => {
    const props = { scanId: null, systemPrompt: "x", onRestart: () => {} };
    const withQuality = {
      checks: ["direct_prompt_injection", "instruction_following"],
      cards: [card("direct_prompt_injection", "safety"), card("instruction_following", "quality")],
    };
    const { unmount } = render(<ProveStep result={withQuality} {...props} />);
    expect(screen.queryByRole("heading", { name: "Quality" })).toBeNull(); // no empty heading
    unmount();
    const safetyOnly = { checks: ["direct_prompt_injection"], cards: [card("direct_prompt_injection", "safety")] };
    render(<ProveStep result={safetyOnly} {...props} />);
    expect(screen.getByRole("heading", { name: "Quality" })).toBeInTheDocument();
  });
});
