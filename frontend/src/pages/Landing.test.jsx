import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router-dom";
import Landing from "./Landing";
import evidence from "../content/evidence.json";
import { interval } from "../lib/evidence";

const renderLanding = () =>
  render(
    <HelmetProvider>
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    </HelmetProvider>,
  );

describe("Overview page", () => {
  it("reads as abstract, method, results, limitations, run it locally", () => {
    renderLanding();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/runtime guard/i);
    const h2 = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(h2).toEqual(["Method", "Results", "Limitations", "Run Locally"]);
  });

  it("renders the step 3 guard result with its interval from the evidence", () => {
    renderLanding();
    const v3 = evidence.step3_guard.arms.v3;
    const table = screen.getAllByRole("table")[0];
    expect(within(table).getAllByText(interval(v3.recall)).length).toBeGreaterThan(0);
    expect(within(table).getAllByText(interval(v3.over_block)).length).toBeGreaterThan(0);
    expect(within(table).getByText("Negative results")).toBeInTheDocument();
  });

  it("states the negative results plainly", () => {
    const { container } = renderLanding();
    expect(container.textContent).toMatch(/Rubric grading is not more accurate than one plain question/);
    expect(container.textContent).toMatch(/prompt fix did not reliably reduce attacks/);
  });

  it("lists the findings below the results table", () => {
    const { container } = renderLanding();
    const results = container.querySelector("#results");
    const list = results.querySelector("ol");
    const table = results.querySelector("table");
    expect(list.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
  });

  it("shows the headline stats without a caption", () => {
    const { container } = renderLanding();
    expect(container.querySelector(".headline-stats figcaption")).toBeNull();
    expect(container.textContent).not.toMatch(/Pre-registered, scored once on fresh attacks/);
  });

  it("links to the demo, the local setup and the full evidence", () => {
    renderLanding();
    expect(screen.getByRole("link", { name: "Run Demo" })).toHaveAttribute("href", "/scan");
    expect(screen.getAllByRole("link", { name: "Run Locally" })[0]).toHaveAttribute("href", "/use#local");
    expect(screen.getByRole("link", { name: /Evidence/ })).toHaveAttribute("href", "/trust");
  });

  it("keeps a space between words and inline code", () => {
    const { container } = renderLanding();
    for (const code of container.querySelectorAll("dd code, p code")) {
      const prev = code.previousSibling;
      const before = prev?.nodeType === Node.TEXT_NODE ? prev.textContent : "";
      if (before) expect(before).toMatch(/[\s(]$/);
    }
  });

  it("says which results were pre-registered without claiming all were", () => {
    const { container } = renderLanding();
    expect(container.textContent).toMatch(/Committed results with 95% intervals/);
    expect(container.textContent).not.toMatch(/Pre-registered results with/);
  });

  it("shows how to run it locally with the user's own target", () => {
    const { container } = renderLanding();
    expect(container.textContent).toMatch(/pip install "fusion-safety\[serve\]"/);
    expect(container.textContent).toMatch(/FUSION_ALLOW_API_SPEND=1/);
    expect(container.textContent).toMatch(/openai-compat:/);
  });
});
