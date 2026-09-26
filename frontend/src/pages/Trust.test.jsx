import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Trust from "./Trust";
import { interval, pct } from "../lib/evidence";
import evidence from "../content/evidence.json";

describe("Trust page", () => {
  it("formats both interval shapes", () => {
    expect(pct(0.925)).toBe("93%");
    expect(interval({ point: 0.8, low: 0.68, high: 0.88 })).toBe("80% (68%–88%)");
    expect(interval({ point: 0.05, ci95: [0.022, 0.112] })).toBe("5% (2%–11%)");
    expect(interval(null)).toBe("—");
  });

  it("renders only what the evidence contains, and says what isn't measured", () => {
    render(
      <MemoryRouter>
        <Trust />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "How far to trust Fusion" })).toBeInTheDocument();
    if (!evidence.fix_efficacy) {
      expect(screen.getByText(/Not yet measured: the as-written vs fixed prompt/)).toBeInTheDocument();
    }
    for (const j of evidence.judge_accuracy) {
      expect(screen.getAllByText(interval(j.accuracy)).length).toBeGreaterThan(0);
    }
  });
});
