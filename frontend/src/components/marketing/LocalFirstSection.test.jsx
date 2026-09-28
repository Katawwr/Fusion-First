import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import LocalFirstSection from "./LocalFirstSection";

function renderSection() {
  return render(
    <MemoryRouter>
      <LocalFirstSection />
    </MemoryRouter>,
  );
}

describe("LocalFirstSection", () => {
  it("says the demo is an example, not a measurement", () => {
    renderSection();
    expect(screen.getByText(/canned responses/i)).toBeInTheDocument();
    expect(screen.getByText(/not a measurement/)).toBeInTheDocument();
  });

  it("names only Claude-backed graders, never a local model", () => {
    const { container } = renderSection();
    expect(screen.getByText(/graded by your coding agent or the claude CLI/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/grade[^.]*local model/i);
  });
});
