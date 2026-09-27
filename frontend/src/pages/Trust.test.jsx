import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Trust from "./Trust";
import { fixVerdict, interval, pct } from "../lib/evidence";
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

  it("says whether the rubric beats a plain judge, and shows the fix pooled over models", () => {
    render(
      <MemoryRouter>
        <Trust />
      </MemoryRouter>,
    );
    const rvp = evidence.rubric_vs_plain;
    if (rvp) {
      expect(screen.getByRole("heading", { name: /simply asking an AI/ })).toBeInTheDocument();
      expect(screen.getAllByText(interval(rvp.pooled.plain)).length).toBeGreaterThan(0);
      if (!rvp.claim_allowed) expect(screen.getByText(/not more accurate than asking/)).toBeInTheDocument();
    }
    for (const p of evidence.fix_pooled || []) {
      expect(screen.getAllByText(new RegExp(`^${p.experiment} \\(all models\\)$`)).length).toBe(1);
    }
  });

  it("names a significant regression instead of calling it inconclusive", () => {
    const worse = { before_after: { absolute_reduction: { point: -0.23 }, mcnemar_p: 0.039, honesty: "INCONCLUSIVE" } };
    const noisy = { before_after: { absolute_reduction: { point: -0.17 }, mcnemar_p: 0.125, honesty: "INCONCLUSIVE" } };
    const proven = { before_after: { absolute_reduction: { point: 0.4 }, mcnemar_p: 0.001, honesty: "PROVEN" } };
    expect(fixVerdict(worse).text).toMatch(/Significantly worse/);
    expect(fixVerdict(noisy).text).toMatch(/not significant/);
    expect(fixVerdict(proven).text).toMatch(/Significantly better/);
  });
});
