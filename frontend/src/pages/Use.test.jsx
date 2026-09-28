import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Use from "./Use";
import content from "../content/integrations.json";

describe("Use page", () => {
  it("renders every integration section with its commands", () => {
    render(
      <MemoryRouter>
        <Use />
      </MemoryRouter>,
    );
    for (const section of content.sections) {
      expect(screen.getByRole("heading", { name: section.title })).toBeInTheDocument();
    }
    expect(screen.getByText(/fusion doctor/)).toBeInTheDocument();
    expect(screen.getByText(/claude plugin install fusion@fusion-first/)).toBeInTheDocument();
  });

  it("names key variables but never embeds a key", () => {
    const text = JSON.stringify(content);
    expect(text).not.toMatch(/(api[_ ]?key|token)\s*[:=]\s*["']?[\w-]{6,}/i);
    expect(text).not.toMatch(/\bsk-[\w-]{6,}/);
  });

  it("never presents a local model as the grader", () => {
    // The free local grader missed its pre-registered accuracy bar (TRUST_REPORT.md).
    const graders = JSON.stringify(content).match(/--grader [^\s"\\]+/g) || [];
    expect(graders.length).toBeGreaterThan(0);
    for (const g of graders) expect(g).toMatch(/^--grader (claude-cli|host)/);
    expect(JSON.stringify(content)).not.toMatch(/grader[^."]*local model/i);
  });
});
