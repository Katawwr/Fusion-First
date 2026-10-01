import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router-dom";
import Use from "./Use";
import content from "../content/integrations.json";

const renderUse = () =>
  render(
    <HelmetProvider>
      <MemoryRouter>
        <Use />
      </MemoryRouter>
    </HelmetProvider>,
  );

describe("Use page", () => {
  it("names the page in the browser tab", async () => {
    renderUse();
    await waitFor(() => expect(document.title).toBe("Use Fusion | Fusion First"));
  });

  it("renders every integration section with its commands", () => {
    renderUse();
    for (const section of content.sections) {
      expect(screen.getByRole("heading", { name: section.title })).toBeInTheDocument();
    }
    expect(screen.getByText(/fusion doctor/)).toBeInTheDocument();
    expect(screen.getByText(/claude plugin install fusion@fusion-first/)).toBeInTheDocument();
  });

  it("opens with running it locally, and names every target with its spec and cost", () => {
    const { container } = renderUse();
    expect(content.sections[0].id).toBe("local");
    expect(content.sections[0].steps[0].code).toBe('pip install "fusion-safety[serve]"\nfusion serve');
    for (const t of content.targets) expect(screen.getByText(t.spec)).toBeInTheDocument();
    expect(container.textContent).toMatch(/FUSION_ALLOW_API_SPEND=1/);
    expect(container.textContent).toMatch(/refuses cmd: targets/);
  });

  it("offers the runtime guard early and the prompt fix as optional", () => {
    const ids = content.sections.map((s) => s.id);
    expect(ids.indexOf("guard")).toBeLessThan(ids.indexOf("models"));
    const steps = content.sections.flatMap((s) => s.steps);
    expect(steps.some((s) => /^Apply the fix/.test(s.label))).toBe(false);
    const plugin = content.sections.find((s) => s.id === "plugin").steps.map((s) => s.code).join("\n");
    expect(plugin.indexOf("/fusion:guard")).toBeGreaterThan(-1);
    expect(plugin.indexOf("/fusion:guard")).toBeLessThan(plugin.indexOf("/fusion:harden"));
  });

  it("keeps slash commands copy-safe: no trailing comments", () => {
    const code = content.sections.flatMap((s) => s.steps).map((s) => s.code).join("\n");
    for (const line of code.split("\n").filter((l) => l.startsWith("/"))) expect(line).not.toMatch(/#/);
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
