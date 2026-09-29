import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import UseCasesSection from "./UseCasesSection";

vi.mock("../../hooks/useReveal", () => ({ default: () => [{ current: null }, false] }));

describe("UseCasesSection", () => {
  it("names the check and the guardrail as the remedy, never the prompt fix", () => {
    const { container } = render(<UseCasesSection />);
    const text = container.textContent;
    expect(text).toMatch(/guardrail/);
    expect(text).not.toMatch(/The fix (tells|makes)/);
    expect(text).not.toMatch(/and a fix, re-tested/);
  });

  it("claims the guard blocks the refund only when the instruction came from content the bot read", () => {
    // Request binding stops injected content, not a user who asks for the refund themselves.
    const { container } = render(<UseCasesSection />);
    const text = container.textContent;
    expect(text).not.toMatch(/A shopper pastes/);
    expect(text).toMatch(/A product review the bot reads says/);
  });
});
