import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Hero from "./Hero";

vi.mock("../../hooks/useReveal", () => ({ default: () => [{ current: null }, true] }));

describe("Hero", () => {
  it("positions Fusion as measure and guard", () => {
    render(<MemoryRouter><Hero /></MemoryRouter>);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Measure and guard AI agents");
  });

  it("lists the measurement and the guardrail before the optional prompt fix", () => {
    const { container } = render(<MemoryRouter><Hero /></MemoryRouter>);
    const text = container.textContent;
    const order = ["Your agent, as written", "Runtime guardrail", "Prompt fix"].map((s) => text.indexOf(s));
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(text).toMatch(/Prompt fix\s*optional/);
  });
});
